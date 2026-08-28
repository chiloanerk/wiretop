import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from destinations import DestinationSource, group_by_app, parse_lsof_connections

# Real captured `lsof -i -P -n` output (trimmed).
LSOF_SAMPLE = """\
COMMAND     PID  USER   FD   TYPE             DEVICE SIZE/OFF   NODE NAME
rapportd    627 admin    5u  IPv4 0xcbae5408914535fb      0t0    TCP *:61234 (LISTEN)
python3.1   746 admin   24u  IPv4 0xd1107a9c29bc3f7d      0t0    TCP 192.168.0.109:55226->99.83.136.103:443 (CLOSED)
Microsoft 29730 admin   22u  IPv4 0xe4f25d6580cd0c14      0t0    TCP 192.168.0.78:63391->4.207.247.139:443 (ESTABLISHED)
Microsoft 29730 admin   24u  IPv4 0x9b448ab48ce2c012      0t0    TCP 192.168.0.78:51673->196.44.10.146:443 (ESTABLISHED)
identitys   671 admin    7u  IPv4 0xf1d0dab7d1d7d732      0t0    UDP *:*
"""


class ParseLsofConnectionsTest(unittest.TestCase):
    def test_listening_sockets_are_skipped(self):
        connections = parse_lsof_connections(LSOF_SAMPLE)
        self.assertNotIn(627, connections)

    def test_established_connections_are_read(self):
        connections = parse_lsof_connections(LSOF_SAMPLE)
        self.assertEqual(connections[746], ["99.83.136.103"])

    def test_multiple_connections_for_one_pid_are_grouped(self):
        connections = parse_lsof_connections(LSOF_SAMPLE)
        self.assertEqual(sorted(connections[29730]), ["196.44.10.146", "4.207.247.139"])

    def test_bare_udp_sockets_are_skipped(self):
        connections = parse_lsof_connections(LSOF_SAMPLE)
        self.assertNotIn(671, connections)


class GroupByAppTest(unittest.TestCase):
    def test_groups_hosts_under_the_apps_pids(self):
        connections = {746: ["99.83.136.103"], 29730: ["4.207.247.139", "196.44.10.146"]}
        app_pids = {"Microsoft Edge": {29730}, "python3": {746}, "quiet app": {1}}
        grouped = group_by_app(connections, app_pids)
        self.assertEqual(grouped["python3"], ["99.83.136.103"])
        self.assertEqual(sorted(grouped["Microsoft Edge"]), ["196.44.10.146", "4.207.247.139"])

    def test_apps_with_no_connections_are_left_out(self):
        grouped = group_by_app({}, {"quiet app": {1}})
        self.assertNotIn("quiet app", grouped)


class ResolveHostnameTest(unittest.TestCase):
    def test_resolves_via_the_injected_resolver(self):
        source = DestinationSource(resolver=lambda ip: ("example.com", [], [ip]))
        self.assertEqual(source.resolve_hostname("1.2.3.4"), "example.com")

    def test_a_failed_lookup_falls_back_to_the_raw_ip(self):
        def always_fails(ip):
            raise OSError("no PTR record")

        source = DestinationSource(resolver=always_fails)
        self.assertEqual(source.resolve_hostname("1.2.3.4"), "1.2.3.4")

    def test_repeat_lookups_are_cached(self):
        calls = []

        def counting_resolver(ip):
            calls.append(ip)
            return (f"host-{ip}", [], [ip])

        source = DestinationSource(resolver=counting_resolver)
        source.resolve_hostname("1.2.3.4")
        source.resolve_hostname("1.2.3.4")
        self.assertEqual(calls, ["1.2.3.4"])

    def test_resolve_hosts_maps_every_ip_in_every_group(self):
        source = DestinationSource(resolver=lambda ip: (f"host-{ip}", [], [ip]))
        grouped = {"Chrome": ["1.1.1.1", "2.2.2.2"]}
        self.assertEqual(source.resolve_hosts(grouped),
                         {"Chrome": ["host-1.1.1.1", "host-2.2.2.2"]})


if __name__ == "__main__":
    unittest.main()
