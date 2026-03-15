# menteedb

menteedb is a lightweight local Python library that combines table-like records with optional vector similarity search.

## Features

- Define tables with a schema.
- Insert structured records.
- Enable vector search on one text field per table.
- Add fast text contains search per table.
- Query by field filters and/or semantic similarity.
- Persist data locally with append-only files for speed.

## Quick Start

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

results = db.query("notes", vector_query="local vector tools", top_k=2)
for item in results:
    print(item["score"], item["record"])

text_hits = db.query("notes", text_query="local", text_fields=["body"])
print(text_hits)
```

## Query Modes

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
- `./data/notes/records.jsonl`
- `./data/notes/vector_ids.jsonl`
- `./data/notes/vectors.f32`

This is local file-based storage. It is not publicly exposed over the network, but anyone with local filesystem access to this folder can read it.

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
