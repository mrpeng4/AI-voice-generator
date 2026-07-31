# 🎙 AI Voice Generator

A desktop app for turning text into natural-sounding speech using Microsoft Edge's
online neural voices (via `edge-tts`). Generate a single voice-over, or build a
multi-character script with a different voice, speed, and pitch per line.

---

## Features

- **Single Voice Mode** — type or paste text, pick a voice, tune speed/pitch, preview
  it out loud, and export to MP3.
- **Multi Voice Mode** — build a script line-by-line, each with its own voice, speed,
  and pitch. Reorder, clone, or delete lines individually, then play or export the
  whole script as one MP3.
- **Name-Based Auto Split** — paste a script like:
  ```
  Alice: Hey, are you free later?
  Bob: Yeah, what's up?
  ```
  and the app automatically splits it into rows, one per line, with a voice assigned
  to each speaker in rotation. An optional "Remove Names" toggle controls whether the
  speaker's name is stripped from the spoken text or read aloud.
- **Favorites** — star your go-to voices so they're quick to reach in both Single and
  Multi Voice mode. Favorites auto-populate the "Voices to Use" box in Multi Voice
  mode on open.
- **Recent Exports** — the last 10 files you've saved are logged and viewable from
  the home screen.
- **Built-in Tutorial** — a step-by-step walkthrough of every feature, launched from
  the home screen at any time.
- **Light/Dark theme toggle**, resizable window, and clean, human-readable voice
  names (e.g. `Aria (United States)` instead of `en-US-AriaNeural`).

## Requirements

- Python 3.9+
- An internet connection (required — this app streams audio from Microsoft's
  online TTS service; it checks connectivity on launch and exits with a warning if
  offline)

### Python packages

```bash
pip install customtkinter edge-tts pygame
```

| Package | Purpose |
|---|---|
| `customtkinter` | Modern-styled UI on top of Tkinter |
| `edge-tts` | Fetches the voice list and generates speech via Microsoft Edge's TTS service |
| `pygame` | Plays back generated audio |

Tkinter itself ships with most Python installations; on Linux you may need to
install it separately (e.g. `sudo apt install python3-tk`).

## Running the app

```bash
python voice_app.py
```

On launch, the app checks for an internet connection, then fetches the full list
of available voices before showing the home screen.

## How to use it

### Single Voice Mode
1. Type or paste your text into the box.
2. Pick a voice from the dropdown (or select one of your ⭐ favorites).
3. Adjust **Speed** and **Pitch** with the sliders if you want.
4. Click **🔊 Speak** to preview, or **💾 Save MP3** to export.

### Multi Voice Mode
1. Add voices to the **Voices to Use** box (➕ Add Voice, or ⭐ Add a favorite).
   Use the ⬆️⬇️ buttons to change the order voices are assigned in.
2. Either:
   - Build rows manually with **➕ Add Sentence**, picking a voice/speed/pitch per row, or
   - Paste a `Name: line` formatted script into the **Name-Based Split** box and click
     **👥 Name-Based Auto Split** to generate rows automatically.
3. Use ⬆️⬇️ to reorder, 📥 to clone, or ❌ to remove any row.
4. **🔊 Speak All** previews the full script in order; **💾 Save All** exports it as a
   single MP3.

### Favorites
Click the star (☆ / ⭐) next to a voice to add or remove it from your favorites.
Favorites are saved between sessions and are available from a dedicated dropdown in
both modes.

## Data storage

The app stores small local files under a per-user app data folder:

- **Windows:** `%APPDATA%\AI_Voice_Generator\`
- **macOS/Linux:** `~/AI_Voice_Generator/`

| File | Contents |
|---|---|
| `favorite_voices.json` | Your starred voices |
| `recent_exports.json` | The last 10 MP3s you've saved, with timestamps |

No text or audio you generate is stored or sent anywhere beyond what's needed to
synthesize speech via the TTS service.

## Notes & limitations

- Requires an active internet connection — there's no offline/local TTS fallback.
- Long text is automatically chunked before synthesis to stay within the TTS
  service's limits.
- Voice availability and quality depend on Microsoft's Edge TTS service.

## License

Add your preferred license here (e.g. MIT).
