from __future__ import annotations

DEFAULT_LANG = "en"
SUPPORTED_LANGUAGES = ("en", "it")


def translate(strings: dict[str, dict[str, str]], lang: str, key: str, **kwargs) -> str:
    """Looks up `key` in `strings[lang]`, falling back to English if the
    language or the key itself is missing (a key added to one language and
    forgotten in the other still renders instead of raising). Callers own a
    module-local `_STRINGS` dict shaped {lang: {key: template}} and use this
    as their single lookup+format helper - see cost_saving_agent.py,
    guardrails.py, anomalies.py and duplicates.py."""
    table = strings.get(lang) or strings[DEFAULT_LANG]
    template = table.get(key) or strings[DEFAULT_LANG][key]
    return template.format(**kwargs) if kwargs else template
