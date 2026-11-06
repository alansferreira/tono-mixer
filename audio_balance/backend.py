"""Acesso ao PipeWire/PulseAudio via `pactl` e agrupamento de streams por instância de aplicativo."""

from __future__ import annotations

import configparser
import json
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PA_VOLUME_NORM = 65536


def _pactl(*args: str, timeout: float = 3.0) -> str:
    res = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"pactl {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def _pactl_json(*args: str):
    return json.loads(_pactl("-f", "json", *args) or "[]")


@dataclass
class Sink:
    index: int
    name: str
    description: str


@dataclass
class Stream:
    index: int
    sink: int
    corked: bool
    mute: bool
    volume: float  # % (média dos canais)
    channel_volumes: list[float]
    props: dict

    @property
    def app_name(self) -> str:
        return self.props.get("application.name") or self.props.get("node.name") or "Desconhecido"

    @property
    def binary(self) -> str:
        return self.props.get("application.process.binary") or ""

    @property
    def media_name(self) -> str:
        return self.props.get("media.name") or ""

    @property
    def role(self) -> str:
        return self.props.get("media.role") or ""

    @property
    def icon_name(self) -> str:
        return (
            self.props.get("application.icon_name")
            or self.props.get("pipewire.access.portal.app_id")
            or self.binary
            or "audio-volume-high"
        )

    @property
    def unbalanced_channels(self) -> bool:
        return bool(self.channel_volumes) and max(self.channel_volumes) - min(self.channel_volumes) > 0.5


@dataclass
class Group:
    key: str          # identifica a instância em execução
    stable_key: str   # persiste entre reinícios (perfil/caminho), usado na config
    label: str
    app_name: str
    icon_name: str
    streams: list[Stream] = field(default_factory=list)

    @property
    def volume(self) -> float:
        return max((s.volume for s in self.streams), default=0.0)

    @property
    def muted(self) -> bool:
        return bool(self.streams) and all(s.mute for s in self.streams)

    @property
    def playing(self) -> bool:
        return any(not s.corked for s in self.streams)

    @property
    def sink(self) -> int | None:
        sinks = {s.sink for s in self.streams}
        return sinks.pop() if len(sinks) == 1 else None

    @property
    def unbalanced(self) -> bool:
        vols = [s.volume for s in self.streams]
        if not vols:
            return False
        return max(vols) - min(vols) > 0.5 or any(s.unbalanced_channels for s in self.streams)


# ---------------------------------------------------------------- identificação

def _runtime_dir() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))


@lru_cache(maxsize=256)
def flatpak_instance_info(instance_id: str) -> dict:
    """Lê /run/user/UID/.flatpak/<id>/info (instance-path revela o perfil usado)."""
    path = _runtime_dir() / ".flatpak" / instance_id / "info"
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(path.read_text())
    except (OSError, configparser.Error):
        return {}
    out = {}
    if cp.has_section("Instance"):
        out.update(cp["Instance"])
    if cp.has_section("Application"):
        out["app"] = cp["Application"].get("name", "")
    return out


def profile_from_instance_path(instance_path: str | None, app_id: str) -> str | None:
    """`.../profiles/fulano@empresa/.var/app/<app_id>` -> `fulano@empresa`. Caminho padrão -> None."""
    if not instance_path:
        return None
    p = Path(instance_path)
    suffix = Path(".var") / "app" / app_id
    if p.parts[-3:] != suffix.parts:
        return p.name
    base = Path(*p.parts[:-3])
    if base == Path.home():
        return None
    return base.name


def _proc_exe(pid: int) -> str | None:
    try:
        return os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None


def _proc_ppid(pid: int) -> int | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def root_process(pid: int) -> int:
    """Sobe na árvore enquanto o pai for o mesmo executável (ex.: processos utilitários do Electron)."""
    exe = _proc_exe(pid)
    if not exe:
        return pid
    seen = set()
    while pid not in seen:
        seen.add(pid)
        ppid = _proc_ppid(pid)
        if not ppid or ppid <= 1 or _proc_exe(ppid) != exe:
            break
        pid = ppid
    return pid


