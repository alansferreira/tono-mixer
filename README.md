# Tono Mixer

### One mixer for every app instance. Your audio, your way.

Music, videos, notifications, and other sounds can all play at once — and you may not want them at the same volume or coming from the same device. Tono Mixer groups the audio streams from each app instance so you can manage them without affecting everything else.

It works with many kinds of apps, including Firefox, Chrome, VLC, Teams, and Slack.

## Choose your interface

| Version | Description | Documentation |
|---|---|---|
| **Windowed** | A desktop window and system tray app, with automatic popups and per-instance audio controls. | [Windowed README](windowed/README.md) |
| **Plasma widget** | A native Plasma 6 mixer for the panel or system tray. | [Widget README](widgets/README.md) |

Both use the audio backend in `windowed/audio_balance`. The widget installer copies the backend into its installed package, so it does not depend on the repository remaining available after installation.

Each version keeps its own settings. The widget installer disables the windowed service to prevent the two from restoring conflicting audio settings; it does not uninstall the windowed app.

## Repository layout

```text
windowed/   Desktop application, audio backend, and service packaging
widgets/    Plasma widget, installation scripts, and tests
```
