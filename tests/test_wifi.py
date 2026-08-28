import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wifi import parse_wifi_signal

# Real captured `system_profiler SPAirPortDataType` output (trimmed, SSID redacted).
CONNECTED_SAMPLE = """\
      Interfaces:
        en0:
          Status: Connected
          Current Network Information:
            SomeNetwork:
              PHY Mode: 802.11ax
              Channel: 36 (5GHz, 80MHz)
              Country Code: ZA
              Network Type: Infrastructure
              Security: WPA2 Personal
              Signal / Noise: -41 dBm / -90 dBm
              Transmit Rate: 1200
              MCS Index: 11
          Other Local Wi-Fi Networks:
            AnotherNetwork:
              Signal / Noise: -76 dBm / -91 dBm
"""

NOT_CONNECTED_SAMPLE = """\
      Interfaces:
        en0:
          Status: Off
"""


class ParseWifiSignalTest(unittest.TestCase):
    def test_reads_channel_and_band(self):
        info = parse_wifi_signal(CONNECTED_SAMPLE)
        self.assertEqual(info["channel"], 36)
        self.assertEqual(info["band"], "5GHz")

    def test_reads_signal_and_noise(self):
        info = parse_wifi_signal(CONNECTED_SAMPLE)
        self.assertEqual(info["signal_dbm"], -41)
        self.assertEqual(info["noise_dbm"], -90)

    def test_reads_phy_mode(self):
        self.assertEqual(parse_wifi_signal(CONNECTED_SAMPLE)["phy_mode"], "802.11ax")

    def test_ignores_other_local_networks_section(self):
        # -76/-91 belongs to a nearby network, not the connected one
        info = parse_wifi_signal(CONNECTED_SAMPLE)
        self.assertNotEqual(info["signal_dbm"], -76)

    def test_not_connected_gives_none(self):
        self.assertIsNone(parse_wifi_signal(NOT_CONNECTED_SAMPLE))


if __name__ == "__main__":
    unittest.main()
