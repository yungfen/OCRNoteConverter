"""OCR pipeline tuned for photographed/scanned vocab note pages.

Phone photos of notebook pages are rarely OCR-ready: they arrive rotated,
low-contrast, shadowed, or too small. Each step here addresses one of those
failure modes so Tesseract sees the cleanest possible page.
"""

import io
import logging

import pytesseract
from PIL import Image, ImageFilter, ImageOps

try:
    # Lets Pillow open iPhone HEIC photos.
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

# Tesseract reads small text poorly; upscale until the shorter side is at
# least this many pixels.
MIN_SIDE = 1500
MAX_SIDE = 4000

# PSM 6 (uniform block of text) fits a page of one-entry-per-line notes;
# PSM 4 (single column, variable sizes) is the fallback for messier layouts.
PSM_CANDIDATES = (6, 4)


def _detect_languages() -> str:
    """Use English + Traditional/Simplified Chinese when the language packs
    are installed; otherwise fall back to English only."""
    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    langs = ["eng"]
    for lang in ("chi_tra", "chi_sim"):
        if lang in available:
            langs.append(lang)
    return "+".join(langs)


_LANGS = _detect_languages()


def _preprocess(image: Image.Image) -> Image.Image:
    # Respect EXIF orientation from phone cameras before anything else.
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")

    short_side = min(image.size)
    if short_side < MIN_SIDE:
        scale = MIN_SIDE / short_side
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)
    elif max(image.size) > MAX_SIDE:
        scale = MAX_SIDE / max(image.size)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.LANCZOS)

    # Stretch contrast (clipping 2% outliers kills shadows/glare) and
    # sharpen pen strokes thinned by resizing.
    image = ImageOps.autocontrast(image, cutoff=2)
    image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=3))
    return image


def _fix_rotation(image: Image.Image) -> Image.Image:
    """Use Tesseract's orientation detection to fix sideways/upside-down pages."""
    try:
        osd = pytesseract.image_to_osd(image, output_type=pytesseract.Output.DICT)
        rotate = int(osd.get("rotate", 0))
        if rotate:
            image = image.rotate(-rotate, expand=True, fillcolor=255)
    except Exception:
        pass  # OSD fails on sparse pages; assume upright.
    return image


def _ocr_with_confidence(image: Image.Image, psm: int) -> tuple[str, float]:
    config = f"--psm {psm}"
    data = pytesseract.image_to_data(
        image, lang=_LANGS, config=config, output_type=pytesseract.Output.DICT
    )
    words = []
    confs = []
    line = []
    prev_key = None
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key != prev_key and line:
            words.append(" ".join(line))
            line = []
        prev_key = key
        if text.strip() and conf >= 0:
            line.append(text)
            confs.append(conf)
    if line:
        words.append(" ".join(line))
    text = "\n".join(words)
    avg_conf = sum(confs) / len(confs) if confs else 0.0
    return text, avg_conf


# Prefer Apple Vision (Live Text engine) on macOS — dramatically better at
# handwriting than Tesseract. Falls back to Tesseract elsewhere.
try:
    import ocr_vision

    _VISION_AVAILABLE = True
except Exception:  # pyobjc can raise more than ImportError on bad installs
    _VISION_AVAILABLE = False

def vision_available() -> bool:
    return _VISION_AVAILABLE


def extract_text(image_bytes: bytes) -> tuple[str, float]:
    """Return (text, confidence 0-100) for the best OCR pass over the image."""
    if _VISION_AVAILABLE:
        try:
            return ocr_vision.extract_text(image_bytes)
        except Exception:
            logging.exception("Vision OCR failed; falling back to Tesseract")

    image = Image.open(io.BytesIO(image_bytes))
    image = _preprocess(image)
    image = _fix_rotation(image)

    best_text, best_conf = "", -1.0
    for psm in PSM_CANDIDATES:
        try:
            text, conf = _ocr_with_confidence(image, psm)
        except Exception:
            continue
        if conf > best_conf:
            best_text, best_conf = text, conf

    return best_text, max(best_conf, 0.0)
