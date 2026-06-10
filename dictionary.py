"""Cross-check OCR'd headwords against dictionaries.

Two layers, both best-effort:
1. Word-list validation — is the OCR'd English headword a real word? If not,
   suggest the closest match (catches OCR slips like 'pidden' -> 'hidden').
2. Apple Dictionary (macOS DictionaryServices) — fetch a reference definition
   so the user can compare it with their own note.
"""

import difflib
import re
from functools import lru_cache

_WORDLIST_PATHS = ("/usr/share/dict/words", "/usr/dict/words")


def _load_words() -> frozenset:
    for path in _WORDLIST_PATHS:
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return frozenset(w.strip().lower() for w in f if w.strip())
        except OSError:
            continue
    return frozenset()


_WORDS = _load_words()

try:
    # pyobjc-framework-CoreServices; only present on macOS installs.
    from CoreServices import DCSCopyTextDefinition

    _APPLE_DICT = True
except Exception:
    _APPLE_DICT = False


def available() -> dict:
    return {"wordlist": bool(_WORDS), "apple_dictionary": _APPLE_DICT}


@lru_cache(maxsize=4096)
def check_word(word: str) -> tuple:
    """Return (verified, suggestion) for an OCR'd headword.

    verified: True (in dictionary), False (not found), None (no wordlist).
    suggestion: closest real word when not found, else None.
    """
    w = word.strip().lower()
    tokens = [t for t in re.split(r"[\s\-']+", w) if t]
    if not _WORDS or not tokens:
        return None, None
    if all(t in _WORDS for t in tokens):
        return True, None
    if len(tokens) == 1:
        # Length prefilter only — OCR errors often hit the first letter
        # (e.g. 'pidden' -> 'hidden'), so don't require it to match.
        candidates = [c for c in _WORDS if abs(len(c) - len(w)) <= 1]
        match = difflib.get_close_matches(w, candidates, n=1, cutoff=0.8)
        return False, (match[0] if match else None)
    return False, None


def autocorrect_word(word: str) -> tuple:
    """Return (corrected_word, original) — original is '' when unchanged.

    Replaces an OCR-garbled headword with its dictionary suggestion when
    one exists; preserves the original casing style for plain lowercase.
    """
    verified, suggestion = check_word(word)
    if verified is False and suggestion:
        return suggestion, word
    return word, ""


# Tokens to never "correct": common note abbreviations.
_DEF_SKIP = {"esp", "sth", "sb", "etc", "vs", "adj", "adv"}


def autocorrect_definition(text: str) -> str:
    """Fix obvious OCR misspellings inside an English definition.

    Conservative: only lowercase ASCII tokens of 4+ chars that aren't in
    the dictionary, with a high similarity cutoff. CJK text is untouched.
    """
    if not _WORDS:
        return text

    def fix(m):
        token = m.group(0)
        if token in _DEF_SKIP or token in _WORDS:
            return token
        candidates = [c for c in _WORDS if abs(len(c) - len(token)) <= 1]
        match = difflib.get_close_matches(token, candidates, n=1, cutoff=0.86)
        return match[0] if match else token

    return re.sub(r"\b[a-z]{4,}\b", fix, text)


@lru_cache(maxsize=4096)
def reference_definition(word: str) -> str:
    """Apple Dictionary definition snippet for the card back ('' if none)."""
    if not _APPLE_DICT:
        return ""
    try:
        result = DCSCopyTextDefinition(None, word, (0, len(word)))
        if not result:
            return ""
        text = re.sub(r"\s+", " ", str(result)).strip()
        return text[:280]
    except Exception:
        return ""
