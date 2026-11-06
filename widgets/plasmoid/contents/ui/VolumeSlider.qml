pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    property alias from: slider.from
    property alias to: slider.to
    property alias value: slider.value
    property alias stepSize: slider.stepSize
    property real tickInterval: 0
    readonly property bool pressed: slider.pressed
    signal moved()

    spacing: Kirigami.Units.smallSpacing

    Controls.Slider {
        id: slider
        objectName: "slider"
        Layout.fillWidth: true
        snapMode: Controls.Slider.SnapAlways
        Kirigami.StyleHints.tickMarkStepSize: -1
        onMoved: root.moved()
    }

    Item {
        id: tickStrip
        objectName: "scale"
        Layout.fillWidth: true
        implicitHeight: Kirigami.Units.smallSpacing
        visible: root.tickInterval > 0 && slider.to > slider.from

        Repeater {
            model: tickStrip.visible ? Math.floor((slider.to - slider.from) / root.tickInterval) + 1 : 0

            delegate: Rectangle {
                required property int index
                readonly property real position: index * root.tickInterval / (slider.to - slider.from)
                readonly property real handleWidth: slider.handle ? slider.handle.width : 0
                objectName: "tick-" + index
                width: 2
                height: tickStrip.height
                color: Kirigami.Theme.textColor
                opacity: root.enabled ? 1 : 0.5
                x: slider.leftPadding + handleWidth / 2
                   + (slider.availableWidth - handleWidth) * (slider.mirrored ? 1 - position : position)
                   - width / 2
            }
        }
    }
}
