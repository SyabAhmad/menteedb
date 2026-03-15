from pathlib import Path

from menteedb import MenteeDB


def test_create_insert_filter_and_text_query(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="notes",
        fields={"title": "str", "body": "str", "tag": "str"},
        vector_field="body",
    )

    db.insert("notes", {"title": "A", "body": "Vector search is local", "tag": "ml"}, record_id="1")
    db.insert("notes", {"title": "B", "body": "Fast tiny library", "tag": "dev"}, record_id="2")

    filtered = db.query("notes", conditions={"tag": "dev"})
    assert len(filtered) == 1
    assert filtered[0]["id"] == "2"

    text_hits = db.query("notes", text_query="tiny", text_fields=["body"])
    assert len(text_hits) == 1
    assert text_hits[0]["id"] == "2"


def test_vector_query_returns_ranked_results(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="docs",
        fields={"title": "str", "body": "str", "tag": "str"},
        vector_field="body",
    )

    db.insert("docs", {"title": "One", "body": "cats and pets", "tag": "a"}, record_id="r1")
    db.insert("docs", {"title": "Two", "body": "dogs and parks", "tag": "b"}, record_id="r2")

    results = db.query("docs", vector_query="pets", top_k=2)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]


def test_rejects_invalid_table_name(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))

    try:
        db.create_table("../../bad", fields={"x": "str"})
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_query_builder_select_fields(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="users",
        fields={"name": "str", "age": "int", "email": "str", "city": "str"},
    )

    db.insert("users", {"name": "Alice", "age": 30, "email": "alice@example.com", "city": "NYC"}, record_id="u1")
    db.insert("users", {"name": "Bob", "age": 25, "email": "bob@example.com", "city": "LA"}, record_id="u2")
    db.insert("users", {"name": "Charlie", "age": 35, "email": "charlie@example.com", "city": "NYC"}, record_id="u3")

    # Select specific fields
    results = db.find("users").select("name", "age").execute()
    assert len(results) == 3
    assert "name" in results[0]["data"]
    assert "age" in results[0]["data"]
    assert "email" not in results[0]["data"]


def test_query_builder_where_conditions(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="users",
        fields={"name": "str", "age": "int", "email": "str", "city": "str"},
    )

    db.insert("users", {"name": "Alice", "age": 30, "email": "alice@example.com", "city": "NYC"}, record_id="u1")
    db.insert("users", {"name": "Bob", "age": 25, "email": "bob@example.com", "city": "LA"}, record_id="u2")
    db.insert("users", {"name": "Charlie", "age": 35, "email": "charlie@example.com", "city": "NYC"}, record_id="u3")

    # Greater than
    results = db.find("users").where("age", ">", 28).execute()
    assert len(results) == 2
    assert results[0]["id"] in ["u1", "u3"]

    # Less than
    results = db.find("users").where("age", "<", 30).execute()
    assert len(results) == 1
    assert results[0]["id"] == "u2"

    # Equals
    results = db.find("users").where("city", "==", "NYC").execute()
    assert len(results) == 2

    # Not equals
    results = db.find("users").where("city", "!=", "NYC").execute()
    assert len(results) == 1

    # In list
    results = db.find("users").where("name", "in", ["Alice", "Bob"]).execute()
    assert len(results) == 2


def test_query_builder_combined_conditions(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="users",
        fields={"name": "str", "age": "int", "email": "str", "city": "str"},
    )

    db.insert("users", {"name": "Alice", "age": 30, "email": "alice@example.com", "city": "NYC"}, record_id="u1")
    db.insert("users", {"name": "Bob", "age": 25, "email": "bob@example.com", "city": "LA"}, record_id="u2")
    db.insert("users", {"name": "Charlie", "age": 35, "email": "charlie@example.com", "city": "NYC"}, record_id="u3")

    # Multiple conditions (AND logic)
    results = (
        db.find("users")
        .where("age", ">", 26)
        .where("city", "==", "NYC")
        .select("name", "age")
        .execute()
    )
    assert len(results) == 2
    for r in results:
        assert r["data"]["age"] > 26
        assert "city" not in r["data"]  # city not selected


