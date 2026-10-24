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

"""GUI regression tests for how a ribbon page shares its width.

A ribbon page is a row of panels, and a panel is a row of fixed-size buttons
with a caption underneath. When the window is narrower than the page wants, the
buttons that do not fit have to leave the row and turn up in the caption
drop-down, the way a toolbar folds its tail into an extension menu; a page must
never shrink a panel below the space its visible buttons take, because Qt then
packs the buttons on top of each other. Width is taken from the rightmost panel
first, so the panels a workspace leads with keep their buttons the longest.

The split between the row and the drop-down is also the user's to change:
dropping a button on the panel caption moves it into the drop-down, dropping a
drop-down entry on the row shows it as a button, and the result is kept in the
user parameters under Ribbon/Panels/<tab>/<panel>.

To run tests:
    FreeCAD -t TestRibbonLayout
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

MAIN_WINDOW_PARAMS = "User parameter:BaseApp/Preferences/MainWindow"
PANEL_PARAMS = "User parameter:BaseApp/Preferences/Ribbon/Panels"

# The tab the PartDesign workbench backs and its leading panel, see
# src/Gui/Ribbon/Workspaces/Design.json.
SOLID_TAB = "SOLID"
CREATE_PANEL_KEY = "SOLID/CREATE"
MODIFY_PANEL_KEY = "SOLID/MODIFY"
# In the CREATE drop-down but not in its row.
MENU_ONLY_COMMAND = "PartDesign_Sweep"
# Inside the "Pattern" submenu of the CREATE drop-down.
SUBMENU_COMMAND = "PartDesign_PolarPattern"

# What RibbonPanel and RibbonPanelMenu exchange when an entry is dragged.
MIME_TYPE = "application/x-othercad-ribbon-command"

RIBBON_BUTTON_NAMES = ("RibbonButton", "RibbonPrimaryButton")
STANDARD_TOOLBARS = (
    "File",
    "Edit",
    "Clipboard",
    "Workbench",
    "Macro",
    "View",
    "Individual Views",
    "Structure",
    "Help",
)


class TestRibbonLayout(unittest.TestCase):
    """A page folds from the right, and the fold is the user's to arrange."""

    def setUp(self):
        if not FreeCAD.ParamGet(MAIN_WINDOW_PARAMS).GetBool("UseRibbon", True):
            raise unittest.SkipTest("The ribbon shell is switched off in this build")

        self.window = FreeCADGui.getMainWindow()
        if self.window is None:
            raise unittest.SkipTest("No main window in this test environment")

        self.tab_bar = self.window.findChild(QtWidgets.QTabBar, "RibbonTabBar")
        self.pages = self.window.findChild(QtWidgets.QStackedWidget, "RibbonPages")
        if self.tab_bar is None or self.pages is None:
            raise unittest.SkipTest("The ribbon shell is not installed in this test environment")

        self.saved_geometry = self.window.geometry()
        self.saved_state = self.window.windowState()
        self.saved_layout = self._snapshot_layout()
        # A cleanup runs even when setUp goes on to skip, which tearDown does
        # not, and the user's arrangement must come back either way.
        self.addCleanup(self._restore_layout, self.saved_layout)
        self._clear_layout()

        # Activating a workbench that is already active rebuilds nothing, and
        # the SOLID page must be built from the cleared layout, not left over
        # from whatever the previous test arranged.
        self._activate("PartWorkbench")
        self._activate("PartDesignWorkbench")
        if self.tab_bar.tabText(self.tab_bar.currentIndex()) != SOLID_TAB:
            raise unittest.SkipTest("PartDesign does not select the SOLID tab in this build")

    def tearDown(self):
        self._clear_layout()
        self._restore_layout(self.saved_layout)
        self.window.setGeometry(self.saved_geometry)
        self.window.setWindowState(self.saved_state)
        # The pages were built against the widths and overrides of the test, so
        # they are rebuilt from a clean slate for whoever runs next.
        self._activate("PartWorkbench")
        self._activate("PartDesignWorkbench")

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50, rounds=3):
        app = QtWidgets.QApplication.instance()
        for _ in range(rounds):
            FreeCADGui.updateGui()
            app.processEvents()
            time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _activate(self, workbench):
        FreeCADGui.activateWorkbench(workbench)
        self._process_events()

    def _snapshot_layout(self):
        """Every Row override under Ribbon/Panels, as {(tab, panel): row}."""

        snapshot = {}
        root = FreeCAD.ParamGet(PANEL_PARAMS)
        for tab in root.GetGroups():
            tab_group = root.GetGroup(tab)
            for panel in tab_group.GetGroups():
                panel_group = tab_group.GetGroup(panel)
                for kind, name, value in panel_group.GetContents() or []:
                    if kind == "String" and name == "Row":
                        snapshot[(tab, panel)] = value
        return snapshot

    def _clear_layout(self):
        root = FreeCAD.ParamGet(PANEL_PARAMS)
        for tab in list(root.GetGroups()):
            root.RemGroup(tab)

    def _restore_layout(self, snapshot):
        root = FreeCAD.ParamGet(PANEL_PARAMS)
        for (tab, panel), row in snapshot.items():
            root.GetGroup(tab).GetGroup(panel).SetString("Row", row)

    def _row_override(self, key):
        """The stored row of the panel \\a key, or None while it has none."""

        tab, panel = key.split("/", 1)
        root = FreeCAD.ParamGet(PANEL_PARAMS)
        if tab not in root.GetGroups():
            return None
        tab_group = root.GetGroup(tab)
        if panel not in tab_group.GetGroups():
            return None
        for kind, name, value in tab_group.GetGroup(panel).GetContents() or []:
            if kind == "String" and name == "Row":
                return value
        return None

    def _page(self):
        return self.pages.currentWidget()

    def _panels(self, page=None):
        """The panels of \\a page in reading order."""

        page = page or self._page()
        panels = page.findChildren(QtWidgets.QWidget, "RibbonPanel")
        return sorted(panels, key=lambda panel: panel.mapTo(page, QtCore.QPoint(0, 0)).x())

    def _panel(self, key):
        for panel in self._panels():
            if panel.property("panelKey") == key:
                return panel
        return None

    def _wait_for_panel(self, key, previous=None, timeout_ms=3000):
        """The panel \a key once the page has been rebuilt from a queued call,
        which is what a drop or a reset asks for; \a previous is the panel that
        rebuild replaces, so that it is not mistaken for the new one."""

        self._process_events()
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            panel = self._panel(key)
            if panel is not None and panel is not previous:
                return panel
            if time.monotonic() >= deadline:
                return None
            self._process_events(20, 1)

    def _row_buttons(self, panel):
        """Every command button of \\a panel, hidden ones included, in row order."""

        buttons = [
            button
            for button in panel.findChildren(QtWidgets.QToolButton)
            if button.objectName() in RIBBON_BUTTON_NAMES
        ]
        return sorted(buttons, key=lambda button: button.property("rowIndex"))

    def _visible_buttons(self, panel):
        return [b for b in self._row_buttons(panel) if b.isVisibleTo(self._page())]

    def _hidden_buttons(self, panel):
        return [b for b in self._row_buttons(panel) if not b.isVisibleTo(self._page())]

    def _row_commands(self, panel):
        return [button.property("command") for button in self._row_buttons(panel)]

    def _caption(self, panel):
        button = panel.findChild(QtWidgets.QToolButton, "RibbonPanelCaptionButton")
        if button is not None and button.isVisibleTo(panel):
            return button
        return panel.findChild(QtWidgets.QLabel, "RibbonPanelCaption")

    def _menu_commands(self, menu):
        """The commands the drop-down \\a menu names, submenus included."""

        commands = []
        if menu is None:
            return commands
        for action in menu.actions():
            command = action.property("ribbonCommand")
            if command:
                commands.append(command)
            if action.menu() is not None:
                commands.extend(self._menu_commands(action.menu()))
        return commands

    def _drop_down_commands(self, panel):
        caption = self._caption(panel)
        if not isinstance(caption, QtWidgets.QToolButton):
            return []
        return self._menu_commands(caption.menu())

    def _button_rect(self, button, page):
        return QtCore.QRect(button.mapTo(page, QtCore.QPoint(0, 0)), button.size())

    def _panels_minimum(self, page=None):
        """The width below which panels themselves have to leave the page."""

        page = page or self._page()
        margins = page.layout().contentsMargins()
        return (
            sum(panel.minimumSizeHint().width() for panel in self._panels(page))
            + margins.left()
            + margins.right()
        )

    def _set_page_width(self, page_width, fold_only=True):
        """Sizes the window so that the current page gets \\a page_width, or as
        near as the window's own minimum allows; returns the width the page got.

        With \\a fold_only, never below what the panels' captions alone need:
        narrower than that, whole panels leave the page for the overflow
        button, which is a different case from folding and its own test.
        """

        page = self._page()
        # resize() is ignored by a maximized window.
        self.window.showNormal()
        self._process_events(20, 1)
        if fold_only:
            page_width = max(page_width, self._panels_minimum(page))
        offset = self.window.width() - page.width()
        self.window.resize(page_width + offset, self.window.height())
        self._process_events()
        return self._page().width()

    def _drop(self, panel, key, command, pos):
        """Drops \\a command of the panel \\a key at \\a pos of \\a panel, the way
        a drag from a button or a drop-down entry ends."""

        mime = QtCore.QMimeData()
        payload = "{}\n{}".format(key, command).encode("utf-8")
        mime.setData(MIME_TYPE, QtCore.QByteArray(payload))
        app = QtWidgets.QApplication.instance()

        # Qt hands a drop to whichever widget accepted the drag's entry and
        # discards it otherwise, so the entry has to come first here too.
        enter = QtGui.QDragEnterEvent(
            pos, QtCore.Qt.MoveAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
        )
        app.sendEvent(panel, enter)
        if not enter.isAccepted():
            return False

        event = QtGui.QDropEvent(
            QtCore.QPointF(pos),
            QtCore.Qt.MoveAction,
            mime,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
        app.sendEvent(panel, event)
        self._process_events()
        return event.isAccepted()

    def _caption_center(self, panel):
        caption = self._caption(panel)
        return caption.mapTo(panel, caption.rect().center())

    def _row_position_before(self, panel, button):
        """A point on the row just inside the leading edge of \\a button."""

        rect = QtCore.QRect(button.mapTo(panel, QtCore.QPoint(0, 0)), button.size())
        return QtCore.QPoint(rect.left() + 2, rect.center().y())

    def _row_position_after(self, panel, button):
        """A point on the row just inside the trailing edge of \\a button."""

        rect = QtCore.QRect(button.mapTo(panel, QtCore.QPoint(0, 0)), button.size())
        return QtCore.QPoint(rect.right() - 2, rect.center().y())

    # -- overflow --------------------------------------------------------

    def test_wide_page_shows_every_button(self):
        """Given its size hint, a page hides nothing."""

        page = self._page()
        width = self._set_page_width(page.sizeHint().width() + 40)
        if width < page.sizeHint().width():
            raise unittest.SkipTest("The screen is too narrow to show the whole page")

        for panel in self._panels():
            self.assertEqual(
                self._hidden_buttons(panel),
                [],
                "Expected every button of a panel to be shown at full width",
            )

    def test_narrow_page_folds_buttons_instead_of_overlapping_them(self):
        """Buttons that do not fit leave the row; the ones that stay never overlap."""

        page = self._page()
        wanted = page.sizeHint().width()
        width = self._set_page_width(wanted // 2)
        page = self._page()
        if width >= wanted:
            raise unittest.SkipTest("The window would not shrink below the page's size hint")

        hidden = sum(len(self._hidden_buttons(panel)) for panel in self._panels(page))
        self.assertGreater(hidden, 0, "Expected a narrow page to fold some buttons away")

        rects = []
        for panel in self._panels(page):
            for button in self._visible_buttons(panel):
                rects.append((button, self._button_rect(button, page)))

        for i, (first, first_rect) in enumerate(rects):
            self.assertLessEqual(
                first_rect.right(),
                page.width(),
                "Expected a visible button to stay inside the page",
            )
            for second, second_rect in rects[i + 1 :]:
                self.assertFalse(
                    first_rect.intersects(second_rect),
                    "Expected {} and {} not to overlap".format(first.text(), second.text()),
                )

    def test_folded_buttons_are_listed_in_the_caption_drop_down(self):
        """A button that left the row is still reachable, through the caption."""

        page = self._page()
        wanted = page.sizeHint().width()
        width = self._set_page_width(wanted // 2)
        if width >= wanted:
            raise unittest.SkipTest("The window would not shrink below the page's size hint")

        checked = 0
        for panel in self._panels():
            hidden = self._hidden_buttons(panel)
            if not hidden:
                continue
            listed = self._drop_down_commands(panel)
            for button in hidden:
                self.assertIn(
                    button.property("command"),
                    listed,
                    "Expected the drop-down of {} to list {}".format(
                        panel.property("panelKey"), button.text()
                    ),
                )
                checked += 1
        self.assertGreater(checked, 0, "Expected at least one folded button to check")

    def test_width_is_taken_from_the_rightmost_panel_first(self):
        """Only a trailing run of panels folds, and only the first of them partly.

        The SOLID tab has no right-aligned panel; one of those would fold after
        every leading panel and sit, unfolded, to the right of a folded one.
        """

        page = self._page()
        wanted = page.sizeHint().width()
        width = self._set_page_width(wanted - 150)
        if width >= wanted:
            raise unittest.SkipTest("The window would not shrink below the page's size hint")

        panels = self._panels()
        states = [
            (len(self._visible_buttons(panel)), len(self._hidden_buttons(panel)))
            for panel in panels
        ]
        folded = [i for i, (_, hidden) in enumerate(states) if hidden > 0]
        self.assertTrue(folded, "Expected 150 px less than the hint to fold something")

        # Everything left of the first folded panel is complete.
        for i in range(folded[0]):
            self.assertEqual(states[i][1], 0, "Expected panel {} to keep every button".format(i))

        # Everything right of it is folded as far as it goes: a caption wider
        # than a button may still leave room for one, so the measure is the
        # width, not the count.
        for i in range(folded[0] + 1, len(states)):
            self.assertLessEqual(
                panels[i].width(),
                panels[i].minimumSizeHint().width(),
                "Expected panel {} to have folded down to its caption".format(i),
            )

    # -- the caption drop-down -------------------------------------------

    def _caption_drop_down(self, key):
        panel = self._panel(key)
        self.assertIsNotNone(panel, "Expected the {} panel".format(key))
        caption = self._caption(panel)
        self.assertIsInstance(
            caption, QtWidgets.QToolButton, "Expected the {} caption to be a drop-down".format(key)
        )
        return panel, caption

    def test_caption_drop_down_spans_the_row(self):
        """All of the strip under the buttons opens the drop-down, not just its text."""

        panel, caption = self._caption_drop_down(CREATE_PANEL_KEY)
        row = panel.findChild(QtWidgets.QWidget, "RibbonPanelButtons")
        self.assertIsNotNone(row, "Expected the panel to have a button row")
        self.assertGreater(
            row.width(), caption.sizeHint().width(), "Expected a row wider than its caption"
        )
        self.assertEqual(caption.x(), row.x(), "Expected the caption to start with the row")
        self.assertEqual(caption.width(), row.width(), "Expected the caption as wide as the row")

    def test_caption_arrow_stays_beside_the_caption(self):
        """Only the frame spans the row: the caption and its arrow are drawn
        together in the middle, where a button sized to them would put them."""

        _, caption = self._caption_drop_down(CREATE_PANEL_KEY)
        image = caption.grab().toImage()
        scale = image.width() / caption.width()
        hint = caption.sizeHint().width() * scale
        # Clear of the one-pixel frame, whose colour differs from the fill
        # while the button is hovered.
        edge = int(scale) + 1
        # Well left of the caption, so the fill whatever the button's state.
        fill = image.pixelColor(edge, image.height() // 2)

        def inked(x):
            for y in range(edge, image.height() - edge):
                colour = image.pixelColor(x, y)
                difference = (
                    abs(colour.red() - fill.red())
                    + abs(colour.green() - fill.green())
                    + abs(colour.blue() - fill.blue())
                )
                if difference > 60:
                    return True
            return False

        columns = [x for x in range(edge, image.width() - edge) if inked(x)]
        self.assertTrue(columns, "Expected the caption to draw its text")
        tolerance = 2 * scale
        self.assertGreaterEqual(
            columns[0],
            (image.width() - hint) / 2 - tolerance,
            "Expected the caption to start no further left than a button sized to it",
        )
        self.assertLessEqual(
            columns[-1],
            (image.width() + hint) / 2 + tolerance,
            "Expected the arrow to stay beside the caption, not at the end of the row",
        )

    # -- customising the split -------------------------------------------

    def test_drop_down_entries_name_their_commands(self):
        """The drop-down entries are drag sources, so they have to know their command."""

        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        listed = self._drop_down_commands(panel)
        self.assertIn(MENU_ONLY_COMMAND, listed)
        self.assertIn(SUBMENU_COMMAND, listed, "Expected submenu entries to be named too")

    def test_dropping_a_button_on_the_caption_moves_it_to_the_drop_down(self):
        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        moved = before[-1]
        self.assertTrue(
            self._drop(panel, CREATE_PANEL_KEY, moved, self._caption_center(panel)),
            "Expected the panel to accept a drop on its caption",
        )

        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the page to be rebuilt after the drop")
        self.assertEqual(self._row_commands(panel), before[:-1])
        self.assertIn(moved, self._drop_down_commands(panel))
        self.assertEqual(self._row_override(CREATE_PANEL_KEY), ";".join(before[:-1]))

    def test_dropping_a_drop_down_entry_on_the_row_shows_it_as_a_button(self):
        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        self.assertNotIn(MENU_ONLY_COMMAND, before)
        first = self._visible_buttons(panel)[0]
        self.assertTrue(
            self._drop(
                panel, CREATE_PANEL_KEY, MENU_ONLY_COMMAND, self._row_position_before(panel, first)
            ),
            "Expected the panel to accept a drop on its row",
        )

        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the page to be rebuilt after the drop")
        self.assertEqual(self._row_commands(panel), [MENU_ONLY_COMMAND] + before)
        self.assertEqual(
            self._row_override(CREATE_PANEL_KEY), ";".join([MENU_ONLY_COMMAND] + before)
        )

    def test_dropping_a_button_on_the_row_reorders_it(self):
        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        self.assertGreater(len(before), 1)
        last = self._visible_buttons(panel)[-1]
        self.assertTrue(
            self._drop(panel, CREATE_PANEL_KEY, before[0], self._row_position_after(panel, last)),
            "Expected the panel to accept a drop on its row",
        )

        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the page to be rebuilt after the drop")
        self.assertEqual(self._row_commands(panel), before[1:] + [before[0]])

    def test_a_drop_from_another_panel_is_refused(self):
        """The drop-down of a panel is its own command set, so nothing crosses over."""

        panel = self._panel(CREATE_PANEL_KEY)
        modify = self._panel(MODIFY_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")
        self.assertIsNotNone(modify, "Expected the MODIFY panel on the SOLID tab")

        before = self._row_commands(panel)
        foreign = self._row_commands(modify)[0]
        first = self._visible_buttons(panel)[0]
        self.assertFalse(
            self._drop(panel, MODIFY_PANEL_KEY, foreign, self._row_position_before(panel, first)),
            "Expected a drop from another panel to be refused",
        )

        self._process_events()
        panel = self._panel(CREATE_PANEL_KEY)
        self.assertEqual(self._row_commands(panel), before)
        self.assertIsNone(self._row_override(CREATE_PANEL_KEY))

    def test_reset_restores_the_definition(self):
        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        self._drop(panel, CREATE_PANEL_KEY, before[-1], self._caption_center(panel))
        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(self._row_override(CREATE_PANEL_KEY))

        reset = panel.findChild(QtGui.QAction, "RibbonPanelResetAction")
        self.assertIsNotNone(reset, "Expected the panel to offer a reset")
        previous = panel
        reset.trigger()

        panel = self._wait_for_panel(CREATE_PANEL_KEY, previous)
        self.assertIsNotNone(panel, "Expected the page to be rebuilt after the reset")
        self.assertEqual(self._row_commands(panel), before)
        self.assertIsNone(self._row_override(CREATE_PANEL_KEY))

    def test_putting_the_row_back_clears_the_override(self):
        """A row that matches the definition again is not an arrangement to keep."""

        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        self._drop(panel, CREATE_PANEL_KEY, before[-1], self._caption_center(panel))
        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(self._row_override(CREATE_PANEL_KEY))

        last = self._visible_buttons(panel)[-1]
        self._drop(panel, CREATE_PANEL_KEY, before[-1], self._row_position_after(panel, last))
        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertEqual(self._row_commands(panel), before)
        self.assertIsNone(self._row_override(CREATE_PANEL_KEY))

    def test_customised_row_survives_a_page_rebuild(self):
        """The override is what the page is built from, not a patch on top of it."""

        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")

        before = self._row_commands(panel)
        self._drop(panel, CREATE_PANEL_KEY, before[-1], self._caption_center(panel))
        self._wait_for_panel(CREATE_PANEL_KEY)

        self._activate("PartWorkbench")
        self._activate("PartDesignWorkbench")

        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the SOLID page to come back")
        self.assertEqual(self._row_commands(panel), before[:-1])

    # -- generated tabs --------------------------------------------------

    def test_generated_tab_carries_only_the_workbench_toolbars(self):
        """Part has no tab of its own, so one is generated from its toolbars. The
        standard set every workbench shares stays out: the app bar's menus carry
        those commands, and the defined tabs do not repeat them either."""

        self._activate("PartWorkbench")
        self._process_events()

        captions = [self._caption(panel).text() for panel in self._panels()]
        self.assertTrue(captions, "Expected the generated Part tab to have panels")
        for caption in captions:
            self.assertNotIn(
                caption, STANDARD_TOOLBARS, "Expected only the workbench's own toolbars"
            )

    # -- below the panels' minimum ---------------------------------------

    def test_below_the_minimum_whole_panels_move_into_an_overflow_button(self):
        """Narrower than the captions alone need, the rightmost panels leave the
        page for an overflow button whose menu lists each of them."""

        page = self._page()
        floor = self._panels_minimum(page)
        width = self._set_page_width(floor - 150, fold_only=False)
        page = self._page()
        if width >= floor:
            raise unittest.SkipTest("The window would not shrink below the panels' minimum")

        # Creation order is definition order, and SOLID has no right-aligned panel.
        ordered = page.findChildren(QtWidgets.QWidget, "RibbonPanel")
        shown = [panel.isVisibleTo(page) for panel in ordered]
        self.assertIn(False, shown, "Expected some panel to have left the page")
        self.assertIn(True, shown, "Expected some panel to stay on the page")
        first_hidden = shown.index(False)
        self.assertTrue(
            all(not visible for visible in shown[first_hidden:]),
            "Expected the panels that left to be the rightmost ones",
        )

        for panel in ordered:
            if panel.isVisibleTo(page):
                rect = QtCore.QRect(panel.mapTo(page, QtCore.QPoint(0, 0)), panel.size())
                self.assertLessEqual(
                    rect.right(), page.width(), "Expected a shown panel inside the page"
                )

        overflow = page.findChild(QtWidgets.QToolButton, "RibbonPageOverflowButton")
        self.assertIsNotNone(overflow, "Expected the page to have an overflow button")
        self.assertTrue(overflow.isVisibleTo(page), "Expected the overflow button to be shown")

        menu = overflow.menu()
        self.assertIsNotNone(menu, "Expected the overflow button to carry a menu")
        menu.aboutToShow.emit()
        listed = [action.text() for action in menu.actions() if action.menu() is not None]
        expected = [self._caption(panel).text() for panel in ordered[first_hidden:]]
        self.assertEqual(listed, expected, "Expected the menu to list every panel that left")

    def test_a_page_wide_enough_for_the_captions_shows_every_panel(self):
        page = self._page()
        width = self._set_page_width(self._panels_minimum(page) + 20, fold_only=False)
        page = self._page()
        if width < self._panels_minimum(page):
            raise unittest.SkipTest("The window would not reach the panels' minimum")

        for panel in self._panels(page):
            self.assertTrue(panel.isVisibleTo(page), "Expected every panel on the page")
        overflow = page.findChild(QtWidgets.QToolButton, "RibbonPageOverflowButton")
        if overflow is not None:
            self.assertFalse(overflow.isVisibleTo(page), "Expected no overflow button")

    # -- preferences -----------------------------------------------------

    def test_preferences_offer_a_panel_reset(self):
        """The Display preferences carry a button that resets every arrangement."""

        panel = self._panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(panel, "Expected the CREATE panel on the SOLID tab")
        before = self._row_commands(panel)
        self._drop(panel, CREATE_PANEL_KEY, before[-1], self._caption_center(panel))
        self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertIsNotNone(self._row_override(CREATE_PANEL_KEY))

        self.pressed = None
        deadline = time.monotonic() + 8.0

        def press():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is None:
                if time.monotonic() < deadline:
                    QtCore.QTimer.singleShot(100, press)
                else:
                    self.pressed = False
                return
            button = dialog.findChild(QtWidgets.QPushButton, "resetRibbonPanelsButton")
            self.pressed = button is not None and button.isEnabled()
            if self.pressed:
                button.click()
            dialog.reject()

        # showPreferences() blocks until the dialog closes, so the button is
        # pressed from a timer while it is open.
        QtCore.QTimer.singleShot(300, press)
        FreeCADGui.showPreferences("Display")
        self._process_events()

        self.assertTrue(self.pressed, "Expected an enabled reset button on the Display page")
        self.assertIsNone(self._row_override(CREATE_PANEL_KEY))
        panel = self._wait_for_panel(CREATE_PANEL_KEY)
        self.assertEqual(self._row_commands(panel), before)
