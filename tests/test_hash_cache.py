from gtd.hash_cache import HashCache


def test_get_returns_none_when_no_file(tmp_path):
    cache = HashCache(tmp_path / "hash")
    assert cache.get() is None


def test_set_then_get_round_trips(tmp_path):
    cache = HashCache(tmp_path / "hash")
    cache.set("abc123")
    assert cache.get() == "abc123"


def test_set_overwrites_previous_hash(tmp_path):
    cache = HashCache(tmp_path / "hash")
    cache.set("old")
    cache.set("new")
    assert cache.get() == "new"


def test_set_creates_parent_directories(tmp_path):
    cache = HashCache(tmp_path / "nested" / "hash")
    cache.set("abc123")
    assert cache.get() == "abc123"
