# Changelog

## 2.1.0 - 2026-11-16

### Changed

- Automatic popups no longer take focus from the active window.
- Automatic popups close after 3 seconds. A new stream or control action restarts the timer, and slider dragging keeps the popup open until the interaction ends.
- Manually opened panels remain open as usual.

### Tests

- Added regression tests for popup focus, timeout, interaction, and manual closing.