def profile_from_cmdline(pid: int) -> str | None:
    try:
        argv = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    except OSError:
        return None
    argv = [a.decode(errors="replace") for a in argv if a]
    for i, a in enumerate(argv):
        for flag in ("--user-data-dir=", "--profile=", "--class="):
            if a.startswith(flag):
                return Path(a[len(flag):]).name or a[len(flag):]
        if a in ("-P", "--profile", "-profile", "--user-data-dir") and i + 1 < len(argv):
            return Path(argv[i + 1]).name
    return None


def identify(stream: Stream) -> tuple[str, str, str]:
    """Retorna (chave_runtime, chave_estavel, rótulo) do grupo ao qual o stream pertence."""
    p = stream.props
    app_name = stream.app_name
    app_id = p.get("pipewire.access.portal.app_id")
    if app_id:
        inst = p.get("pipewire.access.portal.instance_id", "")
        info = flatpak_instance_info(inst) if inst else {}
        ipath = info.get("instance-path")
        profile = profile_from_instance_path(ipath, app_id)
        if ipath:
            key = stable = f"flatpak:{app_id}:{ipath}"
        else:
            key = f"flatpak:{app_id}:{inst}"
            stable = f"flatpak:{app_id}"
        label = f"{app_name} — {profile}" if profile else app_name
        return key, stable, label

    binary = stream.binary or app_name
    try:
        pid = int(p.get("application.process.id", "0"))
    except ValueError:
        pid = 0
    if pid and Path(f"/proc/{pid}").exists():
        root = root_process(pid)
        profile = profile_from_cmdline(root)
        key = f"proc:{binary}:{root}"
        stable = f"proc:{binary}:{profile or ''}"
        label = f"{app_name} — {profile}" if profile else app_name
        return key, stable, label
    key = stable = f"app:{app_name}"
    return key, stable, app_name


# ---------------------------------------------------------------- pactl

def _parse_volume(vol: dict) -> list[float]:
    return [round(ch["value"] * 100 / PA_VOLUME_NORM, 1) for ch in vol.values()]


def list_streams() -> list[Stream]:
    out = []
    for s in _pactl_json("list", "sink-inputs"):
        chans = _parse_volume(s.get("volume") or {})
        out.append(Stream(
            index=s["index"],
            sink=s.get("sink", -1),
            corked=bool(s.get("corked")),
            mute=bool(s.get("mute")),
            volume=round(sum(chans) / len(chans), 1) if chans else 0.0,
            channel_volumes=chans,
            props=s.get("properties") or {},
        ))
    return out


def list_sinks() -> list[Sink]:
    return [Sink(s["index"], s["name"], s.get("description") or s["name"]) for s in _pactl_json("list", "sinks")]


def group_streams(streams: list[Stream], hidden_apps: list[str] = ()) -> dict[str, Group]:
    hidden = {h.lower() for h in hidden_apps}
    groups: dict[str, Group] = {}
    for st in streams:
        if st.app_name.lower() in hidden or st.binary.lower() in hidden:
            continue
        key, stable, label = identify(st)
        g = groups.get(key)
        if g is None:
            g = groups[key] = Group(key, stable, label, st.app_name, st.icon_name)
        g.streams.append(st)
    for g in groups.values():
        g.streams.sort(key=lambda s: s.index)
    return groups


def set_stream_volume(index: int, percent: float):
    _pactl("set-sink-input-volume", str(index), f"{int(round(percent * PA_VOLUME_NORM / 100))}")


def set_stream_mute(index: int, mute: bool):
    _pactl("set-sink-input-mute", str(index), "1" if mute else "0")


def move_stream(index: int, sink: str | int):
    _pactl("move-sink-input", str(index), str(sink))


def subscribe_cmd() -> list[str]:
    return ["pactl", "subscribe"]


def describe(groups: dict[str, Group]) -> str:
    lines = []
    for g in sorted(groups.values(), key=lambda g: g.label.lower()):
        state = "tocando" if g.playing else "silencioso"
        lines.append(f"{g.label}  [{len(g.streams)} stream(s), {g.volume:.0f}%, {state}{', mudo' if g.muted else ''}]")
        lines.append(f"    chave: {g.stable_key}")
        for s in g.streams:
            lines.append(f"    #{s.index} {shlex.quote(s.media_name)} vol={s.channel_volumes} sink={s.sink}"
                         f"{' corked' if s.corked else ''}{' mute' if s.mute else ''}")
    return "\n".join(lines) or "(nenhum stream de saída)"
