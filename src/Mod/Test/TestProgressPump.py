# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI regression tests for the event loop runs a long operation's progress bar makes.

While an operation reports progress the event loop is run, so the bar moves and Esc is
heard. Every run repaints whatever changed, which in a big window with overlay panels took
30-50 ms; run every 100 ms, a third of a boolean went on painting. Runs are now spaced so
they take at most about a tenth of the time, and still happen.

To run tests:
    FreeCAD -t TestProgressPump
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

PUMP_COST = 0.04  # seconds every run of the event loop costs here
RUN_FOR = 2.0


class _CostlyEventLoop(QtCore.QObject):
    """Makes each run of the event loop cost PUMP_COST, as a slow repaint would."""

    def __init__(self):
        super().__init__()
        self.runs = 0
        self.timer = QtCore.QTimer()
        self.timer.setInterval(0)
        self.timer.timeout.connect(self._cost)

    def _cost(self):
        self.runs += 1
        time.sleep(PUMP_COST)


class TestProgressPump(unittest.TestCase):
    def setUp(self):
        if FreeCADGui.getMainWindow() is None:
            self.skipTest("no main window")

    def _report_progress(self):
        costly = _CostlyEventLoop()
        costly.timer.start()
        progress = FreeCAD.Base.ProgressIndicator()
        progress.start("Testing progress", 1000000)
        end = time.monotonic() + RUN_FOR
        try:
            while time.monotonic() < end:
                progress.next()
        finally:
            progress.stop()
            costly.timer.stop()
        return costly.runs

    def test_the_event_loop_takes_a_small_part_of_a_long_operation(self):
        runs = self._report_progress()
        share = runs * PUMP_COST / RUN_FOR
        self.assertGreater(runs, 0, "the event loop never ran, so the bar would never move")
        self.assertLess(
            share,
            0.2,
            "%d runs of the event loop took %.0f%% of the operation" % (runs, share * 100),
        )


if __name__ == "__main__":
    unittest.main()
