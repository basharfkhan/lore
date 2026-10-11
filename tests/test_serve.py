from lore.serve.budget import FileSpend, RateLimiter


def test_spend_accumulates_per_day(tmp_path):
    store = FileSpend(tmp_path / "spend.json")
    assert store.spent_today() == 0.0
    store.add(0.12)
    store.add(0.30)
    assert store.spent_today() == 0.42
    assert FileSpend(tmp_path / "spend.json").spent_today() == 0.42  # survives a restart


def test_rate_limiter_uses_a_rolling_window():
    limiter = RateLimiter(limit=2, window=60)
    assert limiter.allow("a", now=0)
    assert limiter.allow("a", now=10)
    assert not limiter.allow("a", now=20)
    assert limiter.allow("b", now=20)  # other visitors are unaffected
    assert limiter.allow("a", now=65)  # the first hit has aged out
