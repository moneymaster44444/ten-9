#!/usr/bin/env python
"""
ten-9 -- voice morpher
Mic -> Whisper (speech-to-text) -> Clipboard + Piper (robotic text-to-speech)

Hold your push-to-talk button, speak, release. The transcription is copied
to your clipboard (paste with Ctrl+V anywhere), and in "robot" mode it is
also spoken aloud by Piper into whichever output device you choose -
typically a virtual audio cable that Discord/OBS/etc. listen to as your mic.

All settings live in config.toml. See config.EXAMPLE.toml for docs.
Run `python ten9.py --list-devices` to discover audio device names.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
import wave
from pathlib import Path
from typing import Any

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from pynput import mouse


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config.toml"
CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "config.EXAMPLE.toml"


# ============================================================
# CONFIG LOADING
# ============================================================

def load_config() -> dict[str, Any]:
    """Load config.toml. If it is missing, copy config.EXAMPLE.toml first."""
    if not CONFIG_PATH.exists():
        if not CONFIG_EXAMPLE_PATH.exists():
            sys.exit(
                f"ERROR: neither {CONFIG_PATH.name} nor {CONFIG_EXAMPLE_PATH.name} "
                "exists. Run setup.bat / setup.sh first."
            )
        print(f"[config] creating {CONFIG_PATH.name} from {CONFIG_EXAMPLE_PATH.name}")
        shutil.copyfile(CONFIG_EXAMPLE_PATH, CONFIG_PATH)

    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def resolve_path(p: str | Path) -> Path:
    """Relative paths in config are resolved against the project root."""
    p = Path(p)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


# ============================================================
# RUNTIME STATE
# ============================================================
# These values change at runtime via hotkeys. Collecting them in one
# dict makes it obvious what is dynamic and what comes from config.

STATE: dict[str, Any] = {
    "mode": "clipboard",      # "clipboard" or "robot"
    "language": "en",         # Whisper language code, or None for auto-detect
    "task": "transcribe",     # "transcribe" or "translate"
}


# ============================================================
# MOUSE LISTENER  (for mouse4 / mouse5 push-to-talk)
# ============================================================
# pynput's mouse listener runs on a background thread and flips flags
# in _mouse_state. _wait_for_press / _is_held read those flags.

_mouse_listener: mouse.Listener | None = None
_mouse_lock = threading.Lock()
_mouse_state: dict[str, bool] = {"mouse4": False, "mouse5": False}
_mouse_event = threading.Event()


def _start_mouse_listener() -> None:
    global _mouse_listener
    if _mouse_listener is not None:
        return

    def on_click(x, y, button, pressed):
        if button == mouse.Button.x1:
            name = "mouse4"
        elif button == mouse.Button.x2:
            name = "mouse5"
        else:
            return
        with _mouse_lock:
            _mouse_state[name] = bool(pressed)
            _mouse_event.set()

    _mouse_listener = mouse.Listener(on_click=on_click)
    _mouse_listener.daemon = True
    _mouse_listener.start()


def _stop_mouse_listener() -> None:
    global _mouse_listener
    if _mouse_listener is not None:
        try:
            _mouse_listener.stop()
        except Exception:
            pass
        _mouse_listener = None


def _wait_for_press(trigger: str) -> None:
    """Block until `trigger` is pressed (keyboard key or mouse4/mouse5)."""
    t = trigger.strip().lower()
    if t in ("mouse4", "mouse5"):
        _start_mouse_listener()
        while True:
            _mouse_event.clear()
            with _mouse_lock:
                if _mouse_state.get(t, False):
                    return
            _mouse_event.wait(timeout=0.5)
    else:
        keyboard.wait(trigger)


def _is_held(trigger: str) -> bool:
    """Return True if `trigger` is currently held down."""
    t = trigger.strip().lower()
    if t in ("mouse4", "mouse5"):
        with _mouse_lock:
            return bool(_mouse_state.get(t, False))
    return keyboard.is_pressed(trigger)


# ============================================================
# AUDIO DEVICE HELPERS
# ============================================================

def find_matching_output_devices(name_contains: str) -> list[tuple[int, dict, str]]:
    """Return every output device whose name contains `name_contains`
    (case-insensitive). Empty input returns []. Result items are
    (idx, device_info_dict, host_api_name)."""
    if not name_contains:
        return []
    needle = name_contains.lower()
    hosts = sd.query_hostapis()
    matches: list[tuple[int, dict, str]] = []
    for idx, d in enumerate(sd.query_devices()):
        if d.get("max_output_channels", 0) > 0 and needle in d.get("name", "").lower():
            host_name = hosts[d["hostapi"]]["name"]
            matches.append((idx, d, host_name))
    return matches


def find_output_device(name_contains: str) -> int | None:
    """Return the first output device index whose name contains `name_contains`
    (case-insensitive). Returns None if `name_contains` is empty or no match.
    When multiple devices match, the first one sounddevice enumerates wins --
    on Windows this is the MME version, which is the most compatible host API."""
    matches = find_matching_output_devices(name_contains)
    return matches[0][0] if matches else None


def list_devices() -> None:
    """Print all audio devices -- used by the `--list-devices` CLI flag."""
    print("\nAvailable audio devices:")
    print(f"  {'idx':>4}  {'I/O':<5}  name  [host api]")
    print("  " + "-" * 60)
    hosts = sd.query_hostapis()
    for idx, d in enumerate(sd.query_devices()):
        kinds = []
        if d["max_input_channels"] > 0:
            kinds.append("IN")
        if d["max_output_channels"] > 0:
            kinds.append("OUT")
        kind_s = "/".join(kinds) if kinds else "-"
        host = hosts[d["hostapi"]]["name"]
        print(f"  {idx:>4}  {kind_s:<5}  {d['name']}  [{host}]")
    print()


# ============================================================
# RECORDING (push-to-talk)
# ============================================================

def record_while_held(trigger: str, sample_rate: int, channels: int):
    """Generator. Waits for the PTT key, records while it is held, yields
    a float32 numpy array of the captured audio. Repeats forever."""
    frames: list[np.ndarray] = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    while True:
        _wait_for_press(trigger)
        frames.clear()

        with sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="float32",
            callback=callback,
        ):
            while _is_held(trigger):
                time.sleep(0.01)

        if not frames:
            continue

        audio = np.concatenate(frames, axis=0).flatten()
        # Soft normalize -- prevents overflow and keeps later peak math sane.
        peak = float(np.max(np.abs(audio))) + 1e-9
        audio = audio / max(peak, 1.0)
        yield audio


def write_wav(audio: np.ndarray, path: str, sample_rate: int) -> None:
    """Write a float32 numpy array as a 16-bit mono WAV file."""
    pcm16 = (audio * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())


def load_wav_float32(path: str) -> tuple[np.ndarray, int]:
    """Load a 16-bit PCM WAV as float32 in [-1, 1]. Returns (samples, sample_rate)."""
    with wave.open(path, "rb") as wf:
        ch = wf.getnchannels()
        sr = wf.getframerate()
        sw = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())
    if sw != 2:
        raise RuntimeError(f"Expected 16-bit PCM WAV, got sampwidth={sw}")
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32767.0
    if ch == 2:
        data = data.reshape(-1, 2)
    return data, sr


# ============================================================
# BEEP (plays on successful clipboard copy)
# ============================================================

def play_success_beep(cfg: dict[str, Any]) -> None:
    beep = cfg["beep"]
    dev = find_output_device(cfg["audio"].get("beep_output_name_contains", ""))
    sr = int(beep["sample_rate"])

    try:
        if dev is not None:
            sd.check_output_settings(device=dev, samplerate=sr, channels=1)

        n = int(sr * float(beep["duration_sec"]))
        t = np.linspace(0.0, float(beep["duration_sec"]), n, endpoint=False)
        tone = (float(beep["amplitude"]) * np.sin(2.0 * np.pi * float(beep["freq_hz"]) * t)).astype(np.float32)

        with sd.OutputStream(device=dev, samplerate=sr, channels=1, dtype="float32") as stream:
            stream.write(tone.reshape(-1, 1))
    except Exception as e:
        print(f"[WARN] beep failed: {e}")


# ============================================================
# PIPER TTS
# ============================================================

def _compute_piper_length_scale(piper_cfg: dict[str, Any]) -> str:
    """Piper's --length-scale argument. Smaller = faster speech."""
    speed = float(piper_cfg.get("speech_speed", 1.0)) or 1.0
    ls = float(piper_cfg.get("base_length_scale", 1.0)) / speed
    ls = max(float(piper_cfg["length_scale_min"]), min(float(piper_cfg["length_scale_max"]), ls))
    return f"{ls:.3f}"


