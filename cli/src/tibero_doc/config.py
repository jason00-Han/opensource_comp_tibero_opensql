from __future__ import annotations

import os
import tomllib
from pathlib import Path
from urllib.parse import quote


CONFIG_DIR = Path(os.getenv("TIBERO_DOC_CONFIG_DIR", Path.home() / ".tibero-doc"))
CONFIG_FILE = CONFIG_DIR / "config.toml"
KEYRING_SERVICE = "tibero-doc"
TOKEN_SERVICE = "tibero-doc-access"
REFRESH_SERVICE = "tibero-doc-refresh"

DEFAULT_CONFIG = {
    "api_url": "http://localhost:8000",
    "db_host": "127.0.0.1",
    "db_port": 16432,
    "db_user": "postgres",
    "db_name": "opensql",
    "data_dir": str(CONFIG_DIR / "data"),
    "pipeline_mode": "inline",
    "embedding_provider": "local",
    "embedding_model": "local-hash-384",
    "auth_mode": "required",
}


def load_config() -> dict:
    values = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as stream:
            values.update(tomllib.load(stream))
    return values


def save_config(api_url: str | None = None, **updates) -> dict:
    values = load_config()
    if api_url is not None:
        updates["api_url"] = api_url
    values.update({key: value for key, value in updates.items() if value is not None})
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    lines = []
    for key in DEFAULT_CONFIG:
        value = values[key]
        if isinstance(value, int):
            lines.append(f"{key} = {value}")
        else:
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
    CONFIG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        CONFIG_FILE.chmod(0o600)
    except OSError:
        pass
    return values


def get_api_url() -> str:
    return str(load_config()["api_url"])


def credential_name(config: dict | None = None) -> str:
    values = config or load_config()
    return f"{values['db_user']}@{values['db_host']}:{values['db_port']}"


def save_password(password: str, config: dict | None = None) -> None:
    import keyring

    keyring.set_password(KEYRING_SERVICE, credential_name(config), password)


def load_password(config: dict | None = None) -> str | None:
    from keyring.errors import KeyringError

    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, credential_name(config))
    except (KeyringError, RuntimeError):
        return None


def delete_password(config: dict | None = None) -> None:
    from keyring.errors import KeyringError, PasswordDeleteError

    try:
        import keyring
        keyring.delete_password(KEYRING_SERVICE, credential_name(config))
    except (KeyringError, PasswordDeleteError, RuntimeError):
        pass


def save_access_token(token: str, api_url: str | None = None) -> None:
    import keyring
    keyring.set_password(TOKEN_SERVICE, api_url or get_api_url(), token)


def load_access_token(api_url: str | None = None) -> str | None:
    if os.getenv("TIBERO_DOC_ACCESS_TOKEN"):
        return os.environ["TIBERO_DOC_ACCESS_TOKEN"]
    try:
        import keyring
        return keyring.get_password(TOKEN_SERVICE, api_url or get_api_url())
    except Exception:
        return None


def delete_access_token(api_url: str | None = None) -> None:
    try:
        import keyring
        keyring.delete_password(TOKEN_SERVICE, api_url or get_api_url())
    except Exception:
        pass


def save_refresh_token(token: str, api_url: str | None = None) -> None:
    import keyring
    keyring.set_password(REFRESH_SERVICE, api_url or get_api_url(), token)


def load_refresh_token(api_url: str | None = None) -> str | None:
    try:
        import keyring
        return keyring.get_password(REFRESH_SERVICE, api_url or get_api_url())
    except Exception:
        return None


def build_dsn(password: str, config: dict | None = None) -> str:
    values = config or load_config()
    return (
        f"postgresql://{quote(str(values['db_user']), safe='')}:{quote(password, safe='')}"
        f"@{values['db_host']}:{values['db_port']}/{values['db_name']}"
    )


def runtime_environment(password: str, config: dict | None = None) -> dict[str, str]:
    values = config or load_config()
    return {
        "TIBERO_DOC_DSN": build_dsn(password, values),
        "TIBERO_DOC_DATA_DIR": str(Path(values["data_dir"]).expanduser()),
        "PIPELINE_MODE": str(values["pipeline_mode"]),
        "EMBEDDING_PROVIDER": str(values["embedding_provider"]),
        "EMBEDDING_MODEL": str(values["embedding_model"]),
        "AUTH_MODE": str(values.get("auth_mode", "required")),
    }
