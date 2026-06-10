# Roadmap

Planned once core OCR → card flow is stable:

1. **Spaced repetition (間隔重複)** — schedule reviews per card (e.g. SM-2:
   again/hard/good/easy), store due dates, "review today" queue. Starred
   (frequently re-written) words surface more often.
2. **Quizlet-style swipe practice (左右滑)** — swipe right = know it,
   swipe left = still learning; learning pile repeats until empty.
3. **Multiple-choice quizzes (選擇題)** — generate distractor definitions
   from other cards in the deck; track accuracy per card and feed results
   back into the spaced-repetition scheduler.

Implementation notes for later:
- Card store needs per-card state beyond `count`: ease factor, interval,
  due date, right/wrong history — migrate `data/vocab_freq.json` schema.
- Swipe UI: pointer events on the existing flip-card element.
