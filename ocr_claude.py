"""Claude vision-based note reading.

Classical OCR transcribes pixels to text and leaves layout problems (two
columns, wrapped lines, mixed English/Chinese handwriting) to a parser.
A vision-language model reads the page the way a person does, so it returns
clean structured entries directly. Active when ANTHROPIC_API_KEY is set;
callers fall back to Vision/Tesseract otherwise.
"""

import base64
import io
import json
import os

from PIL import Image, ImageOps

try:
    import anthropic

    _SDK = True
except ImportError:
    _SDK = False

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

# Override with VOCAB_OCR_MODEL (e.g. claude-haiku-4-5 to cut cost ~5x).
MODEL = os.environ.get("VOCAB_OCR_MODEL", "claude-opus-4-8")

# Long-edge cap keeps image cost bounded (~1.6K tokens/page) while staying
# plenty readable for notebook pages.
MAX_EDGE = 1568

_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "definition": {"type": "string"},
                },
                "required": ["word", "definition"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["entries"],
    "additionalProperties": False,
}

_PROMPT = (
    "This photo shows a page of handwritten vocabulary notes. Each entry is "
    "an English word or phrase followed by its definition (English or "
    "Chinese) on the same line; definitions sometimes wrap onto the next "
    "line, and the page may show parts of two columns or an adjacent page — "
    "keep entries separate and never merge text across columns. Extract "
    "every vocabulary entry you can read confidently. Transcribe "
    "definitions faithfully (keep Chinese as Chinese; fix only obvious "
    "letter-level misreads, never reword). Skip page numbers, doodles, "
    "cut-off entries at the photo edge, and anything that isn't a vocab "
    "entry."
)


def available() -> bool:
    return _SDK and bool(os.environ.get("ANTHROPIC_API_KEY"))


def _to_jpeg_b64(image_bytes: bytes) -> str:
    """Normalize any upload (HEIC, oversized photos) to an API-ready JPEG."""
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


def extract_entries(image_bytes: bytes) -> list:
    """Return [{word, definition}] read from the photo by Claude."""
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": _to_jpeg_b64(image_bytes),
                    },
                },
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return [
        {"word": e["word"].strip(), "definition": e["definition"].strip()}
        for e in data.get("entries", [])
        if e.get("word", "").strip() and e.get("definition", "").strip()
    ]
