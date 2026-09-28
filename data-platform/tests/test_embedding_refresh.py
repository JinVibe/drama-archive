import importlib.util
import sys
from pathlib import Path

import pytest

DAG_FILE = Path(__file__).resolve().parents[1] / "dags" / "embedding_refresh.py"


@pytest.fixture(scope="module")
def dag_module():
    # The DAG file imports airflow at module level; only the pure helper is under test here.
    pytest.importorskip("airflow")
    spec = importlib.util.spec_from_file_location("embedding_refresh_dag", DAG_FILE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_embed_text_puts_title_first_and_flattens_aliases(dag_module):
    text = dag_module.embed_text("도깨비", "Goblin\nGuardian", "방송사: tvN\n출연: 공유")
    assert text == "도깨비\nGoblin / Guardian\n방송사: tvN\n출연: 공유"
    assert dag_module.embed_text("시그널", "", "") == "시그널"


def test_embed_synopsis_text_is_plot_only_or_absent(dag_module):
    text = dag_module.embed_synopsis_text("도깨비", "불멸의 도깨비")
    assert text == "도깨비\n줄거리: 불멸의 도깨비"
    assert dag_module.embed_synopsis_text("도깨비", "") is None
