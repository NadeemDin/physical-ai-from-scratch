from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

import ingest


@dataclass
class FakeMsg:
    topic: str
    payload: bytes


class FakeConn:
    """Records every execute() call instead of running SQL."""

    def __init__(self, equipment_id=1):
        self.equipment_id = equipment_id
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return self

    def fetchone(self):
        if self.equipment_id is None:
            return None
        return (self.equipment_id,)


@pytest.fixture
def fake_conn(monkeypatch):
    fake = FakeConn()
    monkeypatch.setattr(ingest, "conn", fake)
    monkeypatch.setattr(ingest, "equipment_ids", {})
    return fake


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (["a"], "INSERT INTO t (a) VALUES (%s)"),
        (["a", "b"], "INSERT INTO t (a, b) VALUES (%s, %s)"),
        (["a", "b", "c"], "INSERT INTO t (a, b, c) VALUES (%s, %s, %s)"),
    ],
)
def test_build_insert_has_one_placeholder_per_column(columns, expected):
    sql = ingest.build_insert("t", columns)

    assert sql == expected


def test_good_message_is_stored(fake_conn):
    msg = FakeMsg("rig/fan1/features", b'{"duty": 40, "rpm": 1440}')
    ts = datetime(2026, 11, 18, tzinfo=UTC)

    ingest.handle_message(msg, ts)

    assert len(fake_conn.calls) == 2
    sql, values = fake_conn.calls[1]
    assert sql == ingest.INSERT_READING_SQL
    assert len(values) == 17
    assert values[0] == ts
    assert values[1] == 1


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (b"not json", "JSONDecodeError"),
        (b"\xff", "UnicodeDecodeError"),
        (b"42", "NotAnObject"),
    ],
)
def test_bad_message_is_rejected(fake_conn, payload, expected_error):
    msg = FakeMsg("rig/fan1/features", payload)
    ts = datetime(2026, 11, 19, tzinfo=UTC)

    ingest.handle_message(msg, ts)

    assert len(fake_conn.calls) == 1
    sql, values = fake_conn.calls[0]
    assert sql == ingest.INSERT_REJECT_SQL
    assert values[3] == expected_error


def test_equipment_is_unknown(monkeypatch):
    fake = FakeConn(equipment_id=None)
    monkeypatch.setattr(ingest, "conn", fake)
    monkeypatch.setattr(ingest, "equipment_ids", {})

    msg = FakeMsg("rig/fan1/features", b'{"duty": 40, "rpm": 1440}')
    ts = datetime(2026, 11, 19, tzinfo=UTC)

    ingest.handle_message(msg, ts)

    assert len(fake.calls) == 2
    sql, values = fake.calls[1]
    assert sql == ingest.INSERT_REJECT_SQL
    assert values[3] == "UnknownEquipment"


def test_select_skipped_when_equipment_in_cache(fake_conn):

    msg = FakeMsg("rig/fan1/features", b'{"duty": 40, "rpm": 1440}')
    ts = datetime(2026, 11, 19, tzinfo=UTC)

    ingest.handle_message(msg, ts)
    ingest.handle_message(msg, ts)

    assert len(fake_conn.calls) == 3

    for sql, _values in fake_conn.calls[1:3]:
        assert sql == ingest.INSERT_READING_SQL
