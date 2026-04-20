# ten-9

Push-to-talk voice morpher.  
**Mic → Whisper (speech-to-text) → Clipboard + Piper (robotic text-to-speech) → Virtual audio cable.**

Hold your push-to-talk button, speak, release. The transcription lands in
your clipboard (paste with `Ctrl+V` anywhere), and in *robot mode* it is
also spoken by Piper in a GLaDOS-style voice into a virtual audio cable,
so friends on Discord hear the robot, not you.

## Features

- Local, GPU-accelerated Whisper transcription (no cloud)
- Robot-voice playback via Piper to any output device
- Push-to-talk on a keyboard key **or** mouse4 / mouse5
- Live hotkeys to swap language, translate-to-English, toggle mode
- Single `config.toml` drives everything; no code edits needed

## Prerequisites

- **Python 3.11 or newer** (uses the stdlib `tomllib`)
- **Windows 10/11**
- A **virtual audio cable** so Discord/OBS can hear Piper:
  - [VB-Cable](https://vb-audio.com/Cable/) (simplest, free)
  - or [Voicemeeter](https://vb-audio.com/Voicemeeter/) (more flexible)
- *Optional* NVIDIA GPU + CUDA for fast Whisper. CPU works too (slower).

## Quick start

1. Clone this repo.
2. Run the setup script: double-click `setup.bat` (or `.\setup.bat` in a
   terminal). This creates `.venv/`, installs dependencies, downloads the
   Piper binary and the default GLaDOS voice model, and copies
   `config.EXAMPLE.toml` → `config.toml`.
3. Find your audio device names:
   ```
   run.bat --list-devices
   ```
4. Open `config.toml` and set:
   - `audio.tts_output_name_contains`: the virtual cable input
     (e.g. `"CABLE Input"`).
   - `audio.beep_output_name_contains`: your real speakers/headphones.
   - `hotkeys.ptt`: push-to-talk button (`mouse4`, `mouse5`, or a key).
5. Run:
   ```
   run.bat
   ```
6. Hold PTT, speak, release. Text is on your clipboard. Toggle robot mode
   with the configured hotkey (default `Ctrl+Alt+Numpad 1`) to also speak
   it through the virtual cable.

## Hotkeys (defaults, edit in `config.toml`)

| Action                         | Default             |
|--------------------------------|---------------------|
| Push-to-talk                   | `mouse4`            |
| Toggle clipboard / robot mode  | `Ctrl+Alt+Num 1`    |
| Language → English             | `Ctrl+Alt+6`        |
| Language → Korean              | `Ctrl+Alt+7`        |
| Task → transcribe              | `Ctrl+Alt+8`        |
| Task → translate (to English)  | `Ctrl+Alt+9`        |

## Piper voices

Any Piper `.onnx` + matching `.onnx.json` model works. Drop new voices into
`piper/models/` and point `piper.model` in `config.toml` at one. More voices:
[Piper releases](https://github.com/rhasspy/piper/releases).

## Troubleshooting

- **"output device containing 'CABLE Input' not found"**
  VB-Cable is not installed or reports a different name. Run
  `--list-devices` and copy the right substring.
- **Whisper errors on CUDA**
  Try `device = "cpu"` and `compute_type = "int8"` in `config.toml`. CPU is
  fine for short phrases. If you *want* CUDA, make sure cuBLAS/cuDNN match
  the `faster-whisper` version; see the
  [faster-whisper docs](https://github.com/SYSTRAN/faster-whisper#gpu).
- **No beep sound**
  The beep device may not support 48 kHz. Set `beep.sample_rate = 44100`,
  or leave `beep_output_name_contains = ""` to use the system default.

## Project layout

```
ten-9/
├── ten9.py                 # main script (one file, clearly sectioned)
├── config.EXAMPLE.toml     # template, copied to config.toml on setup
├── config.toml             # your settings (gitignored)
├── requirements.txt
├── setup.bat               # creates venv, downloads Piper + GLaDOS model
├── run.bat                 # activates venv and launches ten-9
└── piper/                  # downloaded by setup (gitignored)
    ├── piper.exe
    └── models/
        └── glados_piper_medium.onnx
```

## Credits & licenses

ten-9 itself is MIT-licensed. It relies on several other projects, each
with its own license. The setup script downloads these from their
official sources; they are **not** bundled in this repository.

| Component | License | Source |
|---|---|---|
| Piper TTS | MIT | [rhasspy/piper](https://github.com/rhasspy/piper) |
| GLaDOS voice model | CC-BY-4.0 | [DavesArmoury / GLaDOS_TTS](https://huggingface.co/DavesArmoury/GLaDOS_TTS) |
| faster-whisper | MIT | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| sounddevice | MIT | [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) |
| keyboard | MIT | [boppreh/keyboard](https://github.com/boppreh/keyboard) |
| pynput | LGPL-3.0 | [moses-palmer/pynput](https://github.com/moses-palmer/pynput) |
| pyperclip | BSD-3-Clause | [asweigart/pyperclip](https://github.com/asweigart/pyperclip) |
| numpy | BSD-3-Clause | [numpy/numpy](https://github.com/numpy/numpy) |

If you redistribute a build of ten-9 that bundles any of these (e.g. a
zipped release with Piper pre-extracted), include each bundled
component's LICENSE file alongside it. The default setup flow avoids
this entirely by fetching everything at install time.

**Disclaimer about the GLaDOS voice.** The CC-BY-4.0 license covers
DavesArmoury's trained model weights, not Valve's intellectual property
in the GLaDOS character or her voice. This project treats the voice as
fan-use; swap in a different Piper voice if that's a concern for your
deployment.
