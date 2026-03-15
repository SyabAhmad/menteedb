from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import msgpack
import numpy as np
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class StorageFormat:
    """Encryption and format configuration for storage."""

    def __init__(self, use_encryption: bool = False, encryption_key: Optional[str] = None):
        """
        Initialize storage format.

        Args:
            use_encryption: Enable AES-256-GCM encryption
            encryption_key: Password for encryption (min 8 chars). If None, a default is used.
        """
        self.use_encryption = use_encryption
        self._encryption_key = encryption_key

    def _derive_key(self) -> bytes:
        """Derive a 32-byte AES key from password using PBKDF2HMAC."""
        password = (self._encryption_key or "default").encode()
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"menteedb_salt", iterations=100000)
        return kdf.derive(password)

    def encrypt_data(self, data: bytes) -> bytes:
        """Encrypt data with AES-256-GCM, return: IV + ciphertext + tag."""
        if not self.use_encryption:
            return data

        import os

        key = self._derive_key()
        iv = os.urandom(12)  # 96-bit IV for GCM
        cipher = AESGCM(key)
        ciphertext = cipher.encrypt(iv, data, None)
        return iv + ciphertext

    def decrypt_data(self, encrypted: bytes) -> bytes:
        """Decrypt AES-256-GCM data. Expects: IV + ciphertext + tag."""
        if not self.use_encryption:
            return encrypted

        key = self._derive_key()
        iv = encrypted[:12]
        ciphertext_with_tag = encrypted[12:]
        cipher = AESGCM(key)
        return cipher.decrypt(iv, ciphertext_with_tag, None)


# Global storage format (can be configured per MenteeDB instance)
_global_storage_format = StorageFormat(use_encryption=False)


def set_storage_format(use_encryption: bool = False, encryption_key: Optional[str] = None) -> None:
    """Configure global storage format for all operations."""
    global _global_storage_format
    _global_storage_format = StorageFormat(use_encryption=use_encryption, encryption_key=encryption_key)


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
    
    # Serialize record to MessagePack (compact binary format)
    data = msgpack.packb(record, use_bin_type=True)
    
    # Encrypt if enabled
    data = _global_storage_format.encrypt_data(data)
    
    # Append as binary with length prefix for easy chunking
    with rpath.open("ab") as f:
        f.write(len(data).to_bytes(4, byteorder="big"))
        f.write(data)
    
    if secure_permissions:
        _apply_private_permissions(rpath, is_dir=False)


def read_all_records(base_path: Path, table_name: str) -> List[Dict[str, Any]]:
    rpath = records_path(base_path, table_name)
    if not rpath.exists():
        return []

    items: List[Dict[str, Any]] = []
    
    # Check if file has the new binary format or old JSON format
    try:
        with rpath.open("rb") as f:
            content = f.read()
            if not content:
                return []
        
        # Try reading as new binary format (length-prefixed msgpack)
        offset = 0
        while offset < len(content):
            if offset + 4 > len(content):
                break
            length = int.from_bytes(content[offset : offset + 4], byteorder="big")
            offset += 4
            
            if offset + length > len(content):
                break
            
            data = content[offset : offset + length]
            offset += length
            
            # Decrypt if enabled
            data = _global_storage_format.decrypt_data(data)
            
            # Deserialize from MessagePack
            record = msgpack.unpackb(data, raw=False)
            items.append(record)
        
        return items
    except Exception:
        pass
    
    # Fallback: try reading as old JSON format for backward compatibility
    try:
        with rpath.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
    except Exception:
        pass
    
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