def test_query_builder_text_search(tmp_path: Path) -> None:
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="posts",
        fields={"title": "str", "body": "str", "author": "str"},
    )

    db.insert("posts", {"title": "Python Tips", "body": "Learn Python programming", "author": "Alice"}, record_id="p1")
    db.insert("posts", {"title": "JavaScript Guide", "body": "Master JavaScript development", "author": "Bob"}, record_id="p2")
    db.insert("posts", {"title": "Python Advanced", "body": "Advanced Python techniques", "author": "Charlie"}, record_id="p3")

    # Search in specific fields
    results = db.find("posts").search("Python", in_fields=["title", "body"]).execute()
    assert len(results) == 2

    # Search with contains operator
    results = (
        db.find("posts")
        .where("body", "contains", "development")
        .execute()
    )
    assert len(results) == 1
    assert results[0]["id"] == "p2"


def test_encryption_with_default_settings(tmp_path: Path) -> None:
    """Test that encryption works with default key."""
    from menteedb import set_storage_format
    
    # Turn off encryption for unencrypted storage
    set_storage_format(use_encryption=False)
    db = MenteeDB(base_path=str(tmp_path / "unencrypted"))
    db.create_table(
        table_name="users",
        fields={"name": "str", "age": "int"},
    )
    db.insert("users", {"name": "Alice", "age": 30}, record_id="u1")
    
    results = db.find("users").execute()
    assert len(results) == 1
    assert results[0]["data"]["name"] == "Alice"
    
    # Now test with encryption
    set_storage_format(use_encryption=True, encryption_key="my_secret_password")
    db_enc = MenteeDB(base_path=str(tmp_path / "encrypted"))
    db_enc.create_table(
        table_name="users",
        fields={"name": "str", "age": "int"},
    )
    db_enc.insert("users", {"name": "Bob", "age": 25}, record_id="u2")
    
    results = db_enc.find("users").execute()
    assert len(results) == 1
    assert results[0]["data"]["name"] == "Bob"


def test_encryption_persistence(tmp_path: Path) -> None:
    """Test that encrypted data persists and can be decrypted."""
    from menteedb import set_storage_format
    
    db_path = str(tmp_path)
    key = "secure_password_123"
    
    # Create and insert with encryption
    set_storage_format(use_encryption=True, encryption_key=key)
    db = MenteeDB(base_path=db_path)
    db.create_table(
        table_name="secrets",
        fields={"secret": "str", "value": "str"},
    )
    db.insert("secrets", {"secret": "api_key", "value": "sk-1234567890"}, record_id="s1")
    
    results = db.find("secrets").execute()
    assert results[0]["data"]["value"] == "sk-1234567890"
    
    # Reopen with same key
    db2 = MenteeDB(base_path=db_path)
    results2 = db2.find("secrets").execute()
    assert len(results2) == 1
    assert results2[0]["data"]["value"] == "sk-1234567890"


def test_encryption_with_query_builder(tmp_path: Path) -> None:
    """Test query builder works with encrypted storage."""
    from menteedb import set_storage_format
    
    set_storage_format(use_encryption=True, encryption_key="test_key_secure")
    db = MenteeDB(base_path=str(tmp_path))
    db.create_table(
        table_name="employees",
        fields={"name": "str", "salary": "int", "department": "str"},
    )
    
    db.insert("employees", {"name": "Alice", "salary": 60000, "department": "Engineering"}, record_id="e1")
    db.insert("employees", {"name": "Bob", "salary": 55000, "department": "Sales"}, record_id="e2")
    db.insert("employees", {"name": "Charlie", "salary": 65000, "department": "Engineering"}, record_id="e3")
    
    # Complex query with encryption
    results = (
        db.find("employees")
        .where("department", "==", "Engineering")
        .where("salary", ">", 58000)
        .select("name", "salary")
        .execute()
    )
    assert len(results) == 2
    for r in results:
        assert "department" not in r["data"]  # Not selected
        assert "name" in r["data"]
        assert "salary" in r["data"]
