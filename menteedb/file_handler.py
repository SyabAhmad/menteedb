from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def ensure_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def table_dir(base_path: Path, table_name: str) -> Path:
    return base_path / table_name


def schema_path(base_path: Path, table_name: str) -> Path:
    return table_dir(base_path, table_name) / "schema.json"


def records_path(base_path: Path, table_name: str) -> Path:
    return table_dir(base_path, table_name) / "records.jsonl"


def vectors_path(base_path: Path, table_name: str) -> Path:
    return table_dir(base_path, table_name) / "vectors.npz"


def vectors_bin_path(base_path: Path, table_name: str) -> Path:
    return table_dir(base_path, table_name) / "vectors.f32"


def vector_ids_path(base_path: Path, table_name: str) -> Path:
    return table_dir(base_path, table_name) / "vector_ids.jsonl"


def _apply_private_permissions(path: Path, is_dir: bool) -> None:
    # Best effort only. On Windows, chmod is limited and ACLs are the real control.
    try:
        os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass


def table_exists(base_path: Path, table_name: str) -> bool:
    return schema_path(base_path, table_name).exists()


def create_table_files(base_path: Path, table_name: str, schema: Dict[str, Any], secure_permissions: bool = True) -> None:
    tdir = table_dir(base_path, table_name)
    ensure_path(tdir)

    spath = schema_path(base_path, table_name)
    rpath = records_path(base_path, table_name)

    with spath.open("w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=True, indent=2)

    if not rpath.exists():
        rpath.touch()

    if secure_permissions:
        _apply_private_permissions(tdir, is_dir=True)
        _apply_private_permissions(spath, is_dir=False)
        _apply_private_permissions(rpath, is_dir=False)


def load_schema(base_path: Path, table_name: str) -> Dict[str, Any]:
    spath = schema_path(base_path, table_name)
    if not spath.exists():
        raise ValueError(f"Table '{table_name}' does not exist.")

    with spath.open("r", encoding="utf-8") as f:
        return json.load(f)


def append_record(base_path: Path, table_name: str, record: Dict[str, Any], secure_permissions: bool = True) -> None:
    rpath = records_path(base_path, table_name)
    with rpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")
    if secure_permissions:
        _apply_private_permissions(rpath, is_dir=False)


def read_all_records(base_path: Path, table_name: str) -> List[Dict[str, Any]]:
    rpath = records_path(base_path, table_name)
    if not rpath.exists():
        return []

    items: List[Dict[str, Any]] = []
    with rpath.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def append_vector(
    base_path: Path,
    table_name: str,
    record_id: str,
    vector: np.ndarray,
    secure_permissions: bool = True,
) -> None:
    id_path = vector_ids_path(base_path, table_name)
    bin_path = vectors_bin_path(base_path, table_name)

    with id_path.open("a", encoding="utf-8") as idf:
        idf.write(json.dumps(record_id, ensure_ascii=True) + "\n")

    vec = vector.astype(np.float32, copy=False)
    with bin_path.open("ab") as vf:
        vec.tofile(vf)

    if secure_permissions:
        _apply_private_permissions(id_path, is_dir=False)
        _apply_private_permissions(bin_path, is_dir=False)


def load_vectors(base_path: Path, table_name: str, dimension: Optional[int] = None) -> Tuple[List[str], Optional[np.ndarray]]:
    # Backward compatibility with the initial compressed storage format.
    legacy_vpath = vectors_path(base_path, table_name)
    if legacy_vpath.exists():
        data = np.load(legacy_vpath, allow_pickle=True)
        ids = data["ids"].tolist()
        vectors = data["vectors"]
        return ids, vectors

    id_path = vector_ids_path(base_path, table_name)
    bin_path = vectors_bin_path(base_path, table_name)
    if not id_path.exists() or not bin_path.exists():
        return [], None

    ids: List[str] = []
    with id_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ids.append(json.loads(line))

    raw = np.fromfile(bin_path, dtype=np.float32)
    if not ids:
        return [], None
    if dimension is None:
        raise ValueError("dimension is required for binary vector loading.")

    expected = len(ids) * dimension
    if raw.size != expected:
        raise ValueError(
            f"Corrupt vector storage for table '{table_name}': expected {expected} float32 values, found {raw.size}."
        )

    return ids, raw.reshape(len(ids), dimension)
