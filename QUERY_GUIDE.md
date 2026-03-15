# QueryBuilder Guide - SQL-Free Querying 🚀

MenteeDB now features a fluent, Pythonic query API with field selection and filtering—no SQL needed!

## Basic Usage

### Select Specific Fields

Get only the data you need (like `SELECT age, name FROM users`):

```python
from menteedb import MenteeDB

db = MenteeDB()

# Select specific fields
results = db.find('users').select('name', 'age', 'email').execute()

for result in results:
    print(f"{result['id']}: {result['data']}")
    # Output: {"name": "Alice", "age": 30, "email": "alice@example.com"}
```

### Filter with Conditions (WHERE Clauses)

Add conditions without SQL syntax:

```python
# Get users older than 25
results = db.find('users').where('age', '>', 25).execute()

# Get users from specific cities
results = db.find('users').where('city', 'in', ['NYC', 'LA']).execute()

# Get users NOT from NYC
results = db.find('users').where('city', '!=', 'NYC').execute()
```

### Combine Conditions & Field Selection

Chain multiple conditions together (AND logic):

```python
results = (
    db.find('users')
    .where('age', '>', 25)
    .where('city', '==', 'NYC')
    .select('name', 'email')
    .execute()
)
```

## Supported Operators

| Operator   | Example                                         | Description      |
| ---------- | ----------------------------------------------- | ---------------- |
| `==`       | `.where('status', '==', 'active')`              | Equals           |
| `!=`       | `.where('status', '!=', 'inactive')`            | Not equals       |
| `>`        | `.where('age', '>', 25)`                        | Greater than     |
| `<`        | `.where('age', '<', 65)`                        | Less than        |
| `>=`       | `.where('age', '>=', 18)`                       | Greater or equal |
| `<=`       | `.where('age', '<=', 100)`                      | Less or equal    |
| `in`       | `.where('status', 'in', ['active', 'pending'])` | In list          |
| `contains` | `.where('name', 'contains', 'John')`            | String contains  |

## Text Search

Search across fields without exact matches:

```python
# Search for text in specific fields
results = db.find('posts').search('Python', in_fields=['title', 'body']).execute()

# Case-insensitive (default)
results = db.find('posts').search('python', in_fields=['title']).execute()

# Case-sensitive search
results = db.find('posts').search('Python', in_fields=['title'], case_sensitive=True).execute()
```

Or use the `contains` operator for more control:

```python
# Find posts with 'development' in the body
results = db.find('posts').where('body', 'contains', 'development').execute()
```

## Vector Search

Search by semantic similarity:

```python
# Find similar documents to a query
results = (
    db.find('documents')
    .vector_search('machine learning algorithms', top_k=10, min_score=0.7)
    .execute()
)
```

## Complete Example

```python
from menteedb import MenteeDB

# Create database
db = MenteeDB('./my_data')

# Create a users table
db.create_table(
    'users',
    fields={'name': 'str', 'age': 'int', 'city': 'str', 'email': 'str'}
)

# Insert some data
db.insert('users', {'name': 'Alice', 'age': 30, 'city': 'NYC', 'email': 'alice@ex.com'})
db.insert('users', {'name': 'Bob', 'age': 25, 'city': 'LA', 'email': 'bob@ex.com'})
db.insert('users', {'name': 'Charlie', 'age': 35, 'city': 'NYC', 'email': 'charlie@ex.com'})

# Query: Get names and emails of people 25+ from NYC
results = (
    db.find('users')
    .where('age', '>=', 25)
    .where('city', '==', 'NYC')
    .select('name', 'email')
    .execute()
)

print(results)
# [
#   {'id': 'uuid1', 'data': {'name': 'Alice', 'email': 'alice@ex.com'}},
#   {'id': 'uuid3', 'data': {'name': 'Charlie', 'email': 'charlie@ex.com'}}
# ]
```

## API Reference

### `db.find(table_name: str) -> QueryBuilder`

Start a new query for a table.

### `.select(*fields: str) -> QueryBuilder`

Select specific fields to return. If not called, all fields are returned.

### `.where(field: str, operator: str, value: Any) -> QueryBuilder`

Filter records by a condition. Chain multiple `.where()` calls for AND logic.

### `.search(query: str, in_fields: List[str] | None, case_sensitive: bool) -> QueryBuilder`

Text search across fields.

### `.vector_search(query: str, top_k: int, min_score: float | None) -> QueryBuilder`

Semantic similarity search (requires a vector_field in table schema).

### `.execute() -> List[Dict]`

Execute the query and return results as a list of records.

Each result has:

- `id`: Record ID
- `data`: Dictionary of field values

---

**No SQL. Pure Python. Intuitive. 🐍**
