from calcfs_pdf_export.ids import normalize_id, same_id


def test_same_id_numeric() -> None:
    assert same_id(1, 1.0)
    assert same_id("2", 2)
    assert not same_id(1, 3)


def test_normalize_id() -> None:
    assert normalize_id(5.0) == 5
    assert normalize_id("7") == 7
