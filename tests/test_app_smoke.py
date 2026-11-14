from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


def test_app_renders_without_data():
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception
    assert app.title[0].value == "QuantLab"
