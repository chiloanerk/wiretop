import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from latency import parse_ping_summary

# Real captured `ping -c 3 1.1.1.1` output.
SUCCESS_SAMPLE = """\
PING 1.1.1.1 (1.1.1.1): 56 data bytes
64 bytes from 1.1.1.1: icmp_seq=0 ttl=57 time=18.988 ms
64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=53.768 ms
64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 time=23.922 ms

--- 1.1.1.1 ping statistics ---
3 packets transmitted, 3 packets received, 0.0% packet loss
round-trip min/avg/max/stddev = 18.988/32.226/53.768/15.365 ms
"""

FAILURE_SAMPLE = """\
PING 10.255.255.1 (10.255.255.1): 56 data bytes
Request timeout for icmp_seq 0

--- 10.255.255.1 ping statistics ---
1 packets transmitted, 0 packets received, 100.0% packet loss
"""


class ParsePingSummaryTest(unittest.TestCase):
    def test_reads_the_average_round_trip_time(self):
        self.assertAlmostEqual(parse_ping_summary(SUCCESS_SAMPLE), 32.226)

    def test_total_loss_gives_none(self):
        self.assertIsNone(parse_ping_summary(FAILURE_SAMPLE))

    def test_empty_output_gives_none(self):
        self.assertIsNone(parse_ping_summary(""))


if __name__ == "__main__":
    unittest.main()
