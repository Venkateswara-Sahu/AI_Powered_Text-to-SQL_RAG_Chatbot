import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from config import Config


class SchemaRAG:
    """
    RAG pipeline for Northwind database schema.
    Embeds table/column metadata using sentence-transformers and
    retrieves relevant schema context via FAISS (Facebook AI Similarity Search).
    """

    def __init__(self):
        """Initialize the embedding model and FAISS index."""
        print("[RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        self._documents = []       # List of document text strings
        self._metadata = []        # List of metadata dicts
        self._index = None         # FAISS index
        self._is_indexed = False
        print("[RAG] Embedding model loaded.")

    def build_schema_documents(self, schema_info: list[dict]) -> list[dict]:
        """
        Convert raw schema metadata into rich text documents for embedding.
        Each document describes one table comprehensively.
        """
        documents = []

        for table in schema_info:
            table_name = table["table_name"]

            # Build column descriptions
            col_lines = []
            primary_keys = []
            for col in table["columns"]:
                col_name = col["COLUMN_NAME"]
                data_type = col["DATA_TYPE"]
                nullable = "nullable" if col["IS_NULLABLE"] == "YES" else "not null"
                key_info = ""
                if col["COLUMN_KEY"] == "PRI":
                    key_info = " (PRIMARY KEY)"
                    primary_keys.append(col_name)
                elif col["COLUMN_KEY"] == "MUL":
                    key_info = " (INDEXED)"
                elif col["COLUMN_KEY"] == "UNI":
                    key_info = " (UNIQUE)"

                col_lines.append(f"  - {col_name}: {data_type}, {nullable}{key_info}")

            # Build foreign key descriptions
            fk_lines = []
            for fk in table["foreign_keys"]:
                fk_lines.append(
                    f"  - {fk['COLUMN_NAME']} → {fk['REFERENCED_TABLE_NAME']}.{fk['REFERENCED_COLUMN_NAME']}"
                )

            # Build sample data preview
            sample_lines = []
            if table["sample_rows"]:
                for i, row in enumerate(table["sample_rows"][:3]):
                    clean_row = {
                        k: v for k, v in row.items()
                        if v != "<binary>" and v is not None
                    }
                    sample_lines.append(f"  Row {i + 1}: {clean_row}")

            # Compose the full document
            doc = f"Table: {table_name}\n"
            doc += f"Row count: {table['row_count']}\n"
            doc += f"Columns:\n" + "\n".join(col_lines) + "\n"
            if fk_lines:
                doc += f"Foreign Keys:\n" + "\n".join(fk_lines) + "\n"
            if sample_lines:
                doc += f"Sample Data:\n" + "\n".join(sample_lines) + "\n"

            documents.append({
                "id": f"table_{table_name}",
                "text": doc,
                "metadata": {"table_name": table_name},
            })

        return documents

    def index_schema(self, schema_info: list[dict]):
        """Embed and store schema documents in FAISS index."""
        if self._is_indexed:
            print("[RAG] Schema already indexed, skipping.")
            return

        documents = self.build_schema_documents(schema_info)

        if not documents:
            print("[RAG] No schema documents to index.")
            return

        self._documents = [doc["text"] for doc in documents]
        self._metadata = [doc["metadata"] for doc in documents]

        print(f"[RAG] Indexing {len(documents)} table descriptions...")

        # Encode all documents
        embeddings = self.embed_model.encode(self._documents, convert_to_numpy=True)
        embeddings = embeddings.astype(np.float32)

        # Normalize for cosine similarity
        faiss.normalize_L2(embeddings)

        # Create FAISS index (Inner Product on normalized vectors = cosine similarity)
        dimension = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dimension)
        self._index.add(embeddings)

        self._is_indexed = True
        print(f"[RAG] Schema indexed successfully ({len(documents)} tables in FAISS).")

    def retrieve(self, question: str, top_k: int = None) -> str:
        """
        Retrieve the most relevant schema context for a user question.

        Args:
            question: Natural language question
            top_k: Number of top results to return

        Returns:
            Combined schema context string
        """
        if top_k is None:
            top_k = Config.TOP_K_SCHEMA_RESULTS

        if not self._is_indexed or self._index is None:
            return "Schema not indexed yet. Please wait for initialization."

        # Encode and normalize query
        query_embedding = self.embed_model.encode([question], convert_to_numpy=True)
        query_embedding = query_embedding.astype(np.float32)
        faiss.normalize_L2(query_embedding)

        # Search FAISS index
        top_k = min(top_k, len(self._documents))
        scores, indices = self._index.search(query_embedding, top_k)

        # Combine relevant documents
        relevant_docs = [self._documents[i] for i in indices[0] if i < len(self._documents)]

        if not relevant_docs:
            return "No relevant schema found."

        context = "\n---\n".join(relevant_docs)
        return context

    def get_all_table_names(self) -> list[str]:
        """Get all indexed table names."""
        return [m["table_name"] for m in self._metadata]
