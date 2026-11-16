import ingest


def test_build_insert_has_one_placeholder_per_column():
    columns = ["a", "b", "c"]
    
    sql = ingest.build_insert("t", columns)
    
    assert sql == "INSERT INTO t (a, b, c) VALUES (%s, %s, %s)"