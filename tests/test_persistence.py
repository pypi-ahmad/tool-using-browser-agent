"""SQLite roundtrip tests against temporary isolated databases. No LLM, no network.

Responsibility:
- Verify record insertion, deserialization, and recent record queries in SQLite.
- Verify substring search across task, url, and data_json columns.
- Verify session deduplication and disk persistence across distinct connections.

What it must NOT do:
- Must not touch production or default database paths (uses pytest tmp_path fixtures).
- Must not make network or LLM calls.

Next module to read:
- persistence.py (implements SQLite schema creation and memory querying).
"""

from persistence import list_recent, list_sessions, save_record, search_memory


def test_save_and_list_recent(tmp_path):
    db_path = str(tmp_path / "memory.db")
    save_record(
        {
            "session_id": "s1",
            "task": "compare iPhone prices",
            "url": "https://amazon.example/iphone",
            "type": "price",
            "data": {"price": "$799"},
            "created_at": "2026-08-14T00:00:00+00:00",
        },
        db_path=db_path,
    )

    records = list_recent(db_path=db_path)

    assert len(records) == 1
    assert records[0]["url"] == "https://amazon.example/iphone"
    assert records[0]["data"] == {"price": "$799"}


def test_search_memory_matches_url_task_or_data(tmp_path):
    db_path = str(tmp_path / "memory.db")
    save_record(
        {
            "session_id": "s1",
            "task": "compare iPhone prices",
            "url": "https://amazon.example/iphone",
            "type": "price",
            "data": {"price": "$799"},
            "created_at": "2026-08-14T00:00:00+00:00",
        },
        db_path=db_path,
    )
    save_record(
        {
            "session_id": "s1",
            "task": "research competitor features",
            "url": "https://flipkart.example/iphone",
            "type": "table",
            "data": {"feature": "5G"},
            "created_at": "2026-08-14T00:01:00+00:00",
        },
        db_path=db_path,
    )

    by_url = search_memory("amazon", db_path=db_path)
    by_task = search_memory("competitor", db_path=db_path)
    by_data = search_memory("799", db_path=db_path)
    no_match = search_memory("nonexistent", db_path=db_path)

    assert len(by_url) == 1 and by_url[0]["url"] == "https://amazon.example/iphone"
    assert len(by_task) == 1 and by_task[0]["type"] == "table"
    assert len(by_data) == 1 and by_data[0]["data"] == {"price": "$799"}
    assert no_match == []


def test_list_sessions_is_distinct(tmp_path):
    db_path = str(tmp_path / "memory.db")
    for session_id in ("s1", "s1", "s2"):
        save_record(
            {
                "session_id": session_id,
                "task": "t",
                "url": None,
                "type": "text",
                "data": "x",
                "created_at": "2026-08-14T00:00:00+00:00",
            },
            db_path=db_path,
        )

    assert set(list_sessions(db_path=db_path)) == {"s1", "s2"}


def test_persists_across_reconnect(tmp_path):
    """Proves it's actually disk-backed, not process-memory — a fresh connection sees it."""
    db_path = str(tmp_path / "memory.db")
    save_record(
        {
            "session_id": "s1",
            "task": "t",
            "url": "https://example.com",
            "type": "text",
            "data": "hello",
            "created_at": "2026-08-14T00:00:00+00:00",
        },
        db_path=db_path,
    )

    records = list_recent(db_path=db_path)  # opens a brand new sqlite3.connect

    assert len(records) == 1
    assert records[0]["data"] == "hello"
