# Fastype

A typing trainer for the Mac, written in Python with PySide6 (Qt).

## Run it

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/fastype
```

Tests: `.venv/bin/pytest`

### Mac app

`scripts/bundle.sh` builds `Fastype.app` with PyInstaller (about 10 s) and installs it into `~/Applications`, so it opens from Spotlight, Launchpad and the Dock. Rerun it after changing the code. The icon is drawn in code by `scripts/make_icon.py`; after changing it, run that script and then `scripts/bundle.sh`.

## Practice modes

- **Words**: 10–100 random words in English (about 2,800 to pick from) or German (about 2,300, nouns capitalised). Optional punctuation and numbers.
  - Words come from the whole list, which is ordered roughly from most to least common; common words come up more often.
- **Timed**: type as much as you can in 15, 30, 60 or 120 seconds.
- **Weak keys**: picks words that contain the letters you miss most or type slowest, based on your history.
- **Code**: Python, C++ and SQL snippets. Press Return for new lines; indentation is filled in for you.
- **Custom**: paste any text.

**guest** (top right, or ⌘⇧G) lets someone else practise without touching your stats: their runs go into a temporary history that disappears when Fastype quits.

Keys: **Tab** new text, **Esc** restart, **⌥⌫** delete a word, **⌘1 / ⌘2** switch pages, **⌘⇧L** light/dark (also the sun/moon button, top right; the first launch follows macOS). Mistakes stay on screen in red; you can go back and fix them or keep going.

While you type, the on-screen keyboard lights up the next key (and which Shift or Option to hold, on the opposite hand) and flashes keys green or red. It mirrors the keyboard layout macOS is using (German, US, Romanian, …), including the ISO shape with the extra key by left Shift and the tall Return, and follows you when you switch layouts. `ui/layout.py` reads the layout through the system's Text Input Sources API. The streak counter on the right counts correct keys in a row.

**♪ sound** plays a soft key click as you type (a slightly different one each time, a deeper one for space), a muted low tone for a mistake and a short chime when you finish. The **✕ miss** menu swaps the mistake sound for any audio file you pick (MP3, WAV, M4A, AIFF…), with a preview, a volume setting and *Let it finish before playing again* so a long sound isn't restarted by every miss. Picked files are copied to `~/Library/Application Support/Fastype/sounds/`. The built-in sounds are synthesised in code by `ui/sound.py` and cached in `~/Library/Caches/Fastype/`. The sound and keyboard switches are remembered between launches.

After each run you get WPM, raw WPM, accuracy, consistency (how even your rhythm is), the keys you missed and a speed-per-second chart. The **Progress** page shows your totals and day streak, your speed across runs, your accuracy for each hour of the day, a calendar of practice days, a keyboard heatmap of error rates and your slowest keys.

## How it's built

```
src/fastype/
  engine.py   TypingSession: records every keystroke with a timestamp, computes results. No UI code.
  texts.py    Word picking (frequency-weighted), punctuation/number mixing, code snippets.
  data/       english.txt, german.txt: the word lists, most common first. Written for this app and
              checked with the macOS spellchecker. Edit freely; duplicates are ignored.
  settings.py Preferences (FASTYPE_SETTINGS=<file.ini> uses a separate file, for scripted runs).
  store.py    SQLite history (runs + lifetime per-key stats) and the weak-key scoring.
  app.py      Main window.
  ui/         Everything is custom-painted with QPainter:
              theme.py (light matte palette, fonts, keycap and card helpers), sound.py, widgets.py (chips, page switch, stat cards),
              typing_view.py, keyboard.py (live keyboard + heatmap), charts.py, practice.py, progress.py
scripts/      make_icon.py, bundle.sh, launcher.py (PyInstaller entry point)
```

Data lives in `~/Library/Application Support/Fastype/fastype.db`. Set `FASTYPE_DB` to use another file.
