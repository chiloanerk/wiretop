import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netstats import (HOUR_SECONDS, AppStats, Tracker, duration,
                      format_megabytes, is_anomalous, mbps, megabytes,
                      parse_sample, recent_speed_history)
from nettop_source import split_samples


def plain_names(pid, fallback):
    return fallback


class ParseSampleTest(unittest.TestCase):
    def test_reads_name_bytes_in_and_out(self):
        sample = parse_sample(["Mail.29903,406514,37508,"])
        self.assertEqual(sample, {29903: ("Mail", 406514, 37508)})

    def test_splits_pid_off_the_end_of_a_dotted_name(self):
        # a real process on this machine is named "2.1.247"
        sample = parse_sample(["2.1.247.17891,99357,277893,"])
        self.assertEqual(sample, {17891: ("2.1.247", 99357, 277893)})

    def test_ignores_the_carriage_return_a_pty_adds(self):
        sample = parse_sample(["apsd.374,5691,15679,\r"])
        self.assertEqual(sample, {374: ("apsd", 5691, 15679)})

    def test_skips_headers_and_junk(self):
        self.assertEqual(parse_sample([",bytes_in,bytes_out,", "", "nonsense"]), {})


class SplitSamplesTest(unittest.TestCase):
    def test_header_lines_separate_samples(self):
        lines = [
            ",bytes_in,bytes_out,",
            "Mail.1,100,0,",
            ",bytes_in,bytes_out,",
            "Mail.1,7,3,",
        ]
        samples = split_samples(lines)
        self.assertEqual(len(samples), 2)
        self.assertEqual(samples[0][1], ("Mail", 100, 0))
        self.assertEqual(samples[1][1], ("Mail", 7, 3))


class TrackerTest(unittest.TestCase):
    def test_helpers_are_added_up_under_one_program(self):
        tracker = Tracker()
        sample = {1: ("helper", 100, 50), 2: ("helper", 25, 25)}
        tracker.add_sample(sample, lambda pid, fallback: "Google Chrome")
        app = tracker.apps["Google Chrome"]
        self.assertEqual(app.total_in, 125)
        self.assertEqual(app.total_out, 75)

    def test_speed_is_only_the_latest_second(self):
        tracker = Tracker()
        tracker.add_sample({1: ("Mail", 900, 100)}, plain_names)
        tracker.add_sample({1: ("Mail", 5, 5)}, plain_names)
        app = tracker.apps["Mail"]
        self.assertEqual(app.speed_bytes, 10)
        self.assertEqual(app.total_bytes, 1010)

    def test_speed_resets_when_a_program_goes_quiet(self):
        tracker = Tracker()
        tracker.add_sample({1: ("Mail", 900, 100)}, plain_names)
        tracker.add_sample({2: ("Other", 5, 0)}, plain_names)
        self.assertEqual(tracker.apps["Mail"].speed_bytes, 0)
        self.assertFalse(tracker.apps["Mail"].busy)

    def test_sending_time_counts_only_seconds_that_moved_data(self):
        tracker = Tracker()
        tracker.add_sample({1: ("Mail", 10, 0)}, plain_names)
        tracker.add_sample({1: ("Mail", 0, 0)}, plain_names)
        tracker.add_sample({1: ("Mail", 0, 4)}, plain_names)
        self.assertEqual(tracker.apps["Mail"].sending_seconds, 2)

    def test_top_is_ranked_by_average_use(self):
        tracker = Tracker()
        tracker.add_sample({1: ("small", 10, 0), 2: ("big", 900, 0), 3: ("mid", 100, 0)},
                           plain_names)
        self.assertEqual(tracker.pick_top(2), ["big", "mid"])

    def test_rows_stay_in_total_used_order(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 900, 0), 2: ("b", 10, 0)}, plain_names)
        chosen = tracker.pick_top(2)
        self.assertEqual(chosen, ["a", "b"])

        # "b" is briefly faster than "a" this second, but hasn't caught up on
        # total, so the row order should not jump around because of it.
        tracker.add_sample({1: ("a", 1, 0), 2: ("b", 500, 0)}, plain_names)
        names = [app.name for app in tracker.rows_for(chosen)]
        self.assertEqual(names, ["a", "b"])          # order unchanged
        self.assertEqual(sorted(names), ["a", "b"])  # same two programs

    def test_rows_reorder_once_total_used_actually_overtakes(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 900, 0), 2: ("b", 10, 0)}, plain_names)
        chosen = tracker.pick_top(2)

        tracker.add_sample({1: ("a", 0, 0), 2: ("b", 5000, 0)}, plain_names)
        names = [app.name for app in tracker.rows_for(chosen)]
        self.assertEqual(names, ["b", "a"])  # "b" has now used more in total

    def test_a_quiet_program_is_still_shown(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 900, 0), 2: ("b", 10, 0)}, plain_names)
        chosen = tracker.pick_top(2)
        tracker.add_sample({}, plain_names)
        self.assertEqual(len(tracker.rows_for(chosen)), 2)

    def test_rows_can_be_sorted_by_speed_instead(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 900, 0), 2: ("b", 10, 0)}, plain_names)
        chosen = tracker.pick_top(2)

        tracker.add_sample({1: ("a", 1, 0), 2: ("b", 500, 0)}, plain_names)
        names = [app.name for app in tracker.rows_for(chosen, sort_by="speed")]
        self.assertEqual(names, ["b", "a"])  # "b" is faster this second

    def test_rows_can_be_sorted_by_the_past_hour(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 900, 0), 2: ("b", 10, 0)}, plain_names)
        chosen = tracker.pick_top(2)

        tracker.add_sample({1: ("a", 0, 0), 2: ("b", 5000, 0)}, plain_names)
        names = [app.name for app in tracker.rows_for(chosen, sort_by="hour")]
        self.assertEqual(names, ["b", "a"])  # "b" has used more in the last hour

    def test_the_past_hour_only_counts_the_last_3600_seconds(self):
        app = AppStats("a")
        for _ in range(HOUR_SECONDS):
            app.speed_in, app.speed_out = 1, 0
            app.record_second()
        self.assertEqual(app.hour_bytes, HOUR_SECONDS)

        # one more second of silence should push the oldest second out
        app.speed_in, app.speed_out = 0, 0
        app.record_second()
        self.assertEqual(app.hour_bytes, HOUR_SECONDS - 1)

    def test_current_pids_track_only_this_seconds_processes(self):
        tracker = Tracker()
        tracker.add_sample({1: ("helper", 100, 0), 2: ("helper", 50, 0)},
                            lambda pid, fallback: "Google Chrome")
        self.assertEqual(tracker.apps["Google Chrome"].current_pids, {1, 2})

        # pid 2 has gone quiet; only pid 1 shows up this second
        tracker.add_sample({1: ("helper", 10, 0)}, lambda pid, fallback: "Google Chrome")
        self.assertEqual(tracker.apps["Google Chrome"].current_pids, {1})

    def test_history_tracks_the_combined_speed_of_every_app(self):
        tracker = Tracker()
        tracker.add_sample({1: ("a", 100, 0), 2: ("b", 50, 0)}, plain_names)
        tracker.add_sample({1: ("a", 10, 0)}, plain_names)
        self.assertEqual(list(tracker.history), [150, 10])


