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
    property var actionQueue: []
    readonly property bool controlsBusy: (busy && pendingAction) || actionQueue.length > 0
    property int requestNumber: 0
    property string errorMessage: ""

    function shellQuote(value) {
        return "'" + String(value).replace(/'/g, "'\\''") + "'"
    }

    function run(command, key, value) {
        if (busy) {
            if (command !== "status" && command !== "reset")
                actionQueue = actionQueue.concat([{command, key, value}])
            return
        }
        let script = decodeURIComponent(Qt.resolvedUrl("../code/bridge.py").toString().replace(/^file:\/\//, ""))
        let source = "python3 " + shellQuote(script) + " " + shellQuote(command)
        if (key !== undefined)
            source += " " + shellQuote(key) + " " + shellQuote(value)
        source += " #tono-" + (++requestNumber)
        pendingAction = command !== "status" && command !== "reset"
        busy = true
        runner.connectSource(source)
    }

    function completeRequest(refreshAfterAction = true) {
        busy = false
        if (actionQueue.length > 0) {
            const action = actionQueue[0]
            actionQueue = actionQueue.slice(1)
            run(action.command, action.key, action.value)
        } else if (pendingAction && refreshAfterAction) {
            refresh()
        }
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

    ListModel {
        id: groupModel
    }

    ListModel {
        id: sinkModel
    }

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
            if (Number(data["exit code"]) !== 0) {
                root.errorMessage = String(data["stderr"] || "Falha ao consultar o áudio.")
                root.completeRequest(false)
                return
            }
            if (root.pendingAction) {
                root.errorMessage = ""
                root.completeRequest()
                return
            }
            if (root.interacting || root.actionQueue.length > 0) {
                root.completeRequest()
                return
            }
            try {
                let result = JSON.parse(data["stdout"])
                if (!Array.isArray(result.groups) || !Array.isArray(result.sinks))
                    throw new Error("Resposta inválida do mixer")
                if (root.initialized && Streams.hasNewStream(root.groups, result.groups))
                    root.expanded = true
                Streams.syncModel(groupModel, result.groups, "key")
                Streams.syncModel(sinkModel, result.sinks, "index")
                root.groups = result.groups
                root.sinks = result.sinks
                root.maxVolume = result.maxVolume
                root.initialized = true
                root.errorMessage = ""
            } catch (error) {
                root.errorMessage = String(error)
            }
            root.completeRequest()
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
                    model: groupModel

                    delegate: Controls.GroupBox {
                        id: groupCard
                        required property var model
                        property var group: model
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
                                    enabled: !root.controlsBusy
                                    display: Controls.AbstractButton.IconOnly
                                    Controls.ToolTip.text: groupCard.group.muted ? "Ativar áudio" : "Silenciar"
                                    Controls.ToolTip.visible: hovered
                                    onClicked: root.run("mute", groupCard.group.key, groupCard.group.muted ? "0" : "1")
                                }
                                VolumeSlider {
                                    id: groupSlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: root.maxVolume
                                    tickInterval: root.maxVolume - (root.maxVolume / 3)
                                    value: groupCard.group.volume
                                    enabled: !root.controlsBusy
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
                                    model: sinkModel
                                    textRole: "description"
                                    currentIndex: root.sinks.findIndex(sink => sink.index === groupCard.group.sink)
                                    enabled: !root.controlsBusy
                                    onActivated: root.run("sink", groupCard.group.key, root.sinks[index].name)
                                }
                                Controls.Button {
                                    text: "Nivelar"
                                    visible: groupCard.group.unbalanced
                                    enabled: !root.controlsBusy
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
                                model: groupCard.group.streams
                                delegate: RowLayout {
                                    required property var model
                                    property var stream: model
                                    visible: !!root.expandedGroups[groupCard.group.key]
                                    Layout.fillWidth: true
                                    Controls.ToolButton {
                                        icon.name: stream.muted ? "audio-volume-muted" : "audio-volume-medium"
                                        enabled: !root.controlsBusy
                                        onClicked: root.run("stream-mute", groupCard.group.key,
                                                            stream.index + ":" + (stream.muted ? "0" : "1"))
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: Kirigami.Units.smallSpacing

                                        VolumeSlider {
                                            id: streamSlider
                                            Layout.fillWidth: true
                                            from: 0
                                            to: root.maxVolume
                                            tickInterval: root.maxVolume - (root.maxVolume / 3)
                                            stepSize: 1
                                            value: stream.volume
                                            enabled: !root.controlsBusy
                                            onPressedChanged: {
                                                root.interacting = pressed
                                                if (!pressed)
                                                    root.run("stream-volume", groupCard.group.key,
                                                             stream.index + ":" + Math.round(value))
                                            }
                                            onMoved: if (!pressed) root.run("stream-volume", groupCard.group.key,
                                                                            stream.index + ":" + Math.round(value))
                                        }
                                        Controls.Label {
                                            Layout.fillWidth: true
                                            text: stream.name
                                            elide: Text.ElideRight
                                        }
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
