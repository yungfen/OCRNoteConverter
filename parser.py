import re
from typing import List, Dict


# Minimum length for a word and definition to be considered valid
_MIN_WORD_LEN = 1
_MIN_DEF_LEN = 2

# Regex: a word (possibly multi-word) followed by a delimiter then a definition.
# We try to detect multiple entries merged onto one line by OCR by looking for
# repeated delimiter patterns.
_MERGED_SPLIT_RE = re.compile(
    r'(?<=[a-z,;\.!\?])(?=\s+[A-Za-z]{2,}\s+(?:-\s|\:\s|=\s))',
)


def _split_entry(line: str):
    """
    Try to split a single line into (word, definition) using priority delimiters.
    Returns a (word, definition) tuple or None.
    Priority order: ' - ', ':', '=', 2+ spaces.
    """
    # 1. dash with spaces (most common in vocab notes)
    if ' - ' in line:
        parts = line.split(' - ', 1)
        word, definition = parts[0].strip(), parts[1].strip()
        if word and definition:
            return word, definition

    # 2. colon (with or without trailing space, but word must not be empty)
    m = re.match(r'^([^:=]{1,80}):\s+(.+)$', line)
    if m:
        word, definition = m.group(1).strip(), m.group(2).strip()
        if word and definition:
            return word, definition

    # 3. equals sign with spaces
    if ' = ' in line:
        parts = line.split(' = ', 1)
        word, definition = parts[0].strip(), parts[1].strip()
        if word and definition:
            return word, definition

    # 4. two or more spaces (OCR padding)
    m2 = re.split(r' {2,}', line, maxsplit=1)
    if len(m2) == 2:
        word, definition = m2[0].strip(), m2[1].strip()
        if word and definition:
            return word, definition

    return None


def _is_garbage(line: str) -> bool:
    """Return True for lines that are pure noise (no alphabetic content)."""
    # Must contain at least one letter
    if not re.search(r'[A-Za-z]', line):
        return True
    # Very short lines with no delimiter are likely page numbers / artifacts
    if len(line) < 4 and not any(d in line for d in [' - ', ':', '=']):
        return True
    return False


def parse_vocab(text: str) -> List[Dict[str, str]]:
    """
    Parse OCR text into a list of {word, definition} dicts.

    Supports formats (in priority order):
      word - definition          (dash with spaces — primary)
      word: definition           (colon)
      word = definition          (equals with spaces)
      word  <2+ spaces>  def    (OCR spacing artifact)

    Handles:
      - Many entries per page (processes every non-garbage line)
      - OCR-merged lines (two entries without a newline between them)
      - Extra whitespace / noise characters
    """
    cards = []

    # Normalise line endings and collapse runs of blank lines
    lines = text.splitlines()

    for raw_line in lines:
        line = raw_line.strip()

        # Skip empty or garbage lines
        if not line or _is_garbage(line):
            continue

        # Attempt to detect OCR-merged lines: two entries joined without '\n'.
        # Heuristic: after a definition-like segment there's another word followed
        # by a known delimiter.  Split on that boundary and process each sub-line.
        sub_lines = _try_split_merged(line)

        for sub in sub_lines:
            sub = sub.strip()
            if not sub or _is_garbage(sub):
                continue
            result = _split_entry(sub)
            if result is not None:
                word, definition = result
                # Basic sanity: word shouldn't be suspiciously long (likely noise)
                if len(word) <= 120 and len(definition) >= _MIN_DEF_LEN:
                    cards.append({'word': word, 'definition': definition})

    return cards


def _try_split_merged(line: str) -> List[str]:
    """
    If a line looks like two vocab entries glued together by OCR, split them.
    Otherwise return a single-element list containing the original line.

    Detection: look for a known delimiter pattern appearing *after* a
    plausible definition segment (ends with a letter/punctuation) and is
    followed by a capitalised or regular word.
    """
    # Pattern: content, then a word (possibly Title-cased) right before ' - '
    # e.g. "ubiquitous - present everywhere ephemeral - lasting a short time"
    parts = re.split(r'(?<=\S)\s+(?=[A-Za-z][a-z]+ - |[A-Za-z][a-z]+: )', line)
    if len(parts) > 1:
        return parts
    return [line]