def speak_piper_to_device(text: str, cfg: dict[str, Any]) -> None:
    """Synthesize `text` with Piper and play it to the configured TTS output device."""
    text = text.strip()
    if not text:
        return

    piper = cfg["piper"]
    exe = resolve_path(piper["exe"])
    model = resolve_path(piper["model"])

    if not exe.exists():
        raise FileNotFoundError(f"Piper exe not found: {exe}")
    if not model.exists():
        raise FileNotFoundError(f"Piper model not found: {model}")

    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    try:
        length_scale = _compute_piper_length_scale(piper)

        proc = subprocess.run(
            [str(exe), "-m", str(model), "-f", wav_path, "--length-scale", length_scale],
            input=text,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "Piper failed.\n"
                f"STDOUT:\n{proc.stdout}\n"
                f"STDERR:\n{proc.stderr}"
            )

        if piper.get("interrupt_current_tts", True):
            sd.stop()

        audio, sr = load_wav_float32(wav_path)
        audio = audio.astype(np.float32, copy=False)

        # Normalize to a target peak, then apply user gain, then hard-clip as a safety.
        peak = float(np.max(np.abs(audio)) + 1e-12)
        if peak > 0:
            audio = audio * (float(piper["target_peak"]) / peak)
        audio = audio * float(piper["gain"])
        audio = np.clip(audio, -1.0, 1.0)

        name_hint = cfg["audio"].get("tts_output_name_contains", "")
        dev = find_output_device(name_hint)
        if name_hint and dev is None:
            print(f"[WARN] output device containing '{name_hint}' not found -- using default")

        sd.play(audio, samplerate=sr, device=dev, blocking=True)
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass


