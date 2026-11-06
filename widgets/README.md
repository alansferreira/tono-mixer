# Tono Mixer v2: Plasma widget

A native Plasma 6 widget that brings per-instance audio controls to the panel or system tray. The original application remains installed and unchanged.

## Install

Requirements: KDE Plasma 6 with Plasma5Support's executable data engine, Python 3, `pactl`, and a working `systemd --user` session. Run from the repository root:

```bash
bash widgets/install.sh
```

The installer copies the audio backend from `windowed/`, installs the widget for the current user, and disables the original `linux-audio-balance.service` if it is installed. This prevents the two versions from restoring conflicting audio settings. It does not remove the original application.

Add **Tono Mixer** through Plasma's **Add Widgets** menu, or enable it in the system tray's settings. If it does not appear immediately, log out and back in. Click its icon to open the mixer.

For updates, run the same installer again. Updating the package does not reload QML already loaded by Plasma; log out and back in to load the new code. Do not install or update only with `kpackagetool6`, because the installer also copies the shared Python backend.

## Controls

Each app instance has a volume slider, mute button, and output selector. **Nivelar** equalizes its streams and channels. Expand a group with **+** to adjust individual streams. The widget saves group volume and output and restores them for new streams while the widget is loaded.

The panel opens automatically when a new visible output stream is detected. Streams already present when the widget starts do not trigger it. The widget checks for changes approximately every 1.5 seconds, so short-lived streams may not be detected.

Background checks update existing controls without recreating or disabling them. Group volume ticks are drawn below the slider, independently of the Qt Quick Controls style, at 30-percentage-point intervals within its range.

The widget uses its own settings in `~/.config/tono-mixer-v2/config.json`; it does not import the original application's settings. The original application's automatic popup on playback start and rename features remain available when using the original version.

## Uninstall

Remove the widget from the panel or tray, then run from the repository root:

```bash
bash widgets/uninstall.sh
```

The v2 configuration is retained. To use the original version again:

```bash
systemctl --user enable --now linux-audio-balance.service
```

## UI regression tests

Run with the Qt 6 `qmltestrunner` (its location depends on the distribution):

```bash
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software /usr/lib/qt6/bin/qmltestrunner -input widgets/tests
node widgets/tests/test_streams.js
```
