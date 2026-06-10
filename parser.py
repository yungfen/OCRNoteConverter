import re
from typing import List, Dict


def parse_vocab(text: str) -> List[Dict[str, str]]:
    """
    Parse OCR text into a list of {word, definition} dicts.
    Supports formats:
      - word - definition
      - word: definition
      - word = definition
      - word  <2+ spaces>  definition
    Strips OCR noise (short lines, lines that are just numbers/punctuation).
    """
    cards = []
    lines = text.splitlines()

    for line in lines:
        line = line.strip()

        # Skip short lines (under 3 chars)
        if len(line) < 3:
            continue

        # Skip lines that are only numbers and/or punctuation
        if re.fullmatch(r'[\d\s\W]+', line):
            continue

        entry = None

        # Try delimiters in order: " - ", ": ", " = "
        for delimiter in [' - ', ': ', ' = ']:
            if delimiter in line:
                parts = line.split(delimiter, 1)
                word = parts[0].strip()
                definition = parts[1].strip()
                if word and definition:
                    entry = {'word': word, 'definition': definition}
                    break

        # If no delimiter matched, try splitting on 2+ whitespace
        if entry is None:
            match = re.split(r' {2,}', line, maxsplit=1)
            if len(match) == 2:
                word = match[0].strip()
                definition = match[1].strip()
                if word and definition:
                    entry = {'word': word, 'definition': definition}

        if entry is not None:
            cards.append(entry)

    return cards
