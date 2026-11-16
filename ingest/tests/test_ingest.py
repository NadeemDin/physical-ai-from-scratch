import pytest
import ingest


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
