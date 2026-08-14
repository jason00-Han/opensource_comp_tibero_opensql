from pathlib import Path
import tomllib

CONFIG_DIR = Path.home() / ".tibero-doc"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULT_API_URL = "http://localhost:8000"


def save_config(api_url: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    content = f'''
api_url = "{api_url}"
'''

    CONFIG_FILE.write_text(
        content.strip() + "\n",
        encoding="utf-8",
    )


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        return {
            "api_url": DEFAULT_API_URL
        }

    with CONFIG_FILE.open("rb") as f:
        return tomllib.load(f)


def get_api_url() -> str:
    config = load_config()

    return config.get(
        "api_url",
        DEFAULT_API_URL,
    )