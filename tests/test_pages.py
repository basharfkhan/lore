from lore.ingest.pages import _ocr_lines


def _data(rows):
    keys = ["text", "conf", "block_num", "par_num", "line_num"]
    return {k: [row[i] for row in rows] for i, k in enumerate(keys)}


def test_ocr_lines_rebuilds_lines_and_paragraphs():
    data = _data([
        ("", -1, 1, 0, 0),  # layout rows carry no word and conf -1
        ("Board", 96, 1, 1, 1),
        ("findings", 90, 1, 1, 1),
        ("continued", 94, 1, 1, 2),
        ("Recommendations", 88, 2, 1, 1),
    ])
    text, conf = _ocr_lines(data)
    assert text == "Board findings\ncontinued\n\nRecommendations"
    assert conf == 92.0


def test_ocr_lines_on_empty_page():
    assert _ocr_lines(_data([("", -1, 1, 0, 0), ("  ", 95, 1, 1, 1)])) == ("", None)
