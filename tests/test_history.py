import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from history import (History, choose_bucket_seconds, format_span,
                     history_view, period_start_for, resample_periods)


class PeriodStartForTest(unittest.TestCase):
    def test_rounds_down_to_the_period_boundary(self):
        self.assertEqual(period_start_for(1000, period_seconds=300), 900)
        self.assertEqual(period_start_for(899, period_seconds=300), 600)


class ChooseBucketSecondsTest(unittest.TestCase):
    def test_a_short_span_uses_the_finest_bucket(self):
        self.assertEqual(choose_bucket_seconds(30 * 60, target_bars=12), 300)

    def test_a_day_long_span_uses_a_wider_bucket(self):
        # a day / 12 bars needs at least a 2-hour bucket
        self.assertEqual(choose_bucket_seconds(24 * 3600, target_bars=12), 2 * 3600)

    def test_a_span_wider_than_the_ladder_uses_the_widest_step(self):
        self.assertEqual(choose_bucket_seconds(30 * 24 * 3600, target_bars=12), 24 * 3600)


class ResamplePeriodsTest(unittest.TestCase):
    def test_periods_land_in_the_right_bucket(self):
        periods = [(0, 10), (300, 20), (600, 30)]
        buckets = resample_periods(periods, now=900, bucket_seconds=300, num_buckets=3)
        self.assertEqual(buckets, [10, 20, 30])

    def test_multiple_periods_in_one_bucket_are_summed(self):
        periods = [(0, 10), (100, 5)]
        buckets = resample_periods(periods, now=300, bucket_seconds=300, num_buckets=1)
        self.assertEqual(buckets, [15])

    def test_periods_outside_the_window_are_ignored(self):
        periods = [(-1000, 999), (0, 10)]
        buckets = resample_periods(periods, now=300, bucket_seconds=300, num_buckets=1)
        self.assertEqual(buckets, [10])


class HistoryViewTest(unittest.TestCase):
    def test_no_periods_gives_an_empty_view(self):
        self.assertEqual(history_view([], now=1000), ([], 0))

    def test_a_brand_new_history_stays_at_fine_granularity(self):
        # only 10 minutes of data recorded so far
        periods = [(0, 5), (300, 5)]
        values, span = history_view(periods, now=600, target_bars=12)
        self.assertEqual(span, 600)  # 2 buckets of 5 min = 10 min span
        self.assertEqual(len(values), 2)

    def test_span_never_exceeds_the_max(self):
        periods = [(0, 1)]
        now = 30 * 24 * 3600  # 30 days later
        values, span = history_view(periods, now=now, max_span=7 * 24 * 3600)
        self.assertLessEqual(span, 7 * 24 * 3600 + 24 * 3600)  # allow one bucket of slack


class FormatSpanTest(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(format_span(45 * 60), "-45m")

    def test_hours(self):
        self.assertEqual(format_span(6 * 3600), "-6h")

    def test_days(self):
        self.assertEqual(format_span(3 * 86400), "-3d")

    def test_zero_is_now(self):
        self.assertEqual(format_span(0), "now")


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "history.db"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_recording_a_period_can_be_read_back(self):
        history = History(self.path)
        history.record_period(300, 1000)
        self.assertEqual(history.periods_since(0), [(300, 1000)])
        history.close()

    def test_recording_the_same_period_twice_accumulates(self):
        history = History(self.path)
        history.record_period(300, 1000)
        history.record_period(300, 500)
        self.assertEqual(history.periods_since(0), [(300, 1500)])
        history.close()

    def test_periods_since_excludes_older_rows(self):
        history = History(self.path)
        history.record_period(100, 1)
        history.record_period(1000, 2)
        self.assertEqual(history.periods_since(500), [(1000, 2)])
        history.close()

    def test_pruning_removes_old_rows(self):
        history = History(self.path)
        history.record_period(100, 1)
        history.record_period(1000, 2)
        history.prune_older_than(500)
        self.assertEqual(history.periods_since(0), [(1000, 2)])
        history.close()


if __name__ == "__main__":
    unittest.main()
