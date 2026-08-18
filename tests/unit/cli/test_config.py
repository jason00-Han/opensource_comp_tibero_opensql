from tibero_doc.config import build_dsn, runtime_environment


def test_dsn_password_is_url_encoded():
    config = {
        "db_host": "127.0.0.1", "db_port": 16432,
        "db_user": "postgres", "db_name": "opensql",
    }
    dsn = build_dsn("p@ss:^word#%", config)
    assert dsn == "postgresql://postgres:p%40ss%3A%5Eword%23%25@127.0.0.1:16432/opensql"


def test_runtime_environment_is_created_from_config(tmp_path):
    config = {
        "db_host": "db", "db_port": 6432, "db_user": "app", "db_name": "opensql",
        "data_dir": str(tmp_path), "pipeline_mode": "inline",
        "embedding_provider": "local", "embedding_model": "local-hash-384",
    }
    environment = runtime_environment("secret", config)
    assert environment["TIBERO_DOC_DSN"] == "postgresql://app:secret@db:6432/opensql"
    assert environment["PIPELINE_MODE"] == "inline"
    assert environment["EMBEDDING_PROVIDER"] == "local"
