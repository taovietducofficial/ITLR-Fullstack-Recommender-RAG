import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "text", Path(__file__).resolve().parent.parent / "etl_pipeline" / "utils" / "text.py"
)
_text = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_text)
clean_text = _text.clean_text


def test_lowercases():
    assert clean_text("PRODUTO BOM") == "produto bom"


def test_strips_urls():
    assert clean_text("veja http://example.com/x aqui") == "veja aqui"


def test_strips_html():
    assert clean_text("<b>bom</b> produto") == "bom produto"


def test_strips_punctuation():
    assert clean_text("bom! (produto) #1") == "bom produto 1"


def test_strips_emoji():
    assert clean_text("adorei \U0001F600\U0001F680") == "adorei"


def test_lemmatizes_english_plural():
    assert clean_text("good products") == "good product"


def test_empty_string():
    assert clean_text("") == ""
