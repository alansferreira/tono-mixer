import QtQuick
import QtTest
import "../plasmoid/contents/ui"
import "../plasmoid/contents/code/streams.js" as Streams

TestCase {
    id: testCase
    name: "Widget"
    width: 500
    height: 300
    visible: true
    when: windowShown

    Component {
        id: sliderComponent
        VolumeSlider {
            width: 300
            from: 0
            to: 150
            tickInterval: 30
            stepSize: 10
        }
    }

    ListModel {
        id: groups
    }

    Repeater {
        id: delegates
        model: groups
        delegate: Item {
            required property var model
            property var group: model
            Repeater {
                id: streams
                model: parent.group.streams
                delegate: Item {
                    required property var model
                    property int streamIndex: model.index
                    property real volume: model.volume
                }
            }
            property alias streamDelegates: streams
        }
    }

    SignalSpy {
        id: groupAdded
        target: delegates
        signalName: "itemAdded"
    }

    function cleanup() {
        groups.clear()
        groupAdded.clear()
    }

    function test_ticks_data() {
        return [
            {tag: "normal", maximum: 150, count: 6},
            {tag: "test-limit", maximum: 50, count: 2}
        ]
    }

    function test_ticks(data) {
        const control = createTemporaryObject(sliderComponent, testCase, {to: data.maximum})
        verify(control !== null)
        const slider = findChild(control, "slider")
        const scale = findChild(control, "scale")
        verify(slider !== null)
        verify(scale !== null)
        verify(waitForRendering(control))
        tryVerify(() => scale.y >= slider.y + slider.height)
        verify(control.implicitWidth > 0)
        verify(scale.height > 0)
        for (let index = 0; index < data.count; ++index) {
            const tick = findChild(control, "tick-" + index)
            verify(tick !== null)
            verify(tick.visible)
            verify(tick.width > 0 && tick.height > 0)
            verify(tick.x >= 0 && tick.x + tick.width <= scale.width)
            const expected = slider.leftPadding + slider.handle.width / 2
                + (slider.availableWidth - slider.handle.width) * (index * 30 / data.maximum)
            fuzzyCompare(tick.x + tick.width / 2, expected, 0.01)
            const image = grabImage(scale)
            compare(image.pixel(Math.round(tick.x), 0), tick.color)
        }
        compare(findChild(control, "tick-" + data.count), null)
    }

    function test_dragSnaps() {
        const control = createTemporaryObject(sliderComponent, testCase)
        const slider = findChild(control, "slider")
        verify(waitForRendering(control))
        mousePress(slider, slider.width * 0.37, slider.height / 2)
        mouseMove(slider, slider.width * 0.63, slider.height / 2)
        compare(control.pressed, true)
        compare(control.value % 10, 0)
        mouseRelease(slider, slider.width * 0.63, slider.height / 2)
        compare(control.pressed, false)
        compare(control.value % 10, 0)
    }

    function snapshot(volume) {
        return [{key: "app", label: "App", volume,
                 streams: [{index: 1, volume}]}]
    }

    function test_refreshPreservesDelegates() {
        Streams.syncModel(groups, snapshot(20), "key")
        compare(delegates.count, 1)
        const card = delegates.itemAt(0)
        const stream = card.streamDelegates.itemAt(0)
        verify(stream !== null)
        groupAdded.clear()
        for (let index = 0; index < 5; ++index)
            Streams.syncModel(groups, snapshot(20 + index), "key")
        compare(groupAdded.count, 0)
        compare(delegates.itemAt(0), card)
        compare(card.streamDelegates.itemAt(0), stream)
        compare(card.group.volume, 24)
        compare(stream.volume, 24)
    }

    function test_modelMembershipAndOrder() {
        const first = snapshot(20)[0]
        const second = {key: "other", label: "Other", volume: 30, streams: []}
        Streams.syncModel(groups, [first, second], "key")
        const card = delegates.itemAt(0)
        Streams.syncModel(groups, [second, first], "key")
        compare(groups.get(0).key, "other")
        compare(delegates.itemAt(1), card)
        Streams.syncModel(groups, [first], "key")
        compare(groups.count, 1)
        compare(delegates.itemAt(0), card)
        Streams.syncModel(groups, [], "key")
        compare(groups.count, 0)
    }

    function test_nestedStreamChanges() {
        Streams.syncModel(groups, [{key: "app", volume: 20, streams: []}], "key")
        const card = delegates.itemAt(0)
        const updated = [{key: "app", volume: 20, streams: [{index: 42, volume: 30}]}]
        Streams.syncModel(groups, updated, "key")
        compare(delegates.itemAt(0), card)
        compare(card.streamDelegates.count, 1)
        const stream = card.streamDelegates.itemAt(0)
        compare(stream.streamIndex, 42)
        Streams.syncModel(groups, updated, "key")
        compare(card.streamDelegates.itemAt(0), stream)
        Streams.syncModel(groups, [{key: "app", volume: 20, streams: []}], "key")
        compare(card.streamDelegates.count, 0)
        compare(delegates.itemAt(0), card)
    }
}
