# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD contributors
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""GUI regression tests for switching workbench from the ribbon.

The block at the left of the ribbon opens a list of workbenches, and so does
Ctrl+Shift+W: the ribbon's own areas first, named after their tabs, then the last
workbenches used, then every other one. Typing narrows the list and Enter
switches to the first match, so any workbench is two clicks away, or a shortcut
and a few letters.

To run tests:
    FreeCAD -t TestWorkbenchSwitcher
"""

import importlib
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

# FreeCAD's PySide shim does not re-export QtTest (see TestFusionShortcuts), and
# only QTest can deliver a keystroke the way the platform does, which is the only
# way a shortcut fires. Anything a candidate raises means it is not usable.
QtTest = None
for _binding in ("PySide6.QtTest", "PySide.QtTest"):
    try:
        QtTest = importlib.import_module(_binding)
        break
    except Exception:  # pragma: no cover - depends on which binding is installed
        continue

MAIN_WINDOW_PARAMS = "User parameter:BaseApp/Preferences/MainWindow"

# See src/Gui/Ribbon/WorkbenchSwitcher.cpp and RibbonBar.cpp.
SWITCHER = "WorkbenchSwitcher"
FILTER = "WorkbenchSwitcherFilter"
LIST = "WorkbenchSwitcherList"
BLOCK_BUTTON = "RibbonWorkspaceSelector"
COMMAND = "Std_WorkbenchSwitcher"


class TestWorkbenchSwitcher(unittest.TestCase):
    """The ribbon's block and Ctrl+Shift+W switch workbench in a couple of steps."""

    def setUp(self):
        if not FreeCAD.ParamGet(MAIN_WINDOW_PARAMS).GetBool("UseRibbon", True):
            raise unittest.SkipTest("The ribbon shell is switched off in this build")

        self.window = FreeCADGui.getMainWindow()
        if self.window is None:
            raise unittest.SkipTest("No main window in this test environment")

        self.button = self.window.findChild(QtWidgets.QToolButton, BLOCK_BUTTON)
        if self.button is None:
            raise unittest.SkipTest("The ribbon shell is not installed in this test environment")

        FreeCADGui.activateWorkbench("PartDesignWorkbench")
        self._process_events()

    def tearDown(self):
        switcher = self._switcher()
        if switcher is not None:
            switcher.hide()
        FreeCADGui.activateWorkbench("PartDesignWorkbench")
        self._process_events()

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _switcher(self):
        for widget in QtWidgets.QApplication.instance().allWidgets():
            if widget.objectName() == SWITCHER:
                return widget
        return None

    def _shown(self, open_it, message):
        """Opens the switcher with open_it() and returns it once it is on screen.

        On X11 without a window manager, as on CI's Linux runner, a Qt popup shown
        again a moment after it was hidden sometimes never maps; the command
        palette does the same. One more try is what a user's second click would be.
        """

        for _ in range(2):
            open_it()
            self._process_events()
            switcher = self._switcher()
            if switcher is not None and switcher.isVisible():
                return switcher
        self.fail(message)

    def _open(self):
        return self._shown(self.button.click, "The block did not open the switcher")

    def _rows(self, switcher):
        """(text, workbench) for every row; captions have no workbench."""

        view = switcher.findChild(QtWidgets.QListWidget, LIST)
        rows = []
        for index in range(view.count()):
            item = view.item(index)
            rows.append((item.text(), item.data(QtCore.Qt.UserRole)))
        return rows

    def _type(self, switcher, text):
        switcher.findChild(QtWidgets.QLineEdit, FILTER).setText(text)
        self._process_events()

    def _press(self, switcher, key):
        field = switcher.findChild(QtWidgets.QLineEdit, FILTER)
        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            QtWidgets.QApplication.sendEvent(
                field, QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier)
            )
        self._process_events(200)

    @staticmethod
    def _active():
        return FreeCADGui.activeWorkbench().__class__.__name__

    # -- tests -----------------------------------------------------------

    def test_the_block_opens_the_switcher(self):
        self._open()

    def test_the_block_draws_its_arrow_rather_than_typing_it(self):
        """The arrow after the title was the character U+25BE. The first geometric shape Qt
        lays out makes it query every fallback font on the system, about a second of each
        start, so the arrow is drawn and the title is plain text with room left for it."""

        text = self.button.text()
        self.assertEqual(text, text.strip())
        self.assertFalse(
            [c for c in text if 0x2190 <= ord(c) <= 0x2BFF],
            "the block's title holds an arrow or shape character: %r" % text,
        )
        title_width = self.button.fontMetrics().horizontalAdvance(text)
        self.assertGreater(self.button.sizeHint().width(), title_width + 8, "no room for the arrow")

    def test_the_ribbon_areas_lead_the_list_under_their_tab_names(self):
        rows = self._rows(self._open())
        workbenches = [workbench for _, workbench in rows if workbench]

        self.assertEqual(
            workbenches[0],
            "PartDesignWorkbench",
            "The SOLID area should head the list, got " + repr(rows[:4]),
        )
        first = next(text for text, workbench in rows if workbench == "PartDesignWorkbench")
        self.assertEqual(first, "Solid", "Part Design should be listed under its tab's name")

    def test_an_area_is_found_by_its_workbench_name_too(self):
        switcher = self._open()
        self._type(switcher, "part design")

        matches = [workbench for _, workbench in self._rows(switcher) if workbench]
        self.assertIn("PartDesignWorkbench", matches, "Searching for Part Design found nothing")

    def test_typing_narrows_the_list_and_enter_switches(self):
        switcher = self._open()
        self._type(switcher, "mes")

        rows = [row for row in self._rows(switcher) if row[1]]
        self.assertTrue(rows, "Typing 'mes' left nothing in the list")
        self.assertEqual(rows[0][1], "MeshWorkbench", "Mesh should be the first match for 'mes'")

        self._press(switcher, QtCore.Qt.Key_Return)

        self.assertEqual(self._active(), "MeshWorkbench", "Enter did not switch to the match")
        self.assertFalse(switcher.isVisible(), "The switcher stayed open after switching")

    def test_a_workbench_used_recently_is_offered_again(self):
        FreeCADGui.activateWorkbench("PartWorkbench")
        self._process_events(200)
        FreeCADGui.activateWorkbench("PartDesignWorkbench")
        self._process_events(200)

        rows = self._rows(self._open())
        captions = [text for text, workbench in rows if not workbench]
        self.assertIn("Recent", captions, "Expected a Recent section, got " + repr(captions))

        recent = rows.index(("Recent", None))
        after = rows[recent + 1 :]
        section = []
        for text, workbench in after:
            if not workbench:
                break
            section.append(workbench)
        self.assertIn("PartWorkbench", section, "Part should be offered as a recent workbench")

    def test_the_shortcut_opens_the_switcher(self):
        command = FreeCADGui.Command.get(COMMAND)
        self.assertIsNotNone(command, "No %s command" % COMMAND)
        self.assertEqual(command.getShortcut(), "Ctrl+Shift+W")

        self._shown(
            lambda: FreeCADGui.runCommand(COMMAND, 0), "The command did not open the switcher"
        )

    def test_ctrl_shift_w_opens_the_switcher(self):
        """The key itself, not the command: a shortcut only fires once its action
        is in a menu, which is why the command sits in the View menu."""

        if QtTest is None:
            raise unittest.SkipTest("This PySide build has no QtTest, so no key can be delivered")
        handle = self.window.windowHandle()
        if handle is None:
            raise unittest.SkipTest("The main window has no native handle in this environment")
        self.window.activateWindow()
        self.window.raise_()
        self._process_events(200)
        if not self.window.isActiveWindow():
            raise unittest.SkipTest("This machine did not hand the application the keyboard")

        QtTest.QTest.keyClick(
            handle, QtCore.Qt.Key_W, QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier, 0
        )
        self._process_events(200)

        switcher = self._switcher()
        self.assertTrue(
            switcher is not None and switcher.isVisible(), "Ctrl+Shift+W did not open the switcher"
        )


if __name__ == "__main__":
    unittest.main()
