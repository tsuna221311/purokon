"""`.env.example` の設定が起動時に実際に読まれることを見張る。"""

from pathlib import Path


def test_app_loads_project_dotenv_before_engine_imports():
    source = Path("app.py").read_text(encoding="utf-8")
    dotenv_call = source.index("_load_project_dotenv()", source.index("def _load_project_dotenv"))
    engine_import = source.index("from engine.custom_panel import")
    assert dotenv_call < engine_import
    assert "os.environ.setdefault(key, value)" in source
