# OCR Note Converter — Vocab Flashcards

Upload photos of your vocab notes (one `word - definition` per line) and turn
them into flip-style flashcards. Words you've written down more than once get
a ⭐ star — those are the ones you're likely to forget.

## Setup (macOS)

```bash
brew install tesseract          # OCR engine
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Ubuntu/Debian, replace the first line with `sudo apt install tesseract-ocr`.

## Run

```bash
source .venv/bin/activate       # if not already active
uvicorn app:app --reload
```

Open http://localhost:8000, drag in your note photos, and click
**Extract & Build Cards**.

## Tips for good scans

- Good lighting, no shadows across the page
- Hold the camera flat over the page
- Rotated/sideways photos are fixed automatically
- If a scan is too blurry the app will warn you and suggest a retake
