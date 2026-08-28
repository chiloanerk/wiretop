import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interfaces import classify_interface, parse_netstat_ib, parse_wifi_interface_name

# Real captured `netstat -ib` output (trimmed to the interesting rows).
NETSTAT_SAMPLE = """\
Name       Mtu   Network       Address            Ipkts Ierrs     Ibytes    Opkts Oerrs     Obytes  Coll
lo0        16384 <Link#1>                        573986     0  629942739   573986     0  629942739     0
lo0        16384 127           localhost         573986     -  629942739   573986     -  629942739     -
gif0*      1280  <Link#2>                             0     0          0        0     0          0     0
en0        1500  <Link#12>   12:f3:e1:e8:ca:f2 15048725     0 15193744936  8560820     0 4130130705     0
en0        1500  reles-macbo fe80:c::14e5:236a 15048725     - 15193744936  8560820     - 4130130705     -
utun0      1380  <Link#16>                            0     0          0       64     0      10701     0
"""

# Real captured `system_profiler SPAirPortDataType` output (trimmed).
AIRPORT_SAMPLE = """\
Wi-Fi:

      Software Versions:
          CoreWLAN: 16.0 (1657)
      Interfaces:
        en0:
          Card Type: Wi-Fi  (0x14E4, 0x4378)
          MAC Address: 12:f3:e1:e8:ca:f2
        en5:
          Card Type: Wi-Fi  (unused)
"""


class ParseNetstatIbTest(unittest.TestCase):
    def test_only_link_rows_are_kept(self):
        totals = parse_netstat_ib(NETSTAT_SAMPLE)
        self.assertEqual(set(totals), {"lo0", "gif0", "en0", "utun0"})

    def test_bytes_in_and_out_are_read_correctly(self):
        totals = parse_netstat_ib(NETSTAT_SAMPLE)
        self.assertEqual(totals["en0"], (15193744936, 4130130705))

    def test_a_trailing_star_is_stripped_from_the_name(self):
        totals = parse_netstat_ib(NETSTAT_SAMPLE)
        self.assertIn("gif0", totals)
        self.assertNotIn("gif0*", totals)


class ParseWifiInterfaceNameTest(unittest.TestCase):
    def test_finds_the_first_interface_under_interfaces(self):
        self.assertEqual(parse_wifi_interface_name(AIRPORT_SAMPLE), "en0")

    def test_no_interfaces_section_gives_none(self):
        self.assertIsNone(parse_wifi_interface_name("Wi-Fi:\n  Status: Connected\n"))


class ClassifyInterfaceTest(unittest.TestCase):
    def test_the_confirmed_wifi_interface_is_labeled_wifi(self):
        self.assertEqual(classify_interface("en0", wifi_name="en0"), "Wi-Fi")

    def test_other_en_interfaces_are_ethernet(self):
        self.assertEqual(classify_interface("en1", wifi_name="en0"), "Ethernet")

    def test_utun_is_vpn(self):
        self.assertEqual(classify_interface("utun0", wifi_name="en0"), "VPN")

    def test_loopback_is_labeled(self):
        self.assertEqual(classify_interface("lo0", wifi_name="en0"), "Loopback")

    def test_anything_else_is_other(self):
        self.assertEqual(classify_interface("bridge0", wifi_name="en0"), "Other")


if __name__ == "__main__":
    unittest.main()
