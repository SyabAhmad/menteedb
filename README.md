# menteedb

menteedb is a lightweight local Python library that combines table-like records with optional vector similarity search, fluent query API, and optional encryption.

## Features

- Define tables with a schema.
- Insert structured records.
- **Fluent Query Builder** - no SQL, pure Python with field selection, filtering, and conditions.
- Optional **AES-256-GCM encryption** with automatic key derivation.
- **Binary MessagePack format** - ~50% smaller files than JSON, automatic fallback to JSON.
- Enable vector search on one text field per table.
- Fast text contains search per table.
- Query by field filters and/or semantic similarity.
- Persist data locally with append-only files for speed.

## Quick Start

### Basic Usage

```python
from menteedb import MenteeDB

db = MenteeDB(base_path="./data")

db.create_table(
    table_name="notes",
    fields={"title": "str", "body": "str", "tag": "str"},
    vector_field="body",
)

db.insert("notes", {"title": "First", "body": "Vector databases are useful.", "tag": "ml"})
db.insert("notes", {"title": "Second", "body": "I enjoy local-first tools.", "tag": "dev"})

# Fluent query API
results = db.find("notes").where("tag", "==", "ml").select("title", "body").execute()
print(results)
```

### Encrypted Storage (Optional)

```python
from menteedb import MenteeDB

# Enable encryption
db = MenteeDB(
    base_path="./secure_data",
    use_encryption=True,
    encryption_key="my_secure_password"
)

db.create_table("secrets", fields={"key": "str", "value": "str"})
db.insert("secrets", {"key": "api_token", "value": "sk_live_..."})

# Query encrypted data transparently
results = db.find("secrets").where("key", "==", "api_token").execute()
```

## Query API (No SQL!)

Instead of SQL syntax, use Python method chaining:

```python
# SELECT name, email FROM users WHERE age > 25 AND city = 'NYC'
results = (
    db.find('users')
    .where('age', '>', 25)
    .where('city', '==', 'NYC')
    .select('name', 'email')
    .execute()
)
```

### Supported Operators

- Comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Collection: `in`
- String: `contains`

See [QUERY_GUIDE.md](QUERY_GUIDE.md) for complete examples.

## Legacy Query Modes

The original `db.query()` method still works:

- Filter-only:
  - `db.query("notes", conditions={"tag": "ml"})`
- Text contains search:
  - `db.query("notes", text_query="vector", text_fields=["title", "body"])`
- Vector-only:
  - `db.query("notes", vector_query="your text")`
- Hybrid (filter + vector):
  - `db.query("notes", conditions={"tag": "dev"}, vector_query="local tools")`

## Storage Layout

For `base_path="./data"` and table `notes`, menteedb stores:

- `./data/notes/schema.json`
- `./data/notes/records.jsonl` - **Binary MessagePack format** (compact, ~50% smaller than JSON)
- `./data/notes/vector_ids.jsonl`
- `./data/notes/vectors.f32`

### Storage Features

- **MessagePack Binary Format:** Compact and fast serialization (~50% size reduction vs JSON)
- **Optional Encryption:** Enable AES-256-GCM encryption to protect sensitive data on disk
- **Automatic Format Detection:** Seamlessly reads legacy JSON data and writes new data as MessagePack
- **Append-Only Design:** Fast sequential writes with minimal overhead

This is local file-based storage. It is not publicly exposed over the network, but anyone with local filesystem access to this folder can read it. **Enable encryption for sensitive data.**

## Encryption

Protect sensitive data with AES-256-GCM encryption:

```python
from menteedb import MenteeDB

db = MenteeDB(
    base_path="./secure",
    use_encryption=True,
    encryption_key="your_secure_password"
)
```

**Benefits:**

- ✅ AES-256-GCM authenticated encryption
- ✅ Automatic key derivation (PBKDF2-HMAC-SHA256)
- ✅ Transparent to your code
- ✅ ~50% disk savings with MessagePack

See [ENCRYPTION_GUIDE.md](ENCRYPTION_GUIDE.md) for security best practices and examples.

## Privacy and Permissions

- By default, `MenteeDB(..., secure_permissions=True)` applies best-effort private permissions (`700` for table folders, `600` for files).
- On Windows, real privacy is controlled by NTFS ACLs; chmod behavior is limited.

## Testing

Run locally:

```bash
pip install .[dev]
pytest -q
```

## CI/CD to PyPI

Workflow file: `.github/workflows/pypi-publish.yml`

- Runs tests on pushes to `main`, tags (`v*`), and releases.
- Publishes to PyPI on tag push (`v*`) or GitHub Release publish.
- Uses trusted publishing via GitHub OIDC.

## Notes

- This initial version supports one vector field per table.
- Default embeddings use a deterministic local hashing embedder with no external model download.
