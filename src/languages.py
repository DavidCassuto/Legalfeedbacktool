# src/languages.py
"""
Taal-register voor de meertalige tool (Fase 0).

Elke taal draagt: weergavenaam, eigen naam, schrijfrichting (ltr/rtl) en de
volledige Engelse naam (voor in de prompt: 'write all feedback in <X>').
Hebreeuws is rtl — de UI moet daar later op gecontroleerd worden.
"""

DEFAULT_LANGUAGE = 'nl'

LANGUAGES = {
    'nl': {'name': 'Nederlands', 'native': 'Nederlands', 'dir': 'ltr', 'english_name': 'Dutch'},
    'en': {'name': 'Engels',     'native': 'English',     'dir': 'ltr', 'english_name': 'English'},
    'he': {'name': 'Hebreeuws',  'native': 'עברית',       'dir': 'rtl', 'english_name': 'Hebrew'},
}


def normalize(code: str) -> str:
    code = (code or '').strip().lower()
    return code if code in LANGUAGES else DEFAULT_LANGUAGE


def meta(code: str) -> dict:
    return LANGUAGES[normalize(code)]


def direction(code: str) -> str:
    return meta(code)['dir']


def english_name(code: str) -> str:
    return meta(code)['english_name']


def choices() -> list[tuple[str, str]]:
    """(code, weergavenaam) voor keuzelijsten."""
    return [(c, m['name']) for c, m in LANGUAGES.items()]
