"""PostgresStore JSON/JSONB decode.

asyncpg returns a JSONB column as a raw str (no type codec is registered), so
the read side must json.loads it — mirroring SQLite's json.loads and the write
side's json.dumps. The old `dict(row["final_soul_vectors"] or {})` raised
ValueError on the (non-empty) JSON string, crashing get_dead_threads /
get_last_ancestor — so on a Postgres backend no new run could start after the
first death (kernel.initialize reads both). _as_dict decodes defensively.
"""

from __future__ import annotations

from app.db.postgres_store import _as_dict


class TestAsDict:
    def test_empty_json_object_string(self):
        # The DEFAULT '{}'::jsonb comes back as the string "{}" — dict("{}") raised.
        assert _as_dict("{}") == {}

    def test_populated_json_object_string(self):
        assert _as_dict('{"metis": 1.0, "bia": 8.0}') == {"metis": 1.0, "bia": 8.0}

    def test_none_and_empty_become_empty_dict(self):
        assert _as_dict(None) == {}
        assert _as_dict("") == {}

    def test_already_decoded_dict_passes_through(self):
        # Defensive: if a jsonb codec is ever registered, asyncpg returns a dict.
        assert _as_dict({"kleos": 5.0}) == {"kleos": 5.0}
        assert _as_dict({}) == {}