# ============================================================
# HOTKEY ACTIONS
# ============================================================

def set_language(lang: str) -> None:
    STATE["language"] = lang or None
    print(f"[LANGUAGE] {STATE['language']}")


def set_task(task: str) -> None:
    STATE["task"] = task
    print(f"[TASK] {task}")


def toggle_mode() -> None:
    STATE["mode"] = "robot" if STATE["mode"] == "clipboard" else "clipboard"
    print(f"[MODE] {STATE['mode']}")


def register_hotkeys(hk: dict[str, Any]) -> None:
    keyboard.add_hotkey(hk["lang_en"],         lambda: set_language("en"))
    keyboard.add_hotkey(hk["lang_ko"],         lambda: set_language("ko"))
    keyboard.add_hotkey(hk["task_transcribe"], lambda: set_task("transcribe"))
    keyboard.add_hotkey(hk["task_translate"],  lambda: set_task("translate"))
    keyboard.add_hotkey(hk["toggle_mode"],     toggle_mode)


# ============================================================
# STARTUP STATUS
# ============================================================

def _print_resolved_device(label: str, name_contains: str) -> None:
    """Print one 'TTS output:' / 'Beep output:' line for the startup banner.
    Shows the single device that was picked. Run `--list-devices` to see
    the full audio device list."""
    if not name_contains:
        print(f"{label} (blank) -> using system default output")
        return

    matches = find_matching_output_devices(name_contains)
    if not matches:
        print(f"{label} {name_contains!r} -> NOT FOUND")
        return

    idx, d, host = matches[0]
    print(f"{label} [{idx}] {d['name']} [{host}]")


def print_startup_status(cfg: dict[str, Any]) -> None:
    hk = cfg["hotkeys"]
    print("\n==============================")
    print(" ten-9 voice morpher")
    print("==============================")
    print(f"PTT:         {hk['ptt']}")
    print(f"Mode toggle: {hk['toggle_mode']}")
    print(f"Mode:        {STATE['mode']}")
    print(f"Language:    {STATE['language']}")
    print(f"Task:        {STATE['task']}")

    _print_resolved_device("TTS output: ", cfg["audio"].get("tts_output_name_contains", ""))
    _print_resolved_device("Beep output:", cfg["audio"].get("beep_output_name_contains", ""))

    print(f"Piper speed: {cfg['piper']['speech_speed']}x")
    print("==============================\n")


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="ten-9 voice morpher")
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List audio devices and exit (use to configure audio.*_name_contains).",
    )
    args = parser.parse_args()

    if args.list_devices:
        list_devices()
        return

    cfg = load_config()

    # Seed runtime state from config.
    STATE["mode"] = cfg["output"]["mode"]
    STATE["language"] = cfg["whisper"]["language"] or None
    STATE["task"] = cfg["whisper"]["task"]

    register_hotkeys(cfg["hotkeys"])

    print(f"Loading Whisper model '{cfg['whisper']['model_size']}' "
          f"(device={cfg['whisper']['device']}, compute_type={cfg['whisper']['compute_type']}) ...")
    model = WhisperModel(
        cfg["whisper"]["model_size"],
        device=cfg["whisper"]["device"],
        compute_type=cfg["whisper"]["compute_type"],
    )
    print("Ready.")
    print_startup_status(cfg)

    out_cfg = cfg["output"]
    audio_cfg = cfg["audio"]
    ptt = cfg["hotkeys"]["ptt"]

    try:
        for audio in record_while_held(ptt, audio_cfg["sample_rate"], audio_cfg["channels"]):
            fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                write_wav(audio, wav_path, audio_cfg["sample_rate"])

                segments, _info = model.transcribe(
                    wav_path,
                    language=STATE["language"],
                    task=STATE["task"],
                    vad_filter=True,
                    beam_size=5,
                )
                text = "".join(seg.text for seg in segments).strip()

                if not text:
                    print("[EMPTY] no text detected\n")
                    continue

                print(f"[TEXT] {text}")

                # Copy to clipboard when configured to, or in clipboard mode.
                should_copy = out_cfg["always_copy_to_clipboard"] or STATE["mode"] == "clipboard"
                if should_copy:
                    pyperclip.copy(text)
                    print("[COPIED]")

                    should_beep = out_cfg["beep_on_copy"] and (
                        not out_cfg["beep_only_in_clipboard_mode"] or STATE["mode"] == "clipboard"
                    )
                    if should_beep:
                        play_success_beep(cfg)

                if STATE["mode"] == "robot":
                    speak_piper_to_device(text, cfg)
                    print("[SPOKE]\n")
                else:
                    print()
            finally:
                try:
                    os.remove(wav_path)
                except OSError:
                    pass
    except KeyboardInterrupt:
        print("\n[exit] keyboard interrupt")
    finally:
        _stop_mouse_listener()


if __name__ == "__main__":
    main()
