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

"""GUI regression tests for the layout of the start page.

The page used to be a row of six equal buttons over three framed grids of
cards and four lines of plain text about the controls. It is now a sidebar and
a main column. The sidebar gives the usual way in, a new design with a body
ready to sketch on, one large button, and lists the other ways under it. The
main column holds the files, as cards that say how long ago a recent file was
saved, under a filter that narrows every list at once, with the shortcuts shown
as key caps.

The checkbox at the foot of the sidebar used to read "Do not show this Start
page again" and stored the opposite of what it showed. It now reads "Show this
page on startup" and stores what it shows.

To run tests:
    FreeCAD -t TestStartPageLayout
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

START_PARAMS = "User parameter:BaseApp/Preferences/Mod/Start"

# Start::DisplayedFilesModelRoles::baseName, the role the filter matches against
BASE_NAME_ROLE = QtCore.Qt.UserRole + 1

# A filter no file name could match
NO_SUCH_FILE = "zzqx-no-file-is-called-this"


def _process_events(seconds=0.0):
    deadline = time.monotonic() + seconds
    while True:
        FreeCADGui.updateGui()
        QtWidgets.QApplication.instance().processEvents()
        if time.monotonic() >= deadline:
            return
        time.sleep(0.05)


def _find_start_view():
    for widget in QtWidgets.QApplication.instance().allWidgets():
        if widget.metaObject().className() == "StartGui::StartView":
            return widget
    return None


class TestStartPageLayout(unittest.TestCase):
    def setUp(self):
        if FreeCADGui.getMainWindow() is None:
            raise unittest.SkipTest("No main window in this test environment")

        self.params = FreeCAD.ParamGet(START_PARAMS)
        self.saved_show_on_startup = self.params.GetBool("ShowOnStartup", True)
        self.saved_close_start = self.params.GetBool("closeStart", False)
        # Keeps the page open when a test starts a document from it
        self.params.SetBool("closeStart", False)

        self.start_view = _find_start_view()
        self.opened_here = self.start_view is None
        if self.start_view is None:
            FreeCADGui.runCommand("Start_Start")
            deadline = time.monotonic() + 5.0
            while self.start_view is None and time.monotonic() < deadline:
                _process_events(0.05)
                self.start_view = _find_start_view()
        self.assertIsNotNone(self.start_view, "Could not open the start page")
        self.documents_before = set(FreeCAD.listDocuments())

    def tearDown(self):
        for name in set(FreeCAD.listDocuments()) - getattr(self, "documents_before", set()):
            FreeCAD.closeDocument(name)
        if hasattr(self, "params"):
            self.params.SetBool("ShowOnStartup", self.saved_show_on_startup)
            self.params.SetBool("closeStart", self.saved_close_start)
        filter_edit = self._child(QtWidgets.QLineEdit, "StartFilter", required=False)
        if filter_edit is not None:
            filter_edit.clear()
        if getattr(self, "opened_here", False) and self.start_view is not None:
            self.start_view.close()
        _process_events()

    def _child(self, kind, name, required=True):
        widget = self.start_view.findChild(kind, name) if self.start_view else None
        if required:
            self.assertIsNotNone(widget, f"The start page has no {kind.__name__} {name}")
        return widget

    def _file_sections(self):
        """Each list of files, as (section widget, card view, count label)."""
        sections = []
        for view in self.start_view.findChildren(QtWidgets.QListView):
            if view.metaObject().className() != "StartGui::FileCardView":
                continue
            section = view.parentWidget()
            count = section.findChild(QtWidgets.QLabel, "StartSectionCount")
            sections.append((section, view, count))
        return sections

    def test_new_design_is_the_one_large_button(self):
        primary = self._child(QtWidgets.QPushButton, "StartPrimaryButton")
        self.assertEqual("New design", primary.text())
        sidebar = self._child(QtWidgets.QFrame, "StartSidebar")
        self.assertTrue(sidebar.isAncestorOf(primary), "New design should be in the sidebar")

        rows = sidebar.findChildren(QtWidgets.QPushButton, "newFileButton")
        headings = sorted(
            row.findChild(QtWidgets.QLabel, "newFileButtonHeading").text() for row in rows
        )
        self.assertEqual(
            sorted(["Open", "Assembly", "2D Draft", "BIM/Architecture", "Empty File"]),
            headings,
            "The other ways to start should be listed under New design",
        )
        for row in rows:
            self.assertLess(
                row.sizeHint().height(),
                primary.sizeHint().height() * 2,
                "A listed way to start should be a compact row, not a big tile",
            )

    def test_new_design_starts_a_body_to_sketch_on(self):
        primary = self._child(QtWidgets.QPushButton, "StartPrimaryButton")
        primary.click()
        _process_events(0.2)

        new_documents = set(FreeCAD.listDocuments()) - self.documents_before
        self.assertEqual(1, len(new_documents), "New design should make one new document")
        doc = FreeCAD.getDocument(new_documents.pop())
        bodies = [obj for obj in doc.Objects if obj.TypeId == "PartDesign::Body"]
        self.assertEqual(1, len(bodies), "The new document should hold a body")

    def test_show_on_startup_stores_what_it_shows(self):
        check = self._child(QtWidgets.QCheckBox, "StartShowOnStartup")
        self.assertEqual("Show this page on startup", check.text())

        check.setChecked(False)
        self.assertFalse(self.params.GetBool("ShowOnStartup", True))
        check.setChecked(True)
        self.assertTrue(self.params.GetBool("ShowOnStartup", False))

    def test_shortcuts_are_key_caps(self):
        keys = [
            label.text()
            for label in self.start_view.findChildren(QtWidgets.QLabel, "StartShortcutKey")
        ]
        for key in ("S", "E", "Q", "H", "F", "D"):
            self.assertIn(key, keys)

    def test_cards_take_their_colours_from_the_stylesheet_or_palette(self):
        sections = self._file_sections()
        self.assertTrue(sections, "The start page should have at least one list of files")
        for _, view, _ in sections:
            for name in ("cardColor", "wellColor", "borderColor", "accentColor", "mutedTextColor"):
                colour = view.property(name)
                self.assertIsNotNone(colour, f"The card view has no {name} property")
                self.assertTrue(colour.isValid(), f"{name} should fall back to a real colour")
            self.assertEqual(
                QtWidgets.QAbstractItemView.NoSelection,
                view.selectionMode(),
                "A card opens its file, so it should not stay selected afterwards",
            )

    def test_a_filter_that_matches_nothing_says_so(self):
        filter_edit = self._child(QtWidgets.QLineEdit, "StartFilter")
        no_matches = self._child(QtWidgets.QLabel, "StartNoMatches")
        shortcuts = self._child(QtWidgets.QWidget, "StartShortcuts")
        self.assertTrue(no_matches.isHidden())

        filter_edit.setText(NO_SUCH_FILE)
        _process_events()
        for section, view, _ in self._file_sections():
            self.assertEqual(0, view.model().rowCount())
            self.assertTrue(section.isHidden(), "A section the filter empties should go away")
        self.assertTrue(shortcuts.isHidden(), "The shortcuts should make way for the results")
        self.assertFalse(no_matches.isHidden(), "An empty result should say so")

        filter_edit.clear()
        _process_events()
        self.assertTrue(no_matches.isHidden())
        self.assertFalse(shortcuts.isHidden())

    def test_the_filter_narrows_a_list_and_its_count(self):
        filled = None
        deadline = time.monotonic() + 5.0
        while filled is None and time.monotonic() < deadline:
            for section, view, count in self._file_sections():
                if view.model().rowCount() > 1:
                    filled = (section, view, count)
                    break
            _process_events(0.05)
        if filled is None:
            self.skipTest("No list on the start page has two files to tell apart")
        section, view, count = filled
        model = view.model()
        total = model.rowCount()
        self.assertEqual(str(total), count.text())

        first = model.index(0, 0).data(BASE_NAME_ROLE)
        self.assertTrue(first, "The first card should have a file name")
        filter_edit = self._child(QtWidgets.QLineEdit, "StartFilter")
        filter_edit.setText(first.upper())
        _process_events()

        matched = model.rowCount()
        self.assertGreaterEqual(matched, 1, "The filter should ignore case")
        self.assertLess(matched, total, "The filter should leave out files it does not match")
        self.assertEqual(str(matched), count.text(), "The count should follow the filter")
        self.assertFalse(section.isHidden())


if __name__ == "__main__":
    unittest.main()
