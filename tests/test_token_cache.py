from gtd.token_cache import TokenCache


def test_get_returns_none_when_no_file(tmp_path):
    cache = TokenCache(tmp_path / "tokens")
    assert cache.get("client-id") is None


def test_set_then_get_round_trips(tmp_path):
    cache = TokenCache(tmp_path / "tokens")
    cache.set("client-id", "a-refresh-token")
    assert cache.get("client-id") == "a-refresh-token"


def test_set_creates_one_file_per_client_id(tmp_path):
    directory = tmp_path / "tokens"
    cache = TokenCache(directory)
    cache.set("client-a", "token-a")
    cache.set("client-b", "token-b")
    assert (directory / "client-a").read_text() == "token-a"
    assert (directory / "client-b").read_text() == "token-b"


def test_next_to_config_uses_sibling_tokens_directory(tmp_path):
    config_path = tmp_path / "config.yaml"
    TokenCache(tmp_path / "tokens").set("client-id", "a-refresh-token")

    cache = TokenCache.next_to_config(config_path)

    assert cache.get("client-id") == "a-refresh-token"
