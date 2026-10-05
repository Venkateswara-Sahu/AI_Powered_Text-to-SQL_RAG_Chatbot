"""Ground-truth evaluation against the isolated, SELECT-only F1 snapshot.

Run --check-references before model evaluation. No chat store or production
database is used. Each question starts with empty history. Artifacts are unique
and preserve references, retrieval labels/ranks, attempts and full API results.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from dotenv import dotenv_values
from benchmark import compare_result_sets, score_retrieval, summarize_evaluation
from reference_cases import CASES
from agent.tools import AgentTools

class FaultProbeTools(AgentTools):
    """Controlled development-only fault; production tools are untouched."""
    def __init__(self,db,rag):
        super().__init__(db,rag)
        self.injected=False
    def execute_sql(self,sql):
        if not self.injected:
            from sqlglot import parse_one,exp
            self.injected=True
            query=parse_one(sql,read='mysql')
            query.set('expressions',[exp.column('__f1_probe_missing_column__')]+query.expressions)
            bad=query.sql(dialect='mysql')
            result=self.db.execute_query(bad)
            result['executed_sql']=result.get('executed_sql',bad)
            result['controlled_fault']='injected nonexistent projection column on first execution only'
            return result
        return super().execute_sql(sql)

def encode(data):
    return json.dumps(data,sort_keys=True,default=str,ensure_ascii=False,separators=(',',':')).encode()

def code_hash():
    paths = sorted(p for folder in ['agent','database','rag','llm','tests']
                   for p in (ROOT/folder).glob('*.py'))+[ROOT/'config.py']
    return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+p.read_bytes() for p in paths)).hexdigest()

def setup_local(credentials=None):
    # Override every connection variable before Config is imported: it is never
    # permitted to inherit production database settings from the supplied file.
    cfg = dotenv_values(credentials) if credentials else {}
    os.environ.update(MYSQL_HOST='127.0.0.1',MYSQL_PORT='33070',MYSQL_USER='f1_eval_reader',
                      MYSQL_PASSWORD='f1-local-evaluation-only',MYSQL_DATABASE='f1db',MYSQL_SSL='false')
    if credentials:
        if not cfg.get('GROQ_API_KEY'):
            raise ValueError('Credentials file lacks GROQ_API_KEY')
        os.environ['GROQ_API_KEY']=cfg['GROQ_API_KEY']
        os.environ['GROQ_MODEL']=cfg.get('GROQ_MODEL','openai/gpt-oss-120b')
    # AgentTools may already have imported Config. Override its class values as
    # well as environment variables; never trust import order for isolation.
    from config import Config
    Config.MYSQL_HOST='127.0.0.1'; Config.MYSQL_PORT=33070
    Config.MYSQL_USER='f1_eval_reader'; Config.MYSQL_PASSWORD='f1-local-evaluation-only'
    Config.MYSQL_DATABASE='f1db'; Config.MYSQL_SSL=False
    if credentials:
        Config.GROQ_API_KEY=os.environ['GROQ_API_KEY']
        Config.GROQ_MODEL=os.environ['GROQ_MODEL']
    from database.connector import DatabaseConnector
    return DatabaseConnector()

def check_references(db):
    records=[]
    from agent.tools import AgentTools
    for case in CASES:
        actual_tables=set(AgentTools.extract_tables_from_sql(case['reference_sql']))
        if actual_tables != set(case['required_tables']):
            raise ValueError(f"{case['id']}: independent labels disagree with authored SQL tables")
        result=db.execute_query(case['reference_sql'])
        if not result['success']:
            raise ValueError(f"{case['id']}: reference execution failed: {result['error']}")
        if result['row_count'] >= 50:
            raise ValueError(f"{case['id']}: reference reaches application cap; refine contract")
        records.append({'id':case['id'],'columns':result['columns'],'rows':result['rows'],
                        'numeric_columns':result['numeric_columns'],'integer_columns':result['integer_columns']})
    return records

def metrics_by_variant(records):
    output={}
    for variant in ['plain_dense','enriched_dense','enriched_augmented']:
        rows=[r['retrieval'][variant] for r in records]
        output[variant]={key:sum(r[key] for r in rows)/len(rows) if rows else None
                         for key in ['reciprocal_rank','recall_at_k','precision_at_k','all_required_tables_found']}
        output[variant]['cases']=len(rows)
        output[variant]['k']=7 if variant!='enriched_augmented' else 'all injected context tables'
        if variant=='enriched_augmented':
            # Injection order is not a semantic ranking. Report coverage only.
            output[variant].pop('reciprocal_rank')
    return output

def verify_snapshot(db,manifest):
    """Fail before model calls if the current local tables differ from the freeze."""
    connection=db.get_connection()
    cursor=connection.cursor()
    try:
        cursor.execute('SHOW TABLES')
        if {r[0] for r in cursor.fetchall()} != set(manifest['tables']):
            raise ValueError('Snapshot table set changed.')
        for name,expected in sorted(manifest['tables'].items()):
            if not name.replace('_','').isalnum():
                raise ValueError('Invalid manifest table identifier.')
            cursor.execute(f'SHOW KEYS FROM `{name}` WHERE Key_name = %s',('PRIMARY',))
            keys=[row[4] for row in cursor.fetchall()]
            cursor.execute(f'SELECT * FROM `{name}` ORDER BY '+','.join(f'`{key}`' for key in keys))
            digest=hashlib.sha256(); count=0
            while rows:=cursor.fetchmany(1000):
                for row in rows:
                    count+=1
                    digest.update((json.dumps(row,default=str,ensure_ascii=False,separators=(',',':'))+'\n').encode())
            if count!=expected['rows'] or digest.hexdigest()!=expected['content_sha256']:
                raise ValueError(f'Snapshot content changed: {name}')
    finally:
        cursor.close(); connection.close()
    print('[Snapshot] all 14 table content hashes match',flush=True)

class PacedModel:
    """Transparent benchmark-only pacing; all wait time and calls are retained.

    Model/settings/prompts are unchanged. The token bucket is conservative at
    the observed 8000-token/minute free-tier limit. This is not production
    throughput measurement. Explicit transient provider retries are recorded.
    """
    def __init__(self, model):
        self.model=model
        self.remaining=8000.0
        self.updated=time.monotonic()
        self.calls=[]
    def invoke(self,messages):
        from groq import RateLimitError
        estimate=sum(len(str(m.content)) for m in messages)/3+1000
        if estimate>8000:
            raise ValueError('Prompt plus output reserve exceeds the observed per-minute quota.')
        started=time.perf_counter()
        elapsed=time.monotonic()-self.updated
        self.remaining=min(8000,self.remaining+elapsed*8000/60)
        wait=max(0,(estimate-self.remaining)*60/8000)
        if wait:
            print(f'[Quota pacing] waiting {wait:.1f}s',flush=True)
            time.sleep(wait)
        self.remaining=max(0,self.remaining-estimate)
        self.updated=time.monotonic()
        retries=[]
        for attempt in range(3):
            try:
                result=self.model.invoke(messages)
                self.calls.append({'elapsed_s':time.perf_counter()-started,'quota_wait_s':wait,
                    'provider_retries':retries,'token_usage':result.response_metadata.get('token_usage',{}),
                    'finish_reason':result.response_metadata.get('finish_reason'),
                    'system_fingerprint':result.response_metadata.get('system_fingerprint'),
                    'response':result.content})
                return result
            except RateLimitError as exc:
                delay=float(exc.response.headers.get('retry-after','5'))
                retries.append({'http_status':429,'requested_delay_s':delay,'actual_wait_s':0})
                if delay>60 or attempt==2:
                    self.calls.append({'error':'Provider quota exceeded','error_type':'RateLimitError',
                                       'http_status':429,'elapsed_s':time.perf_counter()-started,
                                       'provider_retries':retries,'quota_wait_s':wait})
                    raise
                print(f'[Provider 429] waiting {delay+1:.1f}s',flush=True)
                sleep_start=time.perf_counter()
                time.sleep(delay+1)
                retries[-1]['actual_wait_s']=time.perf_counter()-sleep_start
            except Exception as exc:
                self.calls.append({'error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None),
                    'elapsed_s':time.perf_counter()-started,'quota_wait_s':wait,'provider_retries':retries})
                raise

def build_benchmark_model(api_key,model):
    from langchain_groq import ChatGroq
    # Construct a new SDK client: model_copy would retain its original client
    # retry/timeout settings despite changing the Pydantic wrapper fields.
    return ChatGroq(api_key=api_key,model=model,temperature=0.1,max_tokens=800,
                    timeout=60,max_retries=0)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--split',choices=['dev','eval'],default='dev')
    parser.add_argument('--credentials',type=Path,help='Only Groq key/model are read; DB settings are overridden')
    parser.add_argument('--check-references',action='store_true')
    parser.add_argument('--output',type=Path,required=True,help='New JSON artifact; existing files cannot be overwritten')
    parser.add_argument('--pause',type=float,default=10,help='Pause between questions, excluded from query latency')
    parser.add_argument('--dev-limit',type=int,help='Development-only pilot; evaluation always runs all 40 cases')
    parser.add_argument('--reference-artifact',type=Path,default=ROOT/'docs/evaluation/references.json')
    parser.add_argument('--retry-probe',action='store_true',help='Inject an invalid column in the first five DEV cases; separate recovery measurement')
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('Existing artifacts cannot be overwritten.')
    if args.dev_limit and args.split!='dev':
        raise ValueError('Evaluation set cannot be filtered.')
    if args.retry_probe and (args.split!='dev' or args.dev_limit):
        raise ValueError('Controlled retry probes use the first five development questions only.')
    db=setup_local(args.credentials)
    references=check_references(db)
    snapshot=json.loads((ROOT/'artifacts/benchmarks/snapshot/manifest.json').read_text())
    verify_snapshot(db,snapshot)
    output={'schema_version':3,'timestamp':datetime.now(timezone.utc).isoformat(),
            'split':'controlled_retry_probe' if args.retry_probe else args.split,
            'snapshot':snapshot,'suite_sha256':hashlib.sha256(encode(CASES)).hexdigest(),
            'code_sha256':code_hash(),'cases':[],'references':references,
            'methodology':'Independent reference-result equivalence; exact projection/order contracts; numerical tolerance 1e-6; fresh history per case; no model sees reference SQL/results or required table labels.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    if args.check_references:
        args.output.write_bytes(encode(output))
        print(f'All {len(references)} references execute; independent labels match reference tables.')
        return
    frozen=json.loads(args.reference_artifact.read_text(encoding='utf-8'))
    if encode(references)!=encode(frozen['references']) or frozen['suite_sha256']!=output['suite_sha256']:
        raise ValueError('Current references differ from the independently reviewed frozen artifact.')
    output['reference_artifact_sha256']=hashlib.sha256(args.reference_artifact.read_bytes()).hexdigest()
    if not args.credentials and not os.getenv('GROQ_API_KEY'):
        raise ValueError('Model evaluation requires Groq credentials.')
    from agent.agent import SQLAgent
    from agent.tools import AgentTools
    from config import Config
    from rag.embeddings import SchemaRAG
    import torch
    torch.set_num_threads(2)
    rag=SchemaRAG()
    weights_digest=hashlib.sha256()
    for name,weight in sorted(rag.embed_model.state_dict().items()):
        weights_digest.update(name.encode()+weight.detach().cpu().numpy().tobytes())
    schema=db.get_schema_info()
    if len(schema)!=14:
        raise ValueError('Snapshot must have exactly 14 F1 tables and no chat tables.')
    rag.index_schema(schema)
    plain=SchemaRAG.__new__(SchemaRAG)
    plain.embed_model=rag.embed_model
    plain._documents=[]; plain._metadata=[]; plain._index=None; plain._is_indexed=False
    plain.SEMANTIC_ENRICHMENT={}; plain.TABLE_CO_OCCURRENCE={}
    plain.index_schema(schema)
    agent=SQLAgent(AgentTools(db,rag))
    # Explicitly bound API requests. Provider errors count as failures, never
    # disappear from the evaluation. No implicit network retries hide latency.
    agent.llm=PacedModel(build_benchmark_model(Config.GROQ_API_KEY,Config.GROQ_MODEL))
    output.update(model=Config.GROQ_MODEL,temperature=0.1,max_tokens=800,
                  embedding_model='sentence-transformers/all-MiniLM-L6-v2',
                  embedding_revision=getattr(rag.embed_model._first_module().auto_model.config,'_commit_hash',None),
                  embedding_weights_sha256=weights_digest.hexdigest(),
                  implementation_commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),
                  provider_timeout_s=60,provider_sdk_retries=0,latency_includes_quota_pacing=True,
                  dependencies={d.metadata['Name']:d.version for d in importlib.metadata.distributions()},
                  schema_sha256=hashlib.sha256(encode(schema)).hexdigest(),
                  prompt_sha256=hashlib.sha256((ROOT/'llm/prompt_templates.py').read_bytes()).hexdigest(),
                  retrieval_baseline='Current code with enrichment and co-occurrence disabled, identical schema/sample rows/model/top-7; not a reconstruction of historical MRR.')
    expected={r['id']:r for r in references}
    selected=[case for case in CASES if case['split']==args.split]
    if args.dev_limit:
        selected=selected[:args.dev_limit]
    if args.retry_probe:
        selected=selected[:5]
        output['controlled_fault']='Unknown projection column injected in first execution only; real model handles database feedback; not natural-query accuracy.'
    start_hash=output['code_sha256']
    # Progress uses a distinct JSONL file and is flushed per case. Final JSON
    # is created exclusively only when the full run completes.
    with args.output.with_suffix('.jsonl').open('x',encoding='utf-8') as journal:
        for case in selected:
            if args.retry_probe:
                agent.tools=FaultProbeTools(db,rag)
            ranked=rag.retrieve_with_scores(case['question'])
            enriched=[r['table'] for r in ranked if r['score']!=-1]
            augmented=[r['table'] for r in ranked]
            baseline=[r['table'] for r in plain.retrieve_with_scores(case['question'])]
            retrieval={name:score_retrieval(tables,case['required_tables'],k)
                       for name,tables,k in [('plain_dense',baseline,7),('enriched_dense',enriched,7),('enriched_augmented',augmented,len(augmented))]}
            started=time.perf_counter()
            call_start=len(agent.llm.calls)
            response=agent.run(case['question'],chat_history=[])
            elapsed=time.perf_counter()-started
            attempts=[s for s in response['agent_steps'] if s.get('node')=='execute_sql']
            first=attempts[0].get('execution_result',{}) if attempts else {}
            final=response.get('results')
            record={**case,'expected_result':expected[case['id']],
                    'first_attempt_correct':bool(first.get('success')) and compare_result_sets(first,expected[case['id']],ordered=case['ordered']),
                    'final_correct':final is not None and not response.get('error') and compare_result_sets(final,expected[case['id']],ordered=case['ordered']),
                    'retries':sum(s.get('node')=='retry_sql' for s in response['agent_steps']),
                    'elapsed_s':elapsed,'response':response,'retrieval':retrieval,
                    'model_calls':agent.llm.calls[call_start:],
                    'retrieval_ranks':{'plain_dense':baseline,'enriched_dense':enriched,'enriched_augmented':augmented}}
            output['cases'].append(record)
            journal.write(json.dumps(record,default=str,ensure_ascii=False)+'\n'); journal.flush()
            print(f"{case['id']}: first={record['first_attempt_correct']} final={record['final_correct']} retries={record['retries']} {elapsed:.1f}s",flush=True)
            if response.get('error') and any(token in str(response['error']).lower() for token in ['rate_limit','rate limit','429','401','invalid_api_key']):
                raise RuntimeError('Provider quota/authentication interrupted this run; JSONL retained, no full-set estimate emitted.')
            if any(c.get('http_status') in (401,429) for c in record['model_calls']):
                raise RuntimeError('Provider quota/authentication affected this run; JSONL retained, no full-set estimate emitted.')
            if args.pause:
                time.sleep(args.pause)
    if code_hash()!=start_hash:
        raise RuntimeError('Evaluation code changed during run; refusing a frozen-code claim.')
    verify_snapshot(db,snapshot)
    output['summary']=summarize_evaluation(output['cases'])
    output['retrieval_summary']=metrics_by_variant(output['cases'])
    with args.output.open('x',encoding='utf-8') as handle:
        json.dump(output,handle,indent=2,default=str,ensure_ascii=False,allow_nan=False)
    print(json.dumps({'summary':output['summary'],'retrieval':output['retrieval_summary']},indent=2),flush=True)

if __name__=='__main__':
    main()
