#!/usr/bin/env python3
"""Bridge between the Plasma widget and the shared pactl backend."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
if not (HERE.parent / "audio_balance").exists():
    sys.path.insert(0, str(HERE.parents[4] / "windowed"))

from audio_balance import backend

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "tono-mixer-v2"
RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "tono-mixer-v2"
CONFIG_FILE = CONFIG_DIR / "config.json"
KNOWN_FILE = RUNTIME_DIR / "streams.json"
HIDDEN_APPS = ["speech-dispatcher-dummy", "sd_dummy", "pactl"]
MAX_VOLUME = 150


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.replace(path)


def snapshot(config, reset=False):
    streams = backend.list_streams()
    sinks = backend.list_sinks()
    groups = backend.group_streams(streams, HIDDEN_APPS)
    previous = set() if reset else set(read_json(KNOWN_FILE, []))
    if not reset:
        sink_names = {sink.name: sink.index for sink in sinks}
        for group in groups.values():
            saved = config.get(group.stable_key, {})
            for stream in group.streams:
                if stream.index in previous:
                    continue
                volume = saved.get("volume")
                if volume is not None and abs(stream.volume - volume) > 0.5:
                    backend.set_stream_volume(stream.index, volume)
                sink = saved.get("sink")
                if sink in sink_names and stream.sink != sink_names[sink]:
                    backend.move_stream(stream.index, sink)
    write_json(KNOWN_FILE, [stream.index for stream in streams])
    return {
        "maxVolume": MAX_VOLUME,
        "sinks": [{"index": s.index, "name": s.name, "description": s.description} for s in sinks],
        "groups": [{
            "key": g.key,
            "label": config.get(g.stable_key, {}).get("label") or g.label,
            "icon": g.icon_name,
            "volume": g.volume,
            "muted": g.muted,
            "playing": g.playing,
            "sink": g.sink,
            "unbalanced": g.unbalanced,
            "streams": [{
                "index": s.index,
                "name": s.media_name or f"Stream #{s.index}",
                "volume": s.volume,
                "muted": s.mute,
            } for s in g.streams],
        } for g in sorted(groups.values(), key=lambda item: item.label.lower())],
    }


def apply_action(config, action, key, value):
    groups = backend.group_streams(backend.list_streams(), HIDDEN_APPS)
    group = groups.get(key)
    if group is None:
        raise ValueError("The audio group is no longer available.")
    if action == "volume":
        volume = float(value)
        if not 0 <= volume <= MAX_VOLUME:
            raise ValueError(f"Volume must be between 0 and {MAX_VOLUME}.")
        for stream in group.streams:
            backend.set_stream_volume(stream.index, volume)
        config.setdefault(group.stable_key, {})["volume"] = volume
    elif action == "mute":
        if value not in ("0", "1"):
            raise ValueError("Invalid mute value.")
        for stream in group.streams:
            backend.set_stream_mute(stream.index, value == "1")
    elif action == "sink":
        if value not in {sink.name for sink in backend.list_sinks()}:
            raise ValueError("The output device is no longer available.")
        for stream in group.streams:
            backend.move_stream(stream.index, value)
        config.setdefault(group.stable_key, {})["sink"] = value
    elif action in ("stream-volume", "stream-mute"):
        index_string, separator, stream_value = value.partition(":")
        if not separator:
            raise ValueError("Missing stream value.")
        index = int(index_string)
        if index not in {stream.index for stream in group.streams}:
            raise ValueError("The audio stream is no longer available.")
        if action == "stream-volume":
            volume = float(stream_value)
            if not 0 <= volume <= MAX_VOLUME:
                raise ValueError(f"Volume must be between 0 and {MAX_VOLUME}.")
            backend.set_stream_volume(index, volume)
        else:
            if stream_value not in ("0", "1"):
                raise ValueError("Invalid mute value.")
            backend.set_stream_mute(index, stream_value == "1")
    else:
        raise ValueError("Unknown action.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["status", "reset", "volume", "mute", "sink", "stream-volume", "stream-mute"])
    parser.add_argument("key", nargs="?")
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIR / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config = read_json(CONFIG_FILE, {})
        if args.command in ("status", "reset"):
            print(json.dumps(snapshot(config, reset=args.command == "reset"), ensure_ascii=False))
        else:
            if args.key is None or args.value is None:
                parser.error("an action requires a group key and value")
            apply_action(config, args.command, args.key, args.value)
            write_json(CONFIG_FILE, config)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Tono Mixer: {exc}", file=sys.stderr)
        sys.exit(1)
