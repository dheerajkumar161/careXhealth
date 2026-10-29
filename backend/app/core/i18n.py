"""Supported languages. A user picks one in Settings; agents write patient-facing text in it (see communication_agent)."""
from __future__ import annotations

DEFAULT_LANGUAGE = "en"

# code → (English name, native name)
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"),
    "hi": ("Hindi", "हिन्दी"),
    "bn": ("Bengali", "বাংলা"),
    "ta": ("Tamil", "தமிழ்"),
    "te": ("Telugu", "తెలుగు"),
    "mr": ("Marathi", "मराठी"),
    "gu": ("Gujarati", "ગુજરાતી"),
    "kn": ("Kannada", "ಕನ್ನಡ"),
    "ml": ("Malayalam", "മലയാളം"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ"),
    "ur": ("Urdu", "اردو"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "ar": ("Arabic", "العربية"),
    "pt": ("Portuguese", "Português"),
    "de": ("German", "Deutsch"),
}


def normalize_language(code: str | None) -> str:
    c = (code or "").strip().lower().split("-")[0]
    return c if c in LANGUAGES else DEFAULT_LANGUAGE


def language_name(code: str | None) -> str:
    return LANGUAGES[normalize_language(code)][0]


def language_list() -> list[dict[str, str]]:
    return [{"code": c, "name": n, "native": nat} for c, (n, nat) in LANGUAGES.items()]
