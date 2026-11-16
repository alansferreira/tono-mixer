import QtQuick
import org.kde.plasma.core as PlasmaCore

PlasmaCore.Dialog {
    id: popup

    property int timeout: 3000
    property bool interacting: false

    flags: Qt.Tool | Qt.WindowDoesNotAcceptFocus
    // KWin honors the no-focus hint for notifications, but not applet popups.
    type: PlasmaCore.Dialog.Notification
    hideOnWindowDeactivate: false

    function showTemporarily() {
        visible = true
        closeTimer.restart()
    }

    onVisibleChanged: {
        if (!visible)
            closeTimer.stop()
    }

    onInteractingChanged: {
        if (visible && !interacting)
            closeTimer.restart()
    }

    property Timer closeTimer: Timer {
        id: closeTimer
        interval: popup.timeout
        onTriggered: {
            if (!popup.interacting)
                popup.visible = false
        }
    }
}
