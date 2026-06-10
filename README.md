# OCR Note Converter — Vocab Flashcards

Upload photos of your vocab notes (one `word - definition` per line) and turn
them into flip-style flashcards. Words you've written down more than once get
a ⭐ star — those are the ones you're likely to forget.

## Setup (macOS)

```bash
brew install tesseract          # OCR engine
brew install tesseract-lang     # Chinese (and other) language packs
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Ubuntu/Debian, replace the first line with `sudo apt install tesseract-ocr`.

## Best quality: Claude AI reading (recommended)

With an Anthropic API key, photos are read by Claude's vision model — the
same capability that reads handwriting in the Claude app. It understands
two-column layouts, wrapped definitions, and mixed English/Chinese
handwriting, and returns clean cards directly. Without a key, the app
falls back to Apple Vision (macOS) or Tesseract.

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # get one at console.anthropic.com
```

Cost is roughly a cent or two per page. To cut cost ~5x at slightly lower
accuracy: `export VOCAB_OCR_MODEL=claude-haiku-4-5`.

## Run

```bash
./run.sh
```

This starts the server with hot reload (code changes apply without
restarting) and accepts connections from your phone. Equivalent to:

```bash
source .venv/bin/activate
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open http://localhost:8000, drag in your note photos, and click
**Extract & Build Cards**.

## Use from your phone

Start the server so it accepts connections from your local network:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

With your phone on the same Wi-Fi as your computer, open
`http://<your-computer-ip>:8000` — the exact URL is printed in the
terminal at startup. On iPhone you can tap the upload area to take a
photo of your notes directly with the camera.

If the page doesn't load, allow incoming connections when macOS firewall
asks (System Settings → Network → Firewall).

## Tips for good scans

- Good lighting, no shadows across the page
- Hold the camera flat over the page
- Rotated/sideways photos are fixed automatically
- If a scan is too blurry the app will warn you and suggest a retake
