from runtime.models import RuntimeSession

def test_runtime_session_stores_identity():
    session = RuntimeSession(None, None, None, "https://example.com", "demo")
    assert session.url == "https://example.com"
