import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


BRIDGE_PATH = Path(__file__).resolve().parents[1] / "plasmoid/contents/code/bridge.py"
spec = importlib.util.spec_from_file_location("tono_v2_bridge", BRIDGE_PATH)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
backend = bridge.backend


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.known = Path(self.temporary.name) / "streams.json"
        self.known_patch = patch.object(bridge, "KNOWN_FILE", self.known)
        self.known_patch.start()
        self.addCleanup(self.known_patch.stop)
        self.streams = [
            backend.Stream(1, 10, False, False, 40, [40, 40], {"application.name": "Player"}),
            backend.Stream(2, 10, False, False, 60, [60, 60], {"application.name": "Player"}),
        ]
        self.sinks = [backend.Sink(10, "headphones", "Headphones"), backend.Sink(20, "speakers", "Speakers")]
        self.patches = [
            patch.object(backend, "list_streams", return_value=self.streams),
            patch.object(backend, "list_sinks", return_value=self.sinks),
            patch.object(backend, "set_stream_volume"),
            patch.object(backend, "set_stream_mute"),
            patch.object(backend, "move_stream"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_group_actions_apply_to_all_streams_and_save_choices(self):
        config = {}
        bridge.apply_action(config, "volume", "app:Player", "75")
        self.assertEqual(backend.set_stream_volume.call_args_list, [unittest.mock.call(1, 75), unittest.mock.call(2, 75)])
        self.assertEqual(config["app:Player"]["volume"], 75)
        bridge.apply_action(config, "sink", "app:Player", "speakers")
        self.assertEqual(backend.move_stream.call_count, 2)
        self.assertEqual(config["app:Player"]["sink"], "speakers")
        bridge.apply_action(config, "mute", "app:Player", "1")
        self.assertEqual(backend.set_stream_mute.call_count, 2)

    def test_snapshot_restores_only_new_streams(self):
        config = {"app:Player": {"volume": 80, "sink": "speakers"}}
        result = bridge.snapshot(config, reset=True)
        self.assertEqual(result["groups"][0]["volume"], 60)
        self.assertTrue(result["groups"][0]["unbalanced"])
        backend.set_stream_volume.assert_not_called()
        self.streams.append(backend.Stream(3, 10, False, False, 30, [30, 30], {"application.name": "Player"}))
        bridge.snapshot(config)
        backend.set_stream_volume.assert_called_once_with(3, 80)
        backend.move_stream.assert_called_once_with(3, "speakers")
        bridge.snapshot(config)
        backend.set_stream_volume.assert_called_once()

    def test_stream_controls_validate_membership_and_bounds(self):
        bridge.apply_action({}, "stream-volume", "app:Player", "2:50")
        backend.set_stream_volume.assert_called_once_with(2, 50)
        with self.assertRaises(ValueError):
            bridge.apply_action({}, "stream-mute", "app:Player", "3:1")
        with self.assertRaises(ValueError):
            bridge.apply_action({}, "volume", "app:Player", "151")
        with self.assertRaises(ValueError):
            bridge.apply_action({}, "sink", "app:Player", "missing")


if __name__ == "__main__":
    unittest.main()
