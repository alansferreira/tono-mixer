import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.plasma.plasma5support as Plasma5Support
import "../code/streams.js" as Streams

PlasmoidItem {
    id: root

    Plasmoid.icon: "audio-volume-high"
    Plasmoid.status: PlasmaCore.Types.ActiveStatus
    toolTipMainText: "Tono Mixer"
    toolTipSubText: "Áudio por instância de aplicativo"

    property var groups: []
    property var sinks: []
    property var expandedGroups: ({})
    property int maxVolume: 150
    property bool busy: false
    property bool interacting: false
    property bool initialized: false
    property bool pendingAction: false
    property int requestNumber: 0
    property string errorMessage: ""

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function run(command, key, value) {
        if (busy)
            return
        let script = decodeURIComponent(Qt.resolvedUrl("../code/bridge.py").toString().replace(/^file:\/\//, ""))
        let source = "python3 " + shellQuote(script) + " " + shellQuote(command)
        if (key !== undefined)
            source += " " + shellQuote(key) + " " + shellQuote(value)
        source += " #tono-" + (++requestNumber)
        pendingAction = command !== "status" && command !== "reset"
        busy = true
        runner.connectSource(source)
    }

    function refresh() {
        if (!busy && !interacting)
            run(initialized ? "status" : "reset")
    }

    function setExpanded(key, expanded) {
        let next = Object.assign({}, expandedGroups)
        next[key] = expanded
        expandedGroups = next
    }

    Component.onCompleted: refresh()

    Timer {
        interval: 1500
        running: true
        repeat: true
        onTriggered: root.refresh()
    }

    Plasma5Support.DataSource {
        id: runner
        engine: "executable"
        connectedSources: []

        onNewData: function(source, data) {
            disconnectSource(source)
            root.busy = false
            if (Number(data["exit code"]) !== 0) {
                root.errorMessage = String(data["stderr"] || "Falha ao consultar o áudio.")
                return
            }
            if (root.pendingAction) {
                root.errorMessage = ""
                root.refresh()
                return
            }
            try {
                let result = JSON.parse(data["stdout"])
                if (!Array.isArray(result.groups) || !Array.isArray(result.sinks))
                    throw new Error("Resposta inválida do mixer")
                if (root.initialized && Streams.hasNewStream(root.groups, result.groups))
                    root.expanded = true
                root.groups = result.groups
                root.sinks = result.sinks
                root.maxVolume = result.maxVolume
                root.initialized = true
                root.errorMessage = ""
            } catch (error) {
                root.errorMessage = String(error)
            }
        }
    }

    fullRepresentation: Item {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 20
        Layout.minimumHeight: Kirigami.Units.gridUnit * 12
        Layout.preferredWidth: Kirigami.Units.gridUnit * 24
        Layout.preferredHeight: Kirigami.Units.gridUnit * 25

        Controls.ScrollView {
            anchors.fill: parent
            contentWidth: availableWidth
            clip: true

            ColumnLayout {
                width: parent.width
                spacing: Kirigami.Units.smallSpacing

                Controls.Label {
                    text: "Tono Mixer"
                    font.bold: true
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.15
                }

                Controls.Label {
                    visible: root.errorMessage !== ""
                    text: root.errorMessage
                    color: Kirigami.Theme.negativeTextColor
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Controls.Label {
                    visible: root.initialized && root.groups.length === 0
                    text: "Nenhum aplicativo com áudio."
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Repeater {
                    model: root.groups

                    delegate: Controls.GroupBox {
                        id: groupCard
                        required property var modelData
                        property var group: modelData
                        Layout.fillWidth: true
                        title: group.label

                        ColumnLayout {
                            anchors.fill: parent

                            RowLayout {
                                Layout.fillWidth: true
                                Kirigami.Icon {
                                    source: groupCard.group.icon
                                    implicitWidth: Kirigami.Units.iconSizes.smallMedium
                                    implicitHeight: implicitWidth
                                }
                                Controls.ToolButton {
                                    icon.name: groupCard.group.muted ? "audio-volume-muted" : "audio-volume-high"
                                    enabled: !root.busy
                                    display: Controls.AbstractButton.IconOnly
                                    Controls.ToolTip.text: groupCard.group.muted ? "Ativar áudio" : "Silenciar"
                                    Controls.ToolTip.visible: hovered
                                    onClicked: root.run("mute", groupCard.group.key, groupCard.group.muted ? "0" : "1")
                                }
                                Controls.Slider {
                                    id: groupSlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: root.maxVolume
                                    stepSize: 10
                                    snapMode: Controls.Slider.SnapAlways
                                    Kirigami.StyleHints.tickMarkStepSize: 30
                                    value: groupCard.group.volume
                                    enabled: !root.busy
                                    onPressedChanged: {
                                        root.interacting = pressed
                                        if (!pressed)
                                            root.run("volume", groupCard.group.key, Math.round(value))
                                    }
                                    onMoved: if (!pressed) root.run("volume", groupCard.group.key, Math.round(value))
                                }
                                Controls.Label {
                                    text: Math.round(groupSlider.value) + "%"
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Controls.ComboBox {
                                    id: sinkSelector
                                    Layout.fillWidth: true
                                    model: root.sinks
                                    textRole: "description"
                                    currentIndex: root.sinks.findIndex(sink => sink.index === groupCard.group.sink)
                                    enabled: !root.busy
                                    onActivated: root.run("sink", groupCard.group.key, root.sinks[index].name)
                                }
                                Controls.Button {
                                    text: "Nivelar"
                                    visible: groupCard.group.unbalanced
                                    enabled: !root.busy
                                    onClicked: root.run("volume", groupCard.group.key, Math.round(groupCard.group.volume))
                                }
                                Controls.ToolButton {
                                    text: root.expandedGroups[groupCard.group.key] ? "−" : "+"
                                    Controls.ToolTip.text: "Mostrar streams individuais"
                                    Controls.ToolTip.visible: hovered
                                    onClicked: root.setExpanded(groupCard.group.key, !root.expandedGroups[groupCard.group.key])
                                }
                            }

                            Repeater {
                                model: root.expandedGroups[groupCard.group.key] ? groupCard.group.streams : []
                                delegate: RowLayout {
                                    required property var modelData
                                    property var stream: modelData
                                    Layout.fillWidth: true
                                    Controls.Label {
                                        text: stream.name
                                        elide: Text.ElideRight
                                        Layout.preferredWidth: Kirigami.Units.gridUnit * 5
                                    }
                                    Controls.ToolButton {
                                        icon.name: stream.muted ? "audio-volume-muted" : "audio-volume-medium"
                                        enabled: !root.busy
                                        onClicked: root.run("stream-mute", groupCard.group.key,
                                                            stream.index + ":" + (stream.muted ? "0" : "1"))
                                    }
                                    Controls.Slider {
                                        id: streamSlider
                                        Layout.fillWidth: true
                                        from: 0
                                        to: root.maxVolume
                                        stepSize: 1
                                        snapMode: Controls.Slider.SnapAlways
                                        Kirigami.StyleHints.tickMarkStepSize: -1
                                        value: stream.volume
                                        enabled: !root.busy
                                        onPressedChanged: {
                                            root.interacting = pressed
                                            if (!pressed)
                                                root.run("stream-volume", groupCard.group.key,
                                                         stream.index + ":" + Math.round(value))
                                        }
                                        onMoved: if (!pressed) root.run("stream-volume", groupCard.group.key,
                                                                        stream.index + ":" + Math.round(value))
                                    }
                                    Controls.Label { text: Math.round(streamSlider.value) + "%" }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
