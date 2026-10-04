"""Restore only F1 tables into the deliberately named LOCAL evaluation container.

Never connects to production. Does not import conversations/messages. The
original backup remains private and unchanged. Requires the MySQL 8.4 container
described in docs/ground-truth-evaluation.md; imports use docker exec stdin.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import mysql.connector

F1_TABLES = {'circuits','constructor_results','constructor_standings','constructors',
             'driver_standings','drivers','lap_times','pit_stops','qualifying','races',
             'results','seasons','sprint_results','status'}
CONTAINER = 'codex-f1-eval-20261004'
PASSWORD = 'f1-local-evaluation-only'  # Throwaway localhost credential, not a cloud secret.

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('backup', type=Path)
    args = parser.parse_args()
    raw = args.backup.read_bytes()
    text = raw.decode('utf-8')
    starts = list(re.finditer(r'DROP TABLE IF EXISTS `([^`]+)`;', text))
    selected = []
    names = []
    for index, match in enumerate(starts):
        name = match.group(1)
        if name in F1_TABLES:
            block = text[match.start(): starts[index+1].start() if index+1<len(starts) else len(text)]
            block = re.sub(r'/\*T!\[.*?\].*?\*/', '', block)
            selected.append(block)
            names.append(name)
    if set(names) != F1_TABLES or len(names) != 14:
        raise ValueError('Backup does not contain exactly the expected 14 F1 tables.')
    payload = ('SET FOREIGN_KEY_CHECKS=0;\n'+'\n'.join(selected)+'\nSET FOREIGN_KEY_CHECKS=1;').encode('utf-8')
    artifact = Path('artifacts/benchmarks/snapshot')
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact/'f1-only.sql').write_bytes(payload)
    command = ['docker','exec','-i','-e',f'MYSQL_PWD={PASSWORD}',CONTAINER,
               'mysql','-uroot','--default-character-set=utf8mb4','f1db']
    subprocess.run(command, input=payload, check=True, capture_output=True)
    setup = "CREATE USER IF NOT EXISTS 'f1_eval_reader'@'%' IDENTIFIED BY 'f1-local-evaluation-only'; GRANT SELECT ON f1db.* TO 'f1_eval_reader'@'%'; SET GLOBAL max_execution_time=15000;"
    subprocess.run(command, input=setup.encode(), check=True, capture_output=True)
    conn = mysql.connector.connect(host='127.0.0.1',port=33070,user='f1_eval_reader',password=PASSWORD,database='f1db')
    cur = conn.cursor()
    manifest = {'source_backup_sha256':hashlib.sha256(raw).hexdigest(),
                'f1_only_sql_sha256':hashlib.sha256(payload).hexdigest(),
                'tables':{}, 'excluded_tables':['conversations','messages'],
                'database_engine':'MySQL 8.4, isolated localhost container',
                'query_account':'SELECT-only f1_eval_reader', 'query_timeout_ms':15000}
    for name in sorted(F1_TABLES):
        cur.execute(f'SELECT COUNT(*) FROM `{name}`')
        count = cur.fetchone()[0]
        cur.execute(f'SHOW KEYS FROM `{name}` WHERE Key_name = %s',('PRIMARY',))
        keys = [row[4] for row in cur.fetchall()]
        cur.execute(f'SELECT * FROM `{name}` ORDER BY '+','.join(f'`{key}`' for key in keys))
        digest = hashlib.sha256()
        while rows := cur.fetchmany(1000):
            for row in rows:
                digest.update((json.dumps(row,default=str,ensure_ascii=False,separators=(',',':'))+'\n').encode())
        manifest['tables'][name]={'rows':count,'content_sha256':digest.hexdigest()}
    cur.execute('SELECT MIN(year), MAX(year) FROM races')
    manifest['race_year_range']=list(cur.fetchone())
    cur.execute('SHOW GRANTS')
    manifest['grants']=[row[0] for row in cur.fetchall()]
    cur.close(); conn.close()
    (artifact/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'tables':len(manifest['tables']),'total_rows':sum(t['rows'] for t in manifest['tables'].values()),'race_year_range':manifest['race_year_range'],'snapshot_sha256':manifest['f1_only_sql_sha256']}))

if __name__=='__main__':
    main()
