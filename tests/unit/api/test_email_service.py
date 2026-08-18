from services.api.email_service import send_invitation


class FakeSMTP:
    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.tls = False
        self.credentials = None
        self.message = None
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def starttls(self):
        self.tls = True

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.message = message


def test_invitation_email_uses_tls_auth_and_contains_join_url(monkeypatch):
    FakeSMTP.instances.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("SMTP_USERNAME", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "invite@example.test")
    monkeypatch.setattr("services.api.email_service.smtplib.SMTP", FakeSMTP)

    assert send_invitation("user@example.test", "https://docs.example.test/join?token=abc")
    smtp = FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.test", 2525)
    assert smtp.tls is True
    assert smtp.credentials == ("mailer", "secret")
    assert smtp.message["To"] == "user@example.test"
    assert "https://docs.example.test/join?token=abc" in smtp.message.get_content()


def test_invitation_email_is_disabled_without_smtp_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert send_invitation("user@example.test", "https://example.test/join") is False
