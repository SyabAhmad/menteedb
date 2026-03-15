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
