import asyncio
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import KillConfirmScreen, NetTopApp
    from cards import TopProgramsCard
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
