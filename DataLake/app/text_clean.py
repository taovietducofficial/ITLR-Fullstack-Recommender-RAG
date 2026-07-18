import re

from nltk.stem import WordNetLemmatizer

_lemmatizer = None

_HTML = re.compile(r"<[^>]*>")
_PUNCTUATIONS = "@#!?+&*[]-%.:/();$=><|{}^" + "'`" + "_"
_EMOJI = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)


def _get_lemmatizer():
    global _lemmatizer
    if _lemmatizer is None:
        import nltk

        nltk.download("wordnet", quiet=True)
        _lemmatizer = WordNetLemmatizer()
    return _lemmatizer


def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = _HTML.sub(r"", text)
    for p in _PUNCTUATIONS:
        text = text.replace(p, "")
    lemmatizer = _get_lemmatizer()
    words = [lemmatizer.lemmatize(word) for word in text.split()]
    text = " ".join(words)
    return _EMOJI.sub(r"", text).strip()