class HistoryHelpersTest(unittest.TestCase):
    def test_recent_speed_history_is_a_tail_slice(self):
        history = [1, 2, 3, 4, 5]
        self.assertEqual(recent_speed_history(history, 2), [4, 5])
        self.assertEqual(recent_speed_history(history, 10), [1, 2, 3, 4, 5])

class AnomalyTest(unittest.TestCase):
    def test_a_spike_far_above_its_own_average_is_anomalous(self):
        app = AppStats("a")
        for _ in range(100):
            app.speed_in, app.speed_out = 10, 0
            app.record_second()
        app.speed_in, app.speed_out = 1000, 0  # way above its own average
        self.assertTrue(is_anomalous(app))

    def test_steady_usage_is_not_anomalous(self):
        app = AppStats("a")
        for _ in range(100):
            app.speed_in, app.speed_out = 10, 0
            app.record_second()
        self.assertFalse(is_anomalous(app))

    def test_a_program_with_no_history_yet_is_not_anomalous(self):
        app = AppStats("a")
        app.speed_in, app.speed_out = 1000, 0
        self.assertFalse(is_anomalous(app))


class FormattingTest(unittest.TestCase):
    def test_megabits_per_second(self):
        self.assertAlmostEqual(mbps(1_000_000), 8.0)

    def test_megabytes(self):
        self.assertAlmostEqual(megabytes(1_500_000), 1.5)

    def test_small_amounts_stay_readable(self):
        # 10 KB must not look the same as nothing at all
        self.assertEqual(format_megabytes(0), "0.000")
        self.assertEqual(format_megabytes(10_900), "0.011")
        self.assertNotEqual(format_megabytes(10_900), format_megabytes(0))

    def test_large_amounts_lose_the_noisy_decimals(self):
        self.assertEqual(format_megabytes(4_250_000), "4.25")
        self.assertEqual(format_megabytes(142_300_000), "142.3")

    def test_megabyte_text_always_fits_the_column(self):
        for byte_count in [0, 1, 999, 10_900, 5_000_000, 999_999_999_999]:
            self.assertLessEqual(len(format_megabytes(byte_count)), 12)

    def test_duration_matches_the_examples(self):
        self.assertEqual(duration(23 * 60 + 45), "23:45")
        self.assertEqual(duration(1 * 3600 + 23 * 60 + 45), "1:23:45")
        self.assertEqual(duration(0), "00:00")
        self.assertEqual(duration(9), "00:09")


if __name__ == "__main__":
    unittest.main()
