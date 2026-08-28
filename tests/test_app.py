import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import REFRESH_RATES, KillConfirmScreen, NetTopApp
    from cards import DestinationRow, DestinationsCard, StatusBar, TopProgramsCard
    from textual.widgets import DataTable
except ImportError:  # textual isn't installed in every environment
    NetTopApp = None

from nettop_source import ReplaySource

SAMPLE_PATH = os.path.join(os.path.dirname(__file__), "sample_capture.txt")


class FakeArgs:
    warmup = 0
    top = 5


@unittest.skipIf(NetTopApp is None, "textual is not installed")
class AppSmokeTest(unittest.IsolatedAsyncioTestCase):
    def _make_app(self):
        return NetTopApp(ReplaySource(SAMPLE_PATH), FakeArgs())

    async def test_app_starts_and_cards_mount(self):
        app = self._make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIsNotNone(app.query_one(TopProgramsCard))
        app._source.close()

    async def test_pressing_s_cycles_the_sort_label(self):
        app = self._make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.sort_index
            await pilot.press("s")
            self.assertEqual(app.sort_index, (before + 1) % 3)
        app._source.close()

    async def test_pressing_t_cycles_the_theme_and_shows_it(self):
        app = self._make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            before = app.theme
            await pilot.press("t")
            self.assertNotEqual(app.theme, before)
            self.assertIn(f"Theme: {app.theme}", app.query_one(StatusBar).content)
        app._source.close()

    async def test_pressing_r_cycles_the_refresh_rate_and_shows_it(self):
        app = self._make_app()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("r")
            expected = REFRESH_RATES[1]
            self.assertIn(f"Refresh: {expected:g}s", app.query_one(StatusBar).content)
            await pilot.press("r")
            await pilot.press("r")  # wraps back to the first rate
            self.assertIn(f"Refresh: {REFRESH_RATES[0]:g}s", app.query_one(StatusBar).content)
        app._source.close()

    async def test_top_programs_column_stretches_to_fill_the_width(self):
        app = self._make_app()
        app.tracker.add_sample({1: ("a", 100, 0)}, lambda pid, fb: fb)
        app.top = ["a"]
        async with app.run_test(size=(200, 40)) as pilot:
            await pilot.pause()
            app._refresh_nettop_cards()
            await pilot.pause()
            table = app.query_one(DataTable)
            self.assertEqual(table.virtual_size.width, table.size.width)
        app._source.close()

    async def test_destination_row_hosts_tick_independently(self):
        app = self._make_app()
        async with app.run_test(size=(160, 50)) as pilot:
            await pilot.pause()
            card = app.query_one(DestinationsCard)
            long_hosts = [f"very-long-hostname-number-{i}.example.com" for i in range(10)]
            card.update_from({"Chrome": long_hosts, "Slack": ["short.example.com"]})
            await pilot.pause()

            rows = {row.program_name: row for row in card.query(DestinationRow)}
            chrome_row, slack_row = rows["Chrome"], rows["Slack"]

            chrome_row._advance_ticker()
            self.assertEqual(chrome_row._offset, 1)
            self.assertEqual(slack_row._offset, 0)  # untouched by Chrome's tick

            chrome_text = chrome_row.query_one(".destination-hosts").content
            self.assertNotEqual(str(chrome_text), chrome_row._hosts_text)  # actually scrolled

            slack_text = slack_row.query_one(".destination-hosts").content
            self.assertEqual(str(slack_text), slack_row._hosts_text)  # short enough, unscrolled

            # same programs, updated data -> row identity (and ticker position) preserved
            card.update_from({"Chrome": long_hosts, "Slack": ["short.example.com"]})
            await pilot.pause()
            self.assertEqual(chrome_row._offset, 1)
        app._source.close()

    async def test_kill_requires_confirmation(self):
        app = self._make_app()
        killed = []
        app.tracker.add_sample({1: ("Test App", 100, 0)}, lambda pid, fallback: "Test App")
        app.top = ["Test App"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._refresh_nettop_cards()
            await pilot.pause()

            # Patch os.kill so this test never touches a real process.
            import app as app_module
            original_kill = app_module.os.kill
            app_module.os.kill = lambda pid, sig: killed.append((pid, sig))
            try:
                app.action_kill_selected()
                await pilot.pause()
                self.assertIsInstance(app.screen, KillConfirmScreen)

                app.screen.query_one("#cancel").press()
                await pilot.pause()
                self.assertEqual(killed, [])
                self.assertNotIsInstance(app.screen, KillConfirmScreen)

                app.action_kill_selected()
                await pilot.pause()
                app.screen.query_one("#kill").press()
                await pilot.pause()
                self.assertEqual(killed, [(1, __import__("signal").SIGTERM)])
            finally:
                app_module.os.kill = original_kill
        app._source.close()


if __name__ == "__main__":
    unittest.main()
