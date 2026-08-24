from tibero_doc.client import upload_timeout


def test_upload_timeout_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TIBERO_DOC_HTTP_TIMEOUT_SECONDS", raising=False)
    assert upload_timeout() is None


def test_upload_timeout_accepts_configuration(monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_HTTP_TIMEOUT_SECONDS", "900")
    timeout = upload_timeout()
    assert timeout.read == 900.0
    assert timeout.write == 900.0


def test_upload_timeout_accepts_zero_as_disabled(monkeypatch):
    monkeypatch.setenv("TIBERO_DOC_HTTP_TIMEOUT_SECONDS", "0")
    assert upload_timeout() is None
