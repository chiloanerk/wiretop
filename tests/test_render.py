import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netstats import AppStats
from procnames import ProcessNames, app_name
from render import (breakdown_bars, ticker_window, usage_levels, vitals_summary,
                    wifi_summary)

CHROME_HELPER = ("/Applications/Google Chrome.app/Contents/Frameworks/"
                 "Google Chrome Framework.framework/Versions/151.0.7922.175/"
                 "Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper")


def make_app(name, speed_in=0, speed_out=0, total=0, sending=0, hour=0):
    app = AppStats(name)
    app.speed_in = speed_in
    app.speed_out = speed_out
    app.total_in = total
    app.sending_seconds = sending
    app.hour_bytes = hour
    return app


class AppNameTest(unittest.TestCase):
    def test_a_helper_is_named_after_its_app(self):
        self.assertEqual(app_name(CHROME_HELPER), "Google Chrome")

    def test_reverse_dns_binary_is_named_after_its_app(self):
        path = "/Applications/Docker.app/Contents/MacOS/com.docker.backend"
        self.assertEqual(app_name(path), "Docker")

    def test_a_plain_binary_keeps_its_own_name(self):
        self.assertEqual(app_name("/usr/sbin/mDNSResponder"), "mDNSResponder")

    def test_a_login_shell_loses_its_leading_dash(self):
        self.assertEqual(app_name("-zsh"), "zsh")


class ProcessNamesTest(unittest.TestCase):
    def test_ps_runs_once_for_a_batch_of_new_pids(self):
        calls = []

        def fake_table():
            calls.append(1)
            return {1: CHROME_HELPER, 2: "/usr/sbin/mDNSResponder"}

        names = ProcessNames(read_table=fake_table)
        names.sync([1, 2])
        self.assertEqual(len(calls), 1)
        self.assertEqual(names.get(1, "?"), "Google Chrome")
        self.assertEqual(names.get(2, "?"), "mDNSResponder")

    def test_known_pids_do_not_trigger_another_lookup(self):
        calls = []

        def fake_table():
            calls.append(1)
            return {1: "/usr/sbin/mDNSResponder"}

        names = ProcessNames(read_table=fake_table)
        names.sync([1])
        names.sync([1])
        self.assertEqual(len(calls), 1)

    def test_a_vanished_process_keeps_the_name_nettop_gave(self):
        names = ProcessNames(read_table=dict)
        names.sync([999])
        self.assertEqual(names.get(999, "Google Chrome H"), "Google Chrome H")

    def test_a_vanished_process_is_not_looked_up_again(self):
        calls = []

        def fake_table():
            calls.append(1)
            return {}

        names = ProcessNames(read_table=fake_table)
        names.sync([999])
        names.sync([999])
        self.assertEqual(len(calls), 1)


class UsageLevelsTest(unittest.TestCase):
    def test_plain_rows_below_the_cutoff_get_no_level(self):
        rows = [make_app(str(i), total=100 - i) for i in range(10)]
        levels = usage_levels(rows)
        self.assertEqual(levels[4:], [None] * 6)  # only the top ~35% highlighted

    def test_the_heaviest_row_is_the_most_intense(self):
        rows = [make_app(str(i), total=100 - i) for i in range(8)]
        levels = usage_levels(rows)  # 8 rows -> top 3 highlighted
        self.assertEqual(levels[0], 3)   # heaviest row, most intense step
        self.assertGreater(levels[0], levels[1])
        self.assertGreater(levels[1], levels[2])
        self.assertIsNone(levels[3])

    def test_a_single_row_still_gets_highlighted(self):
        self.assertEqual(usage_levels([make_app("only", total=5)]), [3])

    def test_no_rows_is_fine(self):
        self.assertEqual(usage_levels([]), [])


class BreakdownBarsTest(unittest.TestCase):
    def test_shares_add_up_to_the_whole_bar(self):
        rows = [make_app("big", total=75), make_app("small", total=25)]
        lines = breakdown_bars(rows, bar_width=20)
        self.assertIn("big", lines[0])
        self.assertIn("75.0%", lines[0])
        self.assertIn("25.0%", lines[1])

    def test_no_usage_at_all_does_not_divide_by_zero(self):
        rows = [make_app("idle", total=0)]
        lines = breakdown_bars(rows)
        self.assertIn("0.0%", lines[0])

    def test_no_rows_gives_no_lines(self):
        self.assertEqual(breakdown_bars([]), [])


class VitalsSummaryTest(unittest.TestCase):
    def test_reports_the_busiest_program_and_peak_speed(self):
        rows = [make_app("Chrome", total=100)]
        line = vitals_summary(history=[10, 20, 30], rows=rows, seconds=3, elapsed=90)
        self.assertIn("Chrome", line)
        self.assertIn("01:30", line)
        self.assertIn("Samples 3", line)

    def test_copes_with_no_history_yet(self):
        line = vitals_summary(history=[], rows=[], seconds=0, elapsed=0)
        self.assertIn("Busiest -", line)


class WifiSummaryTest(unittest.TestCase):
    def test_not_connected(self):
        self.assertEqual(wifi_summary(None), "Wi-Fi: not connected")

    def test_reports_signal_and_channel(self):
        line = wifi_summary({"signal_dbm": -41, "channel": 36, "band": "5GHz"})
        self.assertIn("-41 dBm", line)
        self.assertIn("ch36 (5GHz)", line)


class TickerWindowTest(unittest.TestCase):
    def test_text_that_already_fits_is_returned_unchanged(self):
        self.assertEqual(ticker_window("short", width=20, offset=5), "short")

    def test_scrolls_by_offset(self):
        text = "abcdefgh"
        window = ticker_window(text, width=4, offset=0, gap="  ")
        self.assertEqual(window, "abcd")
        window = ticker_window(text, width=4, offset=2, gap="  ")
        self.assertEqual(window, "cdef")

    def test_wraps_around_through_the_gap(self):
        # "abc" + "  " (gap) = "abc  ", looped: "abc  abc  ..."
        window = ticker_window("abc", width=4, offset=4, gap="  ")
        self.assertEqual(window, " abc")

    def test_offset_wraps_around_the_loop_length(self):
        text, gap = "abc", "  "
        loop_length = len(text + gap)
        self.assertEqual(ticker_window(text, 3, offset=1, gap=gap),
                         ticker_window(text, 3, offset=1 + loop_length, gap=gap))

    def test_empty_text_gives_empty_window(self):
        self.assertEqual(ticker_window("", width=10, offset=0), "")

    def test_zero_width_gives_empty_window(self):
        self.assertEqual(ticker_window("hello", width=0, offset=0), "")


if __name__ == "__main__":
    unittest.main()
