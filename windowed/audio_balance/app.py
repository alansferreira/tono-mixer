"""Interface Qt (janela + bandeja) e serviço que observa eventos do PipeWire."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from PyQt6.QtCore import QObject, QProcess, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QMainWindow, QMenu,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QSpinBox, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget,
)

from . import APP_ID, APP_NAME, __version__, backend
from .config import CONFIG_FILE, Config

USER_HOLD_SECONDS = 0.8  # ignora atualizações externas logo após o usuário mexer num controle


def _icon(name: str, fallback: str = "audio-volume-high") -> QIcon:
    ic = QIcon.fromTheme(name)
    return ic if not ic.isNull() else QIcon.fromTheme(fallback)


def _safe(fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # stream pode sumir entre a listagem e o comando
        print(f"[{APP_ID}] {exc}", file=sys.stderr)


class VolumeControl(QWidget):
    """Slider + spinbox em %, com coalescência de alterações."""

    changed = pyqtSignal(float)

    def __init__(self, max_percent: int, parent=None):
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max_percent)
        self.slider.setPageStep(5)
        self.spin = QSpinBox()
        self.spin.setRange(0, max_percent)
        self.spin.setSuffix(" %")
        self.spin.setFixedWidth(80)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.spin)
        self._last_user = 0.0
        self._timer = QTimer(self, singleShot=True, interval=40)
        self._timer.timeout.connect(lambda: self.changed.emit(float(self.slider.value())))
        self.slider.valueChanged.connect(self._on_slider)
        self.spin.valueChanged.connect(self._on_spin)

    def _on_slider(self, v):
        self._last_user = time.monotonic()
        self.spin.blockSignals(True)
        self.spin.setValue(v)
        self.spin.blockSignals(False)
        self._timer.start()

    def _on_spin(self, v):
        self.slider.setValue(v)

    def busy(self) -> bool:
        return self.slider.isSliderDown() or time.monotonic() - self._last_user < USER_HOLD_SECONDS

    def set_value(self, v: float):
        if self.busy():
            return
        for w in (self.slider, self.spin):
            w.blockSignals(True)
            w.setValue(int(round(v)))
            w.blockSignals(False)


class StreamRow(QWidget):
    def __init__(self, ctrl: "Controller", stream: backend.Stream):
        super().__init__()
        self.ctrl = ctrl
        self.index = stream.index
        lay = QHBoxLayout(self)
        lay.setContentsMargins(24, 0, 0, 0)
        self.name = QLabel()
        self.name.setMinimumWidth(160)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.mute = QToolButton(checkable=True)
        self.mute.setAutoRaise(True)
        self.mute.toggled.connect(lambda m: (self._touch(), _safe(backend.set_stream_mute, self.index, m)))
        self.vol = VolumeControl(ctrl.cfg.settings["max_volume_percent"])
        self.vol.changed.connect(lambda v: _safe(backend.set_stream_volume, self.index, v))
        lay.addWidget(self.name, 2)
        lay.addWidget(self.mute)
        lay.addWidget(self.vol, 3)
        self._last_user = 0.0
        self.update_from(stream)

    def _touch(self):
        self._last_user = time.monotonic()

    def update_from(self, s: backend.Stream):
        state = "▶" if not s.corked else "⏸"
        self.name.setText(f"{state} #{s.index} {s.media_name}")
        self.name.setToolTip(f"{s.media_name}\ncanais: {s.channel_volumes}")
        if time.monotonic() - self._last_user > USER_HOLD_SECONDS:
            self.mute.blockSignals(True)
            self.mute.setChecked(s.mute)
            self.mute.blockSignals(False)
        self.mute.setIcon(_icon("audio-volume-muted" if s.mute else "audio-volume-medium"))
        self.vol.set_value(s.volume)


class GroupCard(QFrame):
    def __init__(self, ctrl: "Controller", group: backend.Group):
        super().__init__()
        self.ctrl = ctrl
        self.key = group.key
        self.stable_key = group.stable_key
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._flash_timer = QTimer(self, singleShot=True)
        self._flash_timer.timeout.connect(lambda: self._set_highlight(False))
        self._set_highlight(False)

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.icon = QLabel()
        self.icon.setPixmap(_icon(group.icon_name).pixmap(32, 32))
        titles = QVBoxLayout()
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: bold; font-size: 11pt;")
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet("color: palette(placeholder-text);")
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)

        self.rename_btn = QToolButton(icon=_icon("edit-rename", "document-edit"), autoRaise=True, toolTip="Renomear grupo")
        self.rename_btn.clicked.connect(self._rename)
        self.details_btn = QToolButton(checkable=True, autoRaise=True, toolTip="Mostrar streams individuais")
        self.details_btn.setArrowType(Qt.ArrowType.RightArrow)
        self.details_btn.toggled.connect(self._toggle_details)
        top.addWidget(self.icon)
        top.addLayout(titles, 1)
        top.addWidget(self.rename_btn)
        top.addWidget(self.details_btn)
        root.addLayout(top)

        row = QHBoxLayout()
        self.mute = QToolButton(checkable=True, toolTip="Mudo (todos os streams da instância)")
        self.mute.toggled.connect(self._on_mute)
        self.vol = VolumeControl(ctrl.cfg.settings["max_volume_percent"])
        self.vol.changed.connect(lambda v: ctrl.set_group_volume(self.key, v))
        self.normalize_btn = QPushButton(_icon("view-refresh"), "Nivelar")
        self.normalize_btn.setToolTip("Canais/streams com volumes diferentes: iguala todos ao valor do grupo")
        self.normalize_btn.clicked.connect(lambda: ctrl.set_group_volume(self.key, self.vol.slider.value()))
        self.sink_combo = QComboBox(toolTip="Dispositivo de saída desta instância")
        self.sink_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.sink_combo.setMinimumContentsLength(14)
        self.sink_combo.activated.connect(self._on_sink)
        row.addWidget(self.mute)
        row.addWidget(self.vol, 1)
        row.addWidget(self.normalize_btn)
        row.addWidget(self.sink_combo)
        root.addLayout(row)

        self.details = QWidget()
        self.details_lay = QVBoxLayout(self.details)
        self.details_lay.setContentsMargins(0, 0, 0, 0)
        self.details.setVisible(False)
        root.addWidget(self.details)
        self.rows: dict[int, StreamRow] = {}
        self._last_user = 0.0
        self.update_from(group)

    def _set_highlight(self, on: bool):
        color = "palette(highlight)" if on else "palette(mid)"
        width = 2 if on else 1
        self.setStyleSheet(f"QFrame#card {{ border: {width}px solid {color}; border-radius: 8px; }}")

    def flash(self):
        self._set_highlight(True)
        self._flash_timer.start(4000)

    def _rename(self):
        current = self.ctrl.cfg.group(self.stable_key).get("label") or self.title.text()
        text, ok = QInputDialog.getText(self, "Renomear grupo", "Nome (vazio = automático):", text=current)
        if ok:
            self.ctrl.cfg.set_group_value(self.stable_key, "label", text.strip() or None)
            self.ctrl.refresh()

    def _toggle_details(self, on: bool):
        self.details_btn.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)
        self.details.setVisible(on)

    def _on_mute(self, m: bool):
        self._last_user = time.monotonic()
        self.ctrl.set_group_mute(self.key, m)

    def _on_sink(self, idx: int):
        name = self.sink_combo.itemData(idx)
        if name:
            self.ctrl.move_group(self.key, name)

    def update_from(self, g: backend.Group):
        saved = self.ctrl.cfg.groups.get(g.stable_key, {})
        self.title.setText(saved.get("label") or g.label)
        self.title.setToolTip(g.stable_key)
        n = len(g.streams)
        state = "tocando" if g.playing else "silencioso"
        self.subtitle.setText(f"{n} stream{'s' if n != 1 else ''} · {state}")
        self.vol.set_value(g.volume)
        if time.monotonic() - self._last_user > USER_HOLD_SECONDS:
            self.mute.blockSignals(True)
            self.mute.setChecked(g.muted)
            self.mute.blockSignals(False)
        self.mute.setIcon(_icon("audio-volume-muted" if g.muted else "audio-volume-high"))
        self.normalize_btn.setVisible(g.unbalanced)

        self.sink_combo.blockSignals(True)
        self.sink_combo.clear()
        if g.sink is None:
            self.sink_combo.addItem("(várias saídas)", None)
        for sk in self.ctrl.sinks:
            self.sink_combo.addItem(sk.description, sk.name)
            if sk.index == g.sink:
                self.sink_combo.setCurrentIndex(self.sink_combo.count() - 1)
        self.sink_combo.blockSignals(False)

        live = {s.index for s in g.streams}
        for idx in list(self.rows):
            if idx not in live:
                self.rows.pop(idx).deleteLater()
        for s in g.streams:
            row = self.rows.get(s.index)
            if row is None:
                row = self.rows[s.index] = StreamRow(self.ctrl, s)
                self.details_lay.addWidget(row)
            else:
                row.update_from(s)


class MainWindow(QMainWindow):
    def __init__(self, ctrl: "Controller"):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_icon("audio-volume-high"))
        self.resize(640, 420)

        central = QWidget()
        outer = QVBoxLayout(central)
        bar = QHBoxLayout()
        self.summary = QLabel()
        level_all = QPushButton(_icon("view-refresh"), "Nivelar todos")
        level_all.setToolTip("Em cada grupo, iguala todos os streams/canais ao volume do grupo")
        level_all.clicked.connect(ctrl.normalize_all)
        self.pin = QCheckBox("Manter no topo")
        self.pin.toggled.connect(self._set_on_top)
        bar.addWidget(self.summary, 1)
        bar.addWidget(self.pin)
        bar.addWidget(level_all)
        outer.addLayout(bar)

        self.scroll = QScrollArea(widgetResizable=True)
        self.list_widget = QWidget()
        self.list_lay = QVBoxLayout(self.list_widget)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        outer.addWidget(self.scroll, 1)
        self.empty = QLabel("Nenhum aplicativo reproduzindo áudio.", alignment=Qt.AlignmentFlag.AlignCenter)
        self.list_lay.insertWidget(0, self.empty)
        self.setCentralWidget(central)

        self.cards: dict[str, GroupCard] = {}
        self._auto_hide = QTimer(self, singleShot=True)
        self._auto_hide.timeout.connect(self._maybe_auto_hide)

    # --- janela
    def _set_on_top(self, on: bool):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        if visible:
            self.show()

    def closeEvent(self, ev):
        if self.ctrl.quitting:
            ev.accept()
            return
        ev.ignore()
        self.hide()

    def enterEvent(self, ev):
        self._auto_hide.stop()
        super().enterEvent(ev)

    def _maybe_auto_hide(self):
        if self.underMouse() or QApplication.activeWindow() is self:
            return
        self.hide()

    def hideEvent(self, ev):
        self._auto_hide.stop()
        if self.pin.isChecked() and not self.ctrl.user_pinned:
            self.pin.blockSignals(True)
            self.pin.setChecked(False)
            self.pin.blockSignals(False)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        super().hideEvent(ev)

    def bring_up(self, focus_key: str | None = None, auto: bool = False):
        was_hidden = not self.isVisible() or self.isMinimized()
        if auto and was_hidden and self.ctrl.cfg.settings.get("keep_on_top_when_popup") and not self.pin.isChecked():
            self.pin.blockSignals(True)
            self.pin.setChecked(True)
            self.pin.blockSignals(False)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if auto and was_hidden:
            secs = int(self.ctrl.cfg.settings.get("auto_hide_seconds") or 0)
            if secs > 0:
                self._auto_hide.start(secs * 1000)
        if focus_key and focus_key in self.cards:
            card = self.cards[focus_key]
            self.scroll.ensureWidgetVisible(card)
            card.flash()

    def toggle(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.bring_up()

    # --- conteúdo
    def update_groups(self, groups: dict[str, backend.Group]):
        for key in list(self.cards):
            if key not in groups:
                self.cards.pop(key).deleteLater()
        ordered = sorted(groups.values(), key=lambda g: (g.app_name.lower(), g.label.lower()))
        for pos, g in enumerate(ordered):
            card = self.cards.get(g.key)
            if card is None:
                card = self.cards[g.key] = GroupCard(self.ctrl, g)
            else:
                card.update_from(g)
            if self.list_lay.indexOf(card) != pos + 1:
                self.list_lay.insertWidget(pos + 1, card)
        self.empty.setVisible(not groups)
        playing = sum(1 for g in groups.values() if g.playing)
        self.summary.setText(f"{len(groups)} instância(s) com áudio · {playing} tocando")


class Controller(QObject):
    def __init__(self, app: QApplication, start_hidden: bool):
        super().__init__()
        self.app = app
        self.cfg = Config()
        self.quitting = False
        self.user_pinned = False
        self.sinks: list[backend.Sink] = []
        self.groups: dict[str, backend.Group] = {}
        self._known: dict[int, bool] = {}   # stream index -> corked
        self._seeded = False
        self._last_popup: dict[str, float] = {}

        self.win = MainWindow(self)
        self.win.pin.toggled.connect(lambda on: setattr(self, "user_pinned", on))
        self._setup_tray()

        self._refresh_timer = QTimer(self, singleShot=True, interval=120)
        self._refresh_timer.timeout.connect(self.refresh)
        self._start_subscribe()
        # rede de segurança caso algum evento se perca
        self._poll = QTimer(self, interval=5000)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

        self.refresh()
        if not start_hidden:
            self.win.bring_up()

    # --- bandeja
    def _setup_tray(self):
        self.tray = QSystemTrayIcon(_icon("audio-volume-high"), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu()
        menu.addAction("Abrir", self.win.bring_up)
        menu.addSeparator()
        for key, text in (
            ("popup_on_new_stream", "Abrir ao surgir novo stream de áudio"),
            ("popup_on_playback_start", "Abrir quando um app começar a tocar"),
            ("restore_group_volume", "Reaplicar volume/saída salvos da instância"),
            ("keep_on_top_when_popup", "Popup sempre no topo"),
        ):
            act = QAction(text, menu, checkable=True, checked=bool(self.cfg.settings.get(key)))
            act.toggled.connect(lambda on, k=key: self._set_setting(k, on))
            menu.addAction(act)
        menu.addAction("Editar configuração…", self._edit_config)
        menu.addSeparator()
        menu.addAction("Sair", self.quit)
        self.tray.setContextMenu(menu)
        self._tray_menu = menu
        self.tray.activated.connect(
            lambda r: self.win.toggle() if r in (QSystemTrayIcon.ActivationReason.Trigger,
                                                  QSystemTrayIcon.ActivationReason.MiddleClick) else None)
        self.tray.show()

    def _set_setting(self, key, value):
        self.cfg.settings[key] = value
        self.cfg.save()

    def _edit_config(self):
        self.cfg.save()
        subprocess.Popen(["xdg-open", str(CONFIG_FILE)])

    def quit(self):
        self.quitting = True
        if self._sub.state() != QProcess.ProcessState.NotRunning:
            self._sub.kill()
            self._sub.waitForFinished(1000)
        self.app.quit()

    # --- eventos do PipeWire
    def _start_subscribe(self):
        self._sub = QProcess(self)
        self._sub.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._sub.readyReadStandardOutput.connect(self._on_events)
        self._sub.finished.connect(self._on_sub_finished)
        cmd = backend.subscribe_cmd()
        self._sub.start(cmd[0], cmd[1:])

    def _on_sub_finished(self, *_):
        if not self.quitting:
            QTimer.singleShot(2000, self._start_subscribe)

    def _on_events(self):
        data = bytes(self._sub.readAllStandardOutput()).decode(errors="replace")
        if any(t in data for t in ("sink-input", "on sink #", "server")):
            self._refresh_timer.start()

    # --- estado
    def refresh(self):
        try:
            streams = backend.list_streams()
            self.sinks = backend.list_sinks()
        except Exception as exc:
            print(f"[{APP_ID}] falha ao consultar pactl: {exc}", file=sys.stderr)
            return
        s = self.cfg.settings
        groups = backend.group_streams(streams, s.get("hidden_apps", []))
        popup_key = None
        restored = False
        current = {}
        for g in groups.values():
            saved = self.cfg.groups.get(g.stable_key, {})
            for st in g.streams:
                current[st.index] = st.corked
                if not self._seeded:
                    continue
                prev = self._known.get(st.index)
                is_new = prev is None
                if is_new and s.get("restore_group_volume"):
                    restored |= self._restore(st, saved)
                started = (is_new and not st.corked) or (prev is True and not st.corked)
                if self._wants_popup(g, st) and (
                    (is_new and s.get("popup_on_new_stream")) or (started and s.get("popup_on_playback_start"))
                ):
                    popup_key = popup_key or g.key
        self._known = current
        self._seeded = True
        self.groups = groups
        self.win.update_groups(groups)
        playing = [g for g in groups.values() if g.playing]
        self.tray.setToolTip(f"{APP_NAME}\n" + ("\n".join(f"▶ {self._label(g)} {g.volume:.0f}%" for g in playing)
                                                 or "nada tocando"))
        if popup_key:
            cooldown = float(s.get("popup_cooldown_seconds") or 0)
            now = time.monotonic()
            if now - self._last_popup.get(popup_key, -1e9) >= cooldown:
                self._last_popup[popup_key] = now
                self.win.bring_up(popup_key, auto=True)
        if restored:
            self._refresh_timer.start()

    def _label(self, g: backend.Group) -> str:
        return self.cfg.groups.get(g.stable_key, {}).get("label") or g.label

    def _wants_popup(self, g: backend.Group, st: backend.Stream) -> bool:
        s = self.cfg.settings
        if s.get("ignore_event_sounds") and st.role in ("event", "notification", "a11y"):
            return False
        blocked = {a.lower() for a in s.get("no_popup_apps", [])}
        return not ({g.app_name.lower(), st.binary.lower(), self._label(g).lower()} & blocked)

    def _restore(self, st: backend.Stream, saved: dict) -> bool:
        changed = False
        vol = saved.get("volume")
        if vol is not None and abs(st.volume - vol) > 0.5:
            _safe(backend.set_stream_volume, st.index, vol)
            changed = True
        sink = saved.get("sink")
        if sink and any(sk.name == sink for sk in self.sinks) and \
                not any(sk.name == sink and sk.index == st.sink for sk in self.sinks):
            _safe(backend.move_stream, st.index, sink)
            changed = True
        return changed

    # --- ações
    def set_group_volume(self, key: str, percent: float):
        g = self.groups.get(key)
        if not g:
            return
        for st in g.streams:
            _safe(backend.set_stream_volume, st.index, percent)
        self.cfg.set_group_value(g.stable_key, "volume", percent)

    def set_group_mute(self, key: str, mute: bool):
        g = self.groups.get(key)
        if g:
            for st in g.streams:
                _safe(backend.set_stream_mute, st.index, mute)

    def move_group(self, key: str, sink_name: str):
        g = self.groups.get(key)
        if not g:
            return
        for st in g.streams:
            _safe(backend.move_stream, st.index, sink_name)
        self.cfg.set_group_value(g.stable_key, "sink", sink_name)
        self._refresh_timer.start()

    def normalize_all(self):
        for key, g in self.groups.items():
            if g.unbalanced:
                card = self.win.cards.get(key)
                self.set_group_volume(key, card.vol.slider.value() if card else g.volume)
        self._refresh_timer.start()


def _server_name() -> str:
    return f"{APP_ID}-{os.getuid()}"


def _notify_running_instance(message: bytes) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(300):
        return False
    sock.write(message)
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="audio-balance", description="Agrupa e calibra saídas de áudio por instância")
    ap.add_argument("--hidden", action="store_true", help="inicia só na bandeja (modo serviço)")
    ap.add_argument("--list", action="store_true", help="lista os grupos detectados e sai")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)

    if args.list:
        cfg = Config()
        print(backend.describe(backend.group_streams(backend.list_streams(), cfg.settings.get("hidden_apps", []))))
        return 0

    QApplication.setDesktopFileName(APP_ID)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if _notify_running_instance(b"hidden" if args.hidden else b"show"):
        return 0
    QLocalServer.removeServer(_server_name())
    server = QLocalServer()
    server.listen(_server_name())

    ctrl = Controller(app, start_hidden=args.hidden)

    def on_conn():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def handle():
            if bytes(conn.readAll()).strip() != b"hidden":
                ctrl.win.bring_up()
        conn.readyRead.connect(handle)
        conn.disconnected.connect(conn.deleteLater)
    server.newConnection.connect(on_conn)
    return app.exec()
