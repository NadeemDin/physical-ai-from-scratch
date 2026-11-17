from dataclasses import dataclass

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
