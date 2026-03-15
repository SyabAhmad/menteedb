from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .embeddings import HashingEmbedder
from .file_handler import (
    append_record,
    append_vector,
    create_table_files,
    ensure_path,
    load_schema,
    load_vectors,
    read_all_records,
    set_storage_format,
    table_exists,
)


class QueryBuilder:
    """Fluent query builder for constructing queries without SQL syntax."""

    def __init__(self, db: MenteeDB, table_name: str):
        self._db = db
        self._table_name = table_name
        self._selected_fields: Optional[List[str]] = None
        self._conditions: List[tuple] = []
        self._text_query: Optional[str] = None
        self._text_fields: Optional[List[str]] = None
        self._case_sensitive: bool = False
        self._vector_query: Optional[str] = None
        self._top_k: int = 5
        self._min_score: Optional[float] = None

    def select(self, *fields: str) -> QueryBuilder:
        """
        Select specific fields to return from each record.

        Example:
            query.select('age', 'name')
        """
        self._selected_fields = list(fields)
        return self

    def where(self, field: str, operator: str, value: Any) -> QueryBuilder:
        """
        Add a condition to filter records.

        Supported operators: ==, !=, >, <, >=, <=, in, contains

        Examples:
            query.where('age', '>', 18)
            query.where('name', '==', 'John')
            query.where('status', 'in', ['active', 'pending'])
            query.where('city', 'contains', 'New')
        """
        if operator not in ("==", "!=", ">", "<", ">=", "<=", "in", "contains"):
            raise ValueError(f"Unsupported operator: {operator}")
        self._conditions.append((field, operator, value))
        return self

    def search(self, query: str, in_fields: Optional[List[str]] = None, case_sensitive: bool = False) -> QueryBuilder:
        """
        Add a text search filter.

        Example:
            query.search('python', in_fields=['description', 'title'])
        """
        self._text_query = query
        self._text_fields = in_fields
        self._case_sensitive = case_sensitive
        return self

    def vector_search(self, query: str, top_k: int = 5, min_score: Optional[float] = None) -> QueryBuilder:
        """
        Add a vector similarity search.

        Example:
            query.vector_search('machine learning', top_k=10)
        """
        self._vector_query = query
        self._top_k = top_k
        self._min_score = min_score
        return self

    def execute(self) -> List[Dict[str, Any]]:
        """Execute the query and return results."""
        # Load all records
        rows = read_all_records(self._db.base_path, self._table_name)

        # Apply conditions
        for field, operator, value in self._conditions:
            rows = [r for r in rows if self._evaluate_condition(r, field, operator, value)]

        # Apply text search
        if self._text_query is not None:
            rows = self._db._text_filter_rows(
                rows,
                self._text_query,
                text_fields=self._text_fields,
                case_sensitive=self._case_sensitive,
            )

        # Apply vector search if specified
        if self._vector_query is not None:
            schema = load_schema(self._db.base_path, self._table_name)
            vector_field = schema.get("vector_field")
            if not vector_field:
                raise ValueError(f"Table '{self._table_name}' is not configured for vector search.")

            embedding_dim = schema.get("embedding_dim")
            ids, vectors = load_vectors(self._db.base_path, self._table_name, dimension=embedding_dim)

            if vectors is not None and len(ids) > 0:
                query_vec = self._db.embedder.encode(self._vector_query).astype(np.float32)
                if query_vec.shape[0] != vectors.shape[1]:
                    raise ValueError("Query embedding dimension does not match stored vectors.")

                scores = self._db._cosine_scores(vectors, query_vec)
                by_id = {row["_id"]: row for row in rows}

                ranked = []
                for idx, rid in enumerate(ids):
                    row = by_id.get(rid)
                    if row is None:
                        continue
                    score = float(scores[idx])
                    if self._min_score is not None and score < self._min_score:
                        continue
                    ranked.append({"id": rid, "score": score, "record": row})

                ranked.sort(key=lambda x: x["score"], reverse=True)
                rows = [item["record"] for item in ranked[: self._top_k]]

        # Select specific fields
        if self._selected_fields:
            rows = [self._select_fields(row, self._selected_fields) for row in rows]

        # Format results
        return [{"id": row["_id"], "data": {k: v for k, v in row.items() if k != "_id"}} for row in rows]

    @staticmethod
    def _evaluate_condition(record: Dict[str, Any], field: str, operator: str, value: Any) -> bool:
        """Evaluate a condition against a record."""
        record_value = record.get(field)

        if operator == "==":
            return record_value == value
        elif operator == "!=":
            return record_value != value
        elif operator == ">":
            return record_value is not None and record_value > value
        elif operator == "<":
            return record_value is not None and record_value < value
        elif operator == ">=":
            return record_value is not None and record_value >= value
        elif operator == "<=":
            return record_value is not None and record_value <= value
        elif operator == "in":
            return record_value in value
        elif operator == "contains":
            if isinstance(record_value, str):
                return str(value).lower() in record_value.lower()
            return False

        return False

    @staticmethod
    def _select_fields(row: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """Extract only selected fields from a record."""
        return {
            "_id": row["_id"],
            **{field: row.get(field) for field in fields if field in row},
        }


class MenteeDB:
    def __init__(
        self,
        base_path: str = "./menteedb_data",
        embedder: Optional[Any] = None,
        secure_permissions: bool = True,
        use_encryption: bool = False,
        encryption_key: Optional[str] = None,
    ) -> None:
        """
        Initialize MenteeDB with optional encryption.

        Args:
            base_path: Path to store database files
            embedder: Custom embedder instance
            secure_permissions: Set restrictive file permissions
            use_encryption: Enable AES-256-GCM encryption for records
            encryption_key: Password for encryption (min 8 chars recommended)
        """
        self.base_path = Path(base_path)
        ensure_path(self.base_path)
        self.embedder = embedder or HashingEmbedder()
        self.secure_permissions = secure_permissions
        
        # Configure storage format with encryption if requested
        set_storage_format(use_encryption=use_encryption, encryption_key=encryption_key)

    def create_table(self, table_name: str, fields: Dict[str, str], vector_field: Optional[str] = None) -> Dict[str, Any]:
        if not table_name or not isinstance(table_name, str):
            raise ValueError("table_name must be a non-empty string.")
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", table_name):
            raise ValueError("table_name may only contain letters, numbers, underscore, and dash.")
        if not isinstance(fields, dict) or not fields:
            raise ValueError("fields must be a non-empty dictionary.")
        if table_exists(self.base_path, table_name):
            raise ValueError(f"Table '{table_name}' already exists.")
        if vector_field is not None and vector_field not in fields:
            raise ValueError("vector_field must be one of the schema field names.")

        embedding_dim = getattr(self.embedder, "dimension", None) if vector_field else None
        if vector_field and (not isinstance(embedding_dim, int) or embedding_dim <= 0):
            raise ValueError("Embedder must expose a positive integer 'dimension' attribute when vector_field is enabled.")

        schema = {
            "table_name": table_name,
            "fields": fields,
            "vector_field": vector_field,
            "embedding_dim": embedding_dim,
            "version": 1,
        }
        create_table_files(self.base_path, table_name, schema, secure_permissions=self.secure_permissions)
        return {"ok": True, "table": table_name, "vector_field": vector_field}

    def insert(self, table_name: str, record: Dict[str, Any], record_id: Optional[str] = None) -> Dict[str, Any]:
        schema = load_schema(self.base_path, table_name)
        fields = schema["fields"]

        if not isinstance(record, dict):
            raise ValueError("record must be a dictionary.")

        for field_name in fields:
            if field_name not in record:
                raise ValueError(f"Missing field '{field_name}' in record.")

        rid = record_id or str(uuid.uuid4())
        stored = {"_id": rid, **record}
        append_record(self.base_path, table_name, stored, secure_permissions=self.secure_permissions)

        vector_field = schema.get("vector_field")
        if vector_field:
            value = record.get(vector_field)
            if not isinstance(value, str):
                raise ValueError(f"vector_field '{vector_field}' must contain string data for embedding.")
            embedding = self.embedder.encode(value).astype(np.float32)
            embedding_dim = schema.get("embedding_dim")
            if embedding_dim is None:
                embedding_dim = embedding.shape[0]
            if embedding.shape[0] != embedding_dim:
                raise ValueError("Embedding dimension does not match table configuration.")

            append_vector(
                self.base_path,
                table_name,
                rid,
                embedding,
                secure_permissions=self.secure_permissions,
            )

        return {"ok": True, "id": rid}

    def find(self, table_name: str) -> QueryBuilder:
        """
        Start building a query. Use this to access the fluent query API.

        Example:
            results = db.find('users').where('age', '>', 18).select('name', 'email').execute()
        """
        return QueryBuilder(self, table_name)

    def query(
        self,
        table_name: str,
        conditions: Optional[Dict[str, Any]] = None,
        text_query: Optional[str] = None,
        text_fields: Optional[Sequence[str]] = None,
        case_sensitive: bool = False,
        vector_query: Optional[str] = None,
        top_k: int = 5,
        min_score: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        schema = load_schema(self.base_path, table_name)
        rows = read_all_records(self.base_path, table_name)

        if conditions:
            rows = [r for r in rows if self._record_matches(r, conditions)]

        if text_query is not None:
            rows = self._text_filter_rows(rows, text_query, text_fields=text_fields, case_sensitive=case_sensitive)

        if vector_query is None:
            return [{"id": row["_id"], "score": None, "record": row} for row in rows]

        vector_field = schema.get("vector_field")
        if not vector_field:
            raise ValueError(f"Table '{table_name}' is not configured for vector search.")
        if not isinstance(vector_query, str) or not vector_query.strip():
            raise ValueError("vector_query must be a non-empty string.")

        embedding_dim = schema.get("embedding_dim")
        ids, vectors = load_vectors(self.base_path, table_name, dimension=embedding_dim)
        if vectors is None or len(ids) == 0:
            return []

        query_vec = self.embedder.encode(vector_query).astype(np.float32)
        if query_vec.shape[0] != vectors.shape[1]:
            raise ValueError("Query embedding dimension does not match stored vectors.")

        scores = self._cosine_scores(vectors, query_vec)
        by_id = {row["_id"]: row for row in rows}

        ranked = []
        for idx, rid in enumerate(ids):
            row = by_id.get(rid)
            if row is None:
                continue
            score = float(scores[idx])
            if min_score is not None and score < min_score:
                continue
            ranked.append({"id": rid, "score": score, "record": row})

        ranked.sort(key=lambda x: x["score"], reverse=True)
        return ranked[:top_k]

    @staticmethod
    def _record_matches(record: Dict[str, Any], conditions: Dict[str, Any]) -> bool:
        for key, expected in conditions.items():
            if record.get(key) != expected:
                return False
        return True

    @staticmethod
    def _text_filter_rows(
        rows: List[Dict[str, Any]],
        text_query: str,
        text_fields: Optional[Sequence[str]] = None,
        case_sensitive: bool = False,
    ) -> List[Dict[str, Any]]:
        if not isinstance(text_query, str) or not text_query.strip():
            raise ValueError("text_query must be a non-empty string when provided.")

        query = text_query if case_sensitive else text_query.lower()
        selected_fields = list(text_fields) if text_fields is not None else None

        out: List[Dict[str, Any]] = []
        for row in rows:
            field_names = selected_fields or [k for k in row.keys() if k != "_id"]
            haystack_parts: List[str] = []
            for field_name in field_names:
                value = row.get(field_name)
                if isinstance(value, str):
                    haystack_parts.append(value)
            haystack = " ".join(haystack_parts)
            haystack = haystack if case_sensitive else haystack.lower()
            if query in haystack:
                out.append(row)
        return out

    @staticmethod
    def _cosine_scores(matrix: np.ndarray, query_vector: np.ndarray) -> np.ndarray:
        matrix_norm = np.linalg.norm(matrix, axis=1)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return np.zeros(matrix.shape[0], dtype=np.float32)

        denom = matrix_norm * query_norm
        denom = np.where(denom == 0, 1e-12, denom)
        return (matrix @ query_vector) / denom
