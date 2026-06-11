import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sys

import ocr_claude
from dictionary import check_word, reference_definition
from ocr import extract_text, vision_available
from parser import parse_vocab


def decorate(card: dict) -> dict:
    """Attach dictionary cross-check info to a card."""
    verified, suggestion = check_word(card["word"])
    card["verified"] = verified
    card["suggestion"] = suggestion
    card["ref_def"] = reference_definition(card["word"])
    return card

# Below these average confidences the result is mostly garbage; better to
# tell the user to retake the photo than show junk cards. Vision reports
# conservative scores on handwriting, so its threshold is lower.
LOW_CONFIDENCE = {"tesseract": 45.0, "vision": 28.0}

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Vocab Flashcard App")


def _lan_ip() -> str | None:
    """Best-effort LAN IP so the phone URL can be printed at startup."""
    import socket

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


@app.on_event("startup")
async def log_engine():
    logging.info("OCR engine: %s", _engine_name())
    if sys.platform == "darwin" and not vision_available():
        logging.warning(
            "Apple Vision not active — run 'pip install -r requirements.txt' "
            "in your virtualenv for much better handwriting OCR."
        )
    ip = _lan_ip()
    if ip:
        logging.info(
            "On your phone (same Wi-Fi), open: http://%s:8000 "
            "(requires --host 0.0.0.0)", ip
        )


def _engine_name() -> str:
    if ocr_claude.available():
        return "Claude AI"
    return "Apple Vision" if vision_available() else "Tesseract"


@app.get("/health")
async def health():
    return JSONResponse(content={
        "ocr_engine": _engine_name(),
        "claude_available": ocr_claude.available(),
        "vision_available": vision_available(),
        "platform": sys.platform,
    })

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Data directory and frequency store
data_dir = Path(__file__).parent / "data"
data_dir.mkdir(exist_ok=True)
freq_file = data_dir / "vocab_freq.json"


def load_freq() -> dict:
    if freq_file.exists():
        try:
            with open(freq_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_freq(freq: dict):
    with open(freq_file, "w", encoding="utf-8") as f:
        json.dump(freq, f, ensure_ascii=False, indent=2)


def normalize_word(word: str) -> str:
    return word.strip().lower()


# ---- Spaced repetition (lightweight) ----
# Streak-based intervals: each consecutive correct answer doubles the gap,
# capped at the last entry. A wrong answer resets to "see it again tomorrow".
SRS_INTERVALS_DAYS = [1, 2, 4, 8, 16, 32]


def srs_state(entry: dict) -> dict:
    """Per-word SRS state, tolerating entries saved before SRS existed."""
    srs = entry.get("srs") or {}
    return {
        "streak": srs.get("streak", 0),
        "last_review": srs.get("last_review"),
        "due": srs.get("due"),
    }


def card_payload(entry: dict) -> dict:
    """Build the API card shape for one freq-store entry."""
    srs = srs_state(entry)
    return decorate({
        "word": entry["word"],
        "definition": entry["definition"],
        "starred": entry.get("count", 1) > 1,
        "corrected_from": entry.get("corrected_from", ""),
        "streak": srs["streak"],
        "due": srs["due"],
    })


class ReviewResult(BaseModel):
    word: str
    correct: bool


class ReviewPayload(BaseModel):
    results: List[ReviewResult]


@app.post("/review")
async def review(payload: ReviewPayload):
    """Record practice/quiz results and reschedule each word."""
    freq = load_freq()
    now = datetime.now(timezone.utc)
    updated = 0
    for result in payload.results:
        entry = freq.get(normalize_word(result.word))
        if entry is None:
            continue  # unknown word (e.g. deck was reset mid-session)
        srs = srs_state(entry)
        if result.correct:
            srs["streak"] += 1
            days = SRS_INTERVALS_DAYS[
                min(srs["streak"], len(SRS_INTERVALS_DAYS)) - 1
            ]
        else:
            srs["streak"] = 0
            days = 1
        srs["last_review"] = now.isoformat()
        srs["due"] = (now + timedelta(days=days)).isoformat()
        entry["srs"] = srs
        updated += 1
    save_freq(freq)
    return JSONResponse(content={"ok": True, "updated": updated})


@app.get("/")
async def serve_ui():
    index_path = static_dir / "index.html"
    return FileResponse(str(index_path), media_type="text/html")


@app.post("/upload")
async def upload_images(files: List[UploadFile] = File(...)):
    freq = load_freq()
    all_cards = []
    warnings = []

    if (sys.platform == "darwin" and not vision_available()
            and not ocr_claude.available()):
        warnings.append(
            "Apple Vision OCR is not active — handwriting accuracy will be poor. "
            "Run: pip install -r requirements.txt inside your virtualenv, "
            "then restart the server."
        )

    for upload in files:
        contents = await upload.read()
        name = upload.filename or "image"
        entries = None

        # Claude vision reads the page like a person — structured entries,
        # no parsing needed. Best quality for handwriting.
        if ocr_claude.available():
            try:
                entries = ocr_claude.extract_entries(contents)
            except Exception:
                logging.exception(
                    "Claude OCR failed for %s; falling back", name
                )

        if entries is None:
            try:
                ocr_text, confidence, engine = extract_text(contents)
            except Exception:
                logging.exception("OCR failed for %s", name)
                warnings.append(f"{name}: could not be read as an image.")
                continue

            if confidence < LOW_CONFIDENCE[engine]:
                # Below this threshold the "cards" are mostly OCR garbage —
                # skip the page rather than pollute the deck with junk.
                engine_label = (
                    "Apple Vision" if engine == "vision" else "Tesseract"
                )
                warnings.append(
                    f"{name}: scan quality too low (confidence "
                    f"{confidence:.0f}%, engine: {engine_label}) — page "
                    "skipped. Try better lighting, hold the camera flat, "
                    "and photograph one page at a time."
                )
                continue

            entries = parse_vocab(ocr_text)

        if not entries:
            warnings.append(f"{name}: no vocab entries found on this page.")
            continue

        for entry in entries:
            # Keep the user's content verbatim — auto-replacing OCR'd text
            # fabricates notes the user never wrote. Fidelity > tidiness;
            # accuracy comes from the OCR engine, not post-hoc rewriting.
            word = entry["word"]
            definition = entry["definition"]
            key = normalize_word(word)

            # Update frequency (count how many times this word has appeared)
            if key in freq:
                freq[key]["count"] += 1
                # Keep most recent definition if different
                if freq[key]["definition"] != definition:
                    freq[key]["definition"] = definition
            else:
                freq[key] = {"word": word, "definition": definition, "count": 1}

            all_cards.append({"word": word, "definition": definition, "key": key})

    save_freq(freq)

    # Build response cards with starred status
    # A word is starred if it has appeared more than once (across all uploads/sessions)
    seen_keys = set()
    response_cards = []
    for card in all_cards:
        key = card["key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        response_cards.append(card_payload(freq[key]))

    return JSONResponse(content={"cards": response_cards, "warnings": warnings})


@app.post("/reset")
async def reset_cards():
    if freq_file.exists():
        freq_file.unlink()
    return JSONResponse(content={"ok": True})


@app.get("/cards")
async def get_all_cards():
    freq = load_freq()
    cards = [card_payload(data) for data in freq.values()]
    return JSONResponse(content={"cards": cards})
