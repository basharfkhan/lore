from lore.data.reports import load_reports


def test_manifest_is_consistent():
    reports = load_reports()
    assert len(reports) >= 15
    assert all(r.url.startswith("https://") for r in reports)
    assert all(r.mishap_date <= r.report_date for r in reports)
