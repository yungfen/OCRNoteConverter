import json
import logging
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys

from ocr import extract_text, vision_available
from parser import parse_vocab

# Below this average Tesseract confidence the result is mostly garbage;
# better to tell the user to retake the photo than show junk cards.
LOW_CONFIDENCE = 45.0

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Vocab Flashcard App")


@app.on_event("startup")
async def log_engine():
    engine = "Apple Vision" if vision_available() else "Tesseract"
    logging.info("OCR engine: %s", engine)
    if sys.platform == "darwin" and not vision_available():
        logging.warning(
            "Apple Vision not active — run 'pip install -r requirements.txt' "
            "in your virtualenv for much better handwriting OCR."
        )


@app.get("/health")
async def health():
    return JSONResponse(content={
        "ocr_engine": "Apple Vision" if vision_available() else "Tesseract",
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


@app.get("/")
async def serve_ui():
    index_path = static_dir / "index.html"
    return FileResponse(str(index_path), media_type="text/html")


@app.post("/upload")
async def upload_images(files: List[UploadFile] = File(...)):
    freq = load_freq()
    all_cards = []
    warnings = []

    if sys.platform == "darwin" and not vision_available():
        warnings.append(
            "Apple Vision OCR is not active — handwriting accuracy will be poor. "
            "Run: pip install -r requirements.txt inside your virtualenv, "
            "then restart the server."
        )

    for upload in files:
        contents = await upload.read()
        name = upload.filename or "image"
        try:
            ocr_text, confidence = extract_text(contents)
        except Exception:
            logging.exception("OCR failed for %s", name)
            warnings.append(f"{name}: could not be read as an image.")
            continue

        if confidence < LOW_CONFIDENCE:
            warnings.append(
                f"{name}: scan quality is low (confidence {confidence:.0f}%). "
                "Try better lighting, hold the camera flat, or rescan."
            )

        # Parse vocab entries
        entries = parse_vocab(ocr_text)
        if not entries:
            warnings.append(f"{name}: no vocab entries found on this page.")
            continue

        for entry in entries:
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
        starred = freq.get(key, {}).get("count", 1) > 1
        response_cards.append({
            "word": freq[key]["word"],
            "definition": freq[key]["definition"],
            "starred": starred,
        })

    return JSONResponse(content={"cards": response_cards, "warnings": warnings})


@app.post("/reset")
async def reset_cards():
    if freq_file.exists():
        freq_file.unlink()
    return JSONResponse(content={"ok": True})


@app.get("/cards")
async def get_all_cards():
    freq = load_freq()
    cards = []
    for key, data in freq.items():
        cards.append({
            "word": data["word"],
            "definition": data["definition"],
            "starred": data.get("count", 1) > 1,
        })
    return JSONResponse(content={"cards": cards})
