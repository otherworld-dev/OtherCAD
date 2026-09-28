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

"""GUI regression tests for the folder rows a PartDesign body shows in the tree.

A body shows its Origin, then Sketches, Construction and History folders instead of
its flat feature history. The folders are rows of the tree only: the document and
the selection still see Body > Sketch.

To run tests:
    FreeCAD -t TestBrowserFolders
"""

import importlib
import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtGui, QtWidgets

# FreeCAD's PySide shim does not re-export QtTest (see TestFusionShortcuts). Only the Qt6
# binding is tried, and whatever a candidate throws means it is not usable.
QtTest = None
for _binding in ("PySide6.QtTest", "PySide.QtTest"):
    try:
        QtTest = importlib.import_module(_binding)
        break
    except Exception:  # pragma: no cover - depends on which binding is installed
        continue

TREE_PARAMS = "User parameter:BaseApp/Preferences/TreeView"
DOCUMENT_TYPE = 1000
OBJECT_TYPE = 1001
FOLDER_TYPE = 1002


def _process_events(wait_ms=50):
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    time.sleep(wait_ms / 1000.0)
    app.processEvents()


def _draw_rectangle(sketch, width, height):
    corners = [
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(width, 0.0, 0.0),
        FreeCAD.Vector(width, height, 0.0),
        FreeCAD.Vector(0.0, height, 0.0),
    ]
    first = int(sketch.GeometryCount)
    for index in range(4):
        sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]), False)
    for index in range(4):
        sketch.addConstraint(
            Sketcher.Constraint("Coincident", first + index, 2, first + (index + 1) % 4, 1)
        )


class BrowserFoldersBase(unittest.TestCase):
    """Builds Body: Sketch, Pad, Sketch001 (unused), DatumPlane, ShapeBinder."""

    doc_name = "TestBrowserFolders"

    def setUp(self):
        self.params = FreeCAD.ParamGet(TREE_PARAMS)
        self.saved_pref = self.params.GetBool("BodyFolders", True)
        self.params.SetBool("BodyFolders", True)
        self.doc = FreeCAD.newDocument(self.doc_name)
        if self.doc.UndoMode == 0:
            self.doc.UndoMode = 1
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self._build_body()
        _process_events(200)

    def tearDown(self):
        FreeCADGui.Selection.clearSelection()
        for name in list(FreeCAD.listDocuments()):
            if name.startswith(self.doc_name):
                FreeCAD.closeDocument(name)
        self.params.SetBool("BodyFolders", self.saved_pref)
        _process_events()

    def _origin_feature(self, body, role):
        for feature in body.Origin.OriginFeatures:
            if feature.Role == role:
                return feature
        self.fail("No origin feature with role " + role)

    def _build_body(self):
        doc = self.doc
        self.body = doc.addObject("PartDesign::Body", "Body")
        doc.recompute()
        xy = self._origin_feature(self.body, "XY_Plane")

        self.sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (xy, [""])
        self.sketch.MapMode = "FlatFace"
        _draw_rectangle(self.sketch, 10.0, 6.0)
        doc.recompute()

        self.pad = self.body.newObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = 10.0
        doc.recompute()

        self.free_sketch = self.body.newObject("Sketcher::SketchObject", "Sketch001")
        self.free_sketch.AttachmentSupport = (xy, [""])
        self.free_sketch.MapMode = "FlatFace"
        doc.recompute()

        self.plane = self.body.newObject("PartDesign::Plane", "DatumPlane")
        self.plane.AttachmentSupport = (xy, [""])
        self.plane.MapMode = "FlatFace"
        doc.recompute()

        self.binder = self.body.newObject("PartDesign::ShapeBinder", "ShapeBinder")
        doc.recompute()

    def _folders(self, body=None):
        body = body or self.body
        return body.ViewObject.claimChildrenFolders()


class TestBodyFolderContents(BrowserFoldersBase):
    """What the body's view provider hands the tree."""

    def test_body_sorts_its_group_into_three_folders(self):
        folders = self._folders()
        self.assertEqual([f[0] for f in folders], ["Sketches", "Construction", "History"])
        contents = {f[0]: [o.Name for o in f[2]] for f in folders}
        self.assertEqual(contents["Sketches"], ["Sketch", "Sketch001"])
        self.assertEqual(contents["Construction"], ["DatumPlane", "ShapeBinder"])
        self.assertEqual(contents["History"], ["Pad"])

    def test_a_consumed_sketch_is_still_in_sketches(self):
        # claimChildren leaves Sketch out because Pad claims it; the folder must not
        contents = {f[0]: [o.Name for o in f[2]] for f in self._folders()}
        self.assertNotIn(self.sketch, self.body.ViewObject.claimChildren())
        self.assertIn("Sketch", contents["Sketches"])

    def test_an_empty_folder_is_left_out(self):
        self.doc.removeObject(self.plane.Name)
        self.doc.removeObject(self.binder.Name)
        self.doc.recompute()
        self.assertEqual([f[0] for f in self._folders()], ["Sketches", "History"])

    def test_the_preference_turns_the_folders_off(self):
        self.params.SetBool("BodyFolders", False)
        _process_events()
        self.assertEqual(self._folders(), [])

    def test_other_view_providers_have_no_folders(self):
        box = self.doc.addObject("Part::Box", "Box")
        part = self.doc.addObject("App::Part", "Part")
        self.doc.recompute()
        self.assertEqual(box.ViewObject.claimChildrenFolders(), [])
        self.assertEqual(part.ViewObject.claimChildrenFolders(), [])


def _tree():
    """The model tree, preferring one on screen.

    The tree can be momentarily hidden while its overlay panel is folded away. Its rows are
    kept up to date all the same, so a hidden tree still serves.
    """
    trees = [
        tree
        for tree in FreeCADGui.getMainWindow().findChildren(QtWidgets.QTreeWidget)
        if tree.metaObject().className() == "Gui::TreeWidget"
    ]
    for tree in trees:
        if tree.isVisible():
            return tree
    return trees[0] if trees else None


def _report_view():
    for edit in FreeCADGui.getMainWindow().findChildren(QtWidgets.QTextEdit):
        if edit.objectName() == "Report view":
            return edit
    return None


class TreeFoldersBase(BrowserFoldersBase):
    def setUp(self):
        # Before the document is built, so a skip leaves nothing behind for tearDown
        self.tree = _tree()
        if self.tree is None:
            raise unittest.SkipTest("No model tree in this test environment")
        # PySide ties the wrapper of a row got through child() to its parent row's wrapper,
        # and marks it deleted once the parent's is freed. Every row walked is held here.
        self._held = []
        super().setUp()

    def tearDown(self):
        self._held = []
        super().tearDown()

    def _hold(self, item):
        self._held.append(item)
        return item

    def _doc_item(self):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.type() == DOCUMENT_TYPE and top.text(0) == self.doc.Label:
                return self._hold(top)
        self.fail("No tree row for the test document")

    def _item_of(self, obj, root=None, text=None):
        """First row (depth first) whose text is `text`, or the object's label if not given.

        A row's text is not always its object's Label: an origin feature under a body
        showing folders reads by role ("XY plane") instead.
        """
        wanted = obj.Label if text is None else text
        stack = [root or self._doc_item()]
        while stack:
            item = self._hold(stack.pop(0))
            for i in range(item.childCount()):
                child = item.child(i)
                if child.type() == OBJECT_TYPE and child.text(0) == wanted:
                    return self._hold(child)
                stack.append(child)
        return None

    def _rows(self, item):
        """(type, text) of every direct child row."""
        item.setExpanded(True)
        _process_events()
        return [(item.child(i).type(), item.child(i).text(0)) for i in range(item.childCount())]

    def _folder(self, key_label):
        body = self._item_of(self.body)
        body.setExpanded(True)
        _process_events()
        for i in range(body.childCount()):
            child = body.child(i)
            if child.type() == FOLDER_TYPE and child.text(0).split(" (")[0] == key_label:
                return self._hold(child)
        return None


class TestFolderRows(TreeFoldersBase):
    def test_body_rows_are_origin_then_three_folders(self):
        rows = self._rows(self._item_of(self.body))
        self.assertEqual(rows[0][0], OBJECT_TYPE)
        self.assertEqual(rows[0][1], "Origin")
        self.assertEqual(
            rows[1:],
            [
                (FOLDER_TYPE, "Sketches (2)"),
                (FOLDER_TYPE, "Construction"),
                (FOLDER_TYPE, "History (1)"),
            ],
        )

    def test_folders_hold_their_objects(self):
        self.assertEqual(
            [t for _, t in self._rows(self._folder("Sketches"))], ["Sketch", "Sketch001"]
        )
        self.assertEqual(
            [t for _, t in self._rows(self._folder("Construction"))], ["DatumPlane", "ShapeBinder"]
        )
        self.assertEqual([t for _, t in self._rows(self._folder("History"))], ["Pad"])

    def test_history_keeps_the_sketch_under_its_feature(self):
        pad = self._item_of(self.pad, self._folder("History"))
        self.assertEqual([t for _, t in self._rows(pad)], ["Sketch"])

    def test_the_tip_has_no_row_of_its_own_at_body_level(self):
        texts = [t for _, t in self._rows(self._item_of(self.body))]
        self.assertNotIn(self.pad.Label, texts)

    def test_default_expansion(self):
        self.assertTrue(self._folder("Sketches").isExpanded())
        self.assertFalse(self._folder("Construction").isExpanded())
        self.assertFalse(self._folder("History").isExpanded())

    def test_new_datum_lands_in_construction_live(self):
        self.body.newObject("PartDesign::Line", "DatumLine")
        self.doc.recompute()
        _process_events(300)
        self.assertIn("DatumLine", [t for _, t in self._rows(self._folder("Construction"))])

    def test_undoing_the_only_construction_objects_removes_the_folder(self):
        # Review Focus 2
        self.doc.removeObject(self.binder.Name)
        self.doc.recompute()
        self.doc.openTransaction("add plane")
        self.doc.removeObject(self.plane.Name)
        self.doc.commitTransaction()
        self.doc.recompute()
        _process_events(300)
        self.assertIsNone(self._folder("Construction"))
        self.doc.undo()
        self.doc.recompute()
        _process_events(300)
        self.assertIsNotNone(self._folder("Construction"))

    def test_preference_off_gives_the_stock_layout_and_on_restores_it(self):
        self.params.SetBool("BodyFolders", False)
        _process_events(300)
        rows = self._rows(self._item_of(self.body))
        self.assertNotIn(FOLDER_TYPE, [k for k, _ in rows])
        self.assertIn(self.pad.Label, [t for _, t in rows])
        self.params.SetBool("BodyFolders", True)
        _process_events(300)
        self.assertIsNotNone(self._folder("Sketches"))

    def test_other_objects_are_unchanged(self):
        part = self.doc.addObject("App::Part", "Part")
        box = self.doc.addObject("Part::Box", "Box")
        part.addObject(box)
        self.doc.recompute()
        _process_events(300)
        self.assertEqual(self._rows(self._item_of(part))[-1], (OBJECT_TYPE, "Box"))


class TestFolderDragAndDrop(TreeFoldersBase):
    """Dragging over a row inside a folder: the row's parent is the folder, not an object."""

    def _drag_over(self, pos):
        """Sends the tree a drag entering and moving to pos, then leaving, as QDrag would."""
        viewport = self.tree.viewport()
        mime = QtCore.QMimeData()
        mime.setData(self.tree.model().mimeTypes()[0], QtCore.QByteArray())
        app = QtWidgets.QApplication.instance()
        enter = QtGui.QDragEnterEvent(
            pos, QtCore.Qt.MoveAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
        )
        app.sendEvent(viewport, enter)
        move = QtGui.QDragMoveEvent(
            pos, QtCore.Qt.MoveAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
        )
        app.sendEvent(viewport, move)
        app.sendEvent(viewport, QtGui.QDragLeaveEvent())
        # The tree's drag key filter is only taken down again by a real QDrag
        app.removeEventFilter(self.tree)
        _process_events()

    def test_dragging_over_a_row_in_a_folder_targets_the_body(self):
        # A move-drag over Pad (which takes no drops) retargets to Pad's parent. That used to
        # be the History folder row, read as an object row.
        pad = self._item_of(self.pad, self._folder("History"))
        self.assertIsNotNone(pad)
        FreeCADGui.Selection.addSelection(self.free_sketch)
        _process_events()
        self.tree.scrollToItem(pad)
        _process_events()
        rect = self.tree.visualItemRect(pad)
        pos = QtCore.QPoint(rect.center().x(), rect.top() + 1)  # the in-between zone
        hit = self._hold(self.tree.itemAt(pos)) if self.tree.isVisible() else None
        if hit is None or hit.type() != OBJECT_TYPE or hit.text(0) != self.pad.Label:
            self.skipTest("The Pad row is not on screen in this test environment")

        report = _report_view()
        if report is None:
            self.skipTest("No Report view to catch an error in this test environment")
        before = len(report.toPlainText())
        self._drag_over(pos)

        # GUIApplication::notify turns the bad read into a reported exception, not a crash
        self.assertNotIn("Unhandled", report.toPlainText()[before:])
        self.assertEqual([t for _, t in self._rows(self._folder("History"))], [self.pad.Label])


class TestFolderInteraction(TreeFoldersBase):
    """Selection, editing, search and drops around folder rows."""

    def _point_on(self, item):
        """A point on the item's row near the right end of the label column, or a skip.

        The right end keeps clear of the row's icons, whose clicks toggle visibility.
        """
        if QtTest is None:
            self.skipTest("QtTest is not available in this build")
        self.tree.scrollToItem(item)
        _process_events()
        rect = self.tree.visualItemRect(item)
        header = self.tree.header()
        column_end = header.sectionViewportPosition(0) + header.sectionSize(0)
        pos = QtCore.QPoint(min(rect.right(), column_end) - 4, rect.center().y())
        hit = self._hold(self.tree.itemAt(pos)) if self.tree.isVisible() else None
        if hit is None or hit.type() != item.type() or hit.text(0) != item.text(0):
            self.skipTest("The row is not on screen in this test environment")
        return pos

    def _click(self, item):
        pos = self._point_on(item)
        QtTest.QTest.mouseClick(
            self.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos
        )
        _process_events(200)

    def test_selecting_the_sketch_in_the_document_highlights_its_folder_row(self):
        FreeCADGui.Selection.addSelection(
            self.doc.Name, self.body.Name, self.free_sketch.Name + "."
        )
        _process_events(300)
        row = self._item_of(self.free_sketch, self._folder("Sketches"))
        self.assertTrue(row.isSelected())

    def test_clicking_a_sketch_row_selects_body_dot_sketch(self):
        row = self._item_of(self.free_sketch, self._folder("Sketches"))
        self._click(row)
        sel = FreeCADGui.Selection.getSelectionEx("", 0)
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0].Object.Name, self.body.Name)
        self.assertEqual(list(sel[0].SubElementNames), [self.free_sketch.Name + "."])

    def test_clicking_a_folder_selects_nothing(self):
        FreeCADGui.Selection.addSelection(self.doc.Name, self.pad.Name)
        _process_events()
        folder = self._folder("Construction")
        self._click(folder)
        self.assertFalse(folder.isSelected())
        self.assertEqual(FreeCADGui.Selection.getSelection(), [])

    def test_a_folder_cannot_be_renamed_or_dragged(self):
        folder = self._folder("Sketches")
        flags = folder.flags()
        self.assertFalse(flags & QtCore.Qt.ItemIsSelectable)
        self.assertFalse(flags & QtCore.Qt.ItemIsDragEnabled)
        self.assertFalse(flags & QtCore.Qt.ItemIsEditable)
        self.tree.setCurrentItem(folder)
        self.tree.editItem(folder)  # what F2 ends up calling
        # The tree's own Rename action, as its context menu would run it
        for action in self.tree.findChildren(QtGui.QAction):
            if action.text() == "Rename":
                action.trigger()
        _process_events()
        self.assertEqual(self.tree.state(), QtWidgets.QAbstractItemView.NoState)
        self.assertEqual(folder.text(0), "Sketches (2)")

    def test_double_click_toggles_a_folder(self):
        folder = self._folder("Construction")
        self.assertFalse(folder.isExpanded())
        pos = self._point_on(folder)
        QtTest.QTest.mouseDClick(
            self.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos
        )
        _process_events(200)
        self.assertTrue(folder.isExpanded())

    def test_search_finds_an_object_inside_a_folder(self):
        # The tree only opens rows to a new selection while it syncs with the selection
        saved_sync = self.params.GetBool("SyncSelection", True)
        self.params.SetBool("SyncSelection", True)
        self.addCleanup(self.params.SetBool, "SyncSelection", saved_sync)
        folder = self._folder("Construction")
        folder.setExpanded(False)
        body = self._item_of(self.body)
        body.setExpanded(False)
        _process_events()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.body.Name, self.plane.Name + ".")
        _process_events(300)
        # showItem has to open the folder and the body above it to reveal the row
        self.assertTrue(folder.isExpanded())
        self.assertTrue(body.isExpanded())

    def test_expanding_the_path_to_a_row_in_a_folder_opens_its_body(self):
        # Unlike the selection, this reaches showItem with no scroll to open the rows after it
        folder = self._folder("Construction")
        folder.setExpanded(False)
        body = self._item_of(self.body)
        body.setExpanded(False)
        _process_events()
        FreeCADGui.getDocument(self.doc.Name).toggleTreeItem(self.body, 2, self.plane.Name + ".")
        _process_events()
        self.assertTrue(body.isExpanded())
        self.assertTrue(folder.isExpanded())

    def test_select_all_on_a_folder_child_selects_its_siblings(self):
        row = self._item_of(self.sketch, self._folder("Sketches"))
        self.tree.setCurrentItem(row)
        FreeCADGui.Selection.addSelection(self.doc.Name, self.body.Name, self.sketch.Name + ".")
        _process_events()
        self.tree.selectAll()
        _process_events(200)
        names = {o.Name for o in FreeCADGui.Selection.getSelection()}
        # The body's other children too, not only the ones in the same folder
        self.assertIn(self.free_sketch.Name, names)
        self.assertIn(self.plane.Name, names)
        self.assertIn(self.pad.Name, names)

    def test_select_all_on_a_folder_selects_its_rows(self):
        # A row first, so the tree's selection changes and forgets any earlier select-all
        self.tree.setCurrentItem(self._item_of(self.sketch, self._folder("Sketches")))
        _process_events()
        folder = self._folder("Construction")
        self.tree.setCurrentItem(folder)
        _process_events()
        self.tree.selectAll()
        _process_events(200)
        names = {o.Name for o in FreeCADGui.Selection.getSelection()}
        self.assertEqual(names, {self.plane.Name, self.binder.Name})

    def _popup_from_right_click(self, item):
        """Right-clicks the row and reports whether a popup menu opened.

        A timer closes whatever popup it finds, so a menu that opens can't be left up: its
        exec loop runs the timer. If no menu opens, the event returns at once.
        """
        pos = self._point_on(item)
        app = QtWidgets.QApplication.instance()
        seen = []

        def close_popup():
            popup = app.activePopupWidget()
            if popup is not None:
                seen.append(popup.metaObject().className())
                popup.close()

        timer = QtCore.QTimer()
        timer.timeout.connect(close_popup)
        timer.start(100)
        try:
            event = QtGui.QContextMenuEvent(
                QtGui.QContextMenuEvent.Reason.Mouse, pos, self.tree.viewport().mapToGlobal(pos)
            )
            app.sendEvent(self.tree.viewport(), event)
            _process_events(300)
        finally:
            timer.stop()
            close_popup()
        return seen

    def test_right_clicking_a_folder_opens_no_menu(self):
        # An object row opens the tree's menu, so the check below can see one
        sketch = self._item_of(self.free_sketch, self._folder("Sketches"))
        self.assertTrue(self._popup_from_right_click(sketch))
        # The folder's would act on whatever is selected, which is not the folder
        FreeCADGui.Selection.addSelection(self.doc.Name, self.pad.Name)
        _process_events()
        self.assertEqual(self._popup_from_right_click(self._folder("History")), [])

    def _press_alt(self, key):
        # Straight to the tree, past the application's shortcuts
        event = QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress, key, QtCore.Qt.AltModifier)
        QtWidgets.QApplication.instance().sendEvent(self.tree, event)
        _process_events()

    def test_alt_down_expands_the_rows_inside_folders(self):
        history = self._folder("History")
        pad = self._item_of(self.pad, history)
        self.assertFalse(pad.isExpanded())
        self.tree.setCurrentItem(self._item_of(self.body))
        _process_events()
        self._press_alt(QtCore.Qt.Key_Down)
        self.assertTrue(history.isExpanded())
        self.assertTrue(pad.isExpanded())

    def test_alt_up_collapses_the_rows_inside_folders_but_not_the_folders(self):
        sketches = self._folder("Sketches")
        history = self._folder("History")
        pad = self._item_of(self.pad, history)
        history.setExpanded(True)
        pad.setExpanded(True)
        self.tree.setCurrentItem(self._item_of(self.body))
        _process_events()
        self._press_alt(QtCore.Qt.Key_Up)
        self.assertTrue(sketches.isExpanded())
        self.assertTrue(history.isExpanded())
        self.assertFalse(pad.isExpanded())

    def _send_drop(self, pos):
        """A drag entering, moving and dropping at pos, as QDrag would deliver them."""
        viewport = self.tree.viewport()
        mime = QtCore.QMimeData()
        mime.setData(self.tree.model().mimeTypes()[0], QtCore.QByteArray())
        app = QtWidgets.QApplication.instance()
        buttons, mods = QtCore.Qt.LeftButton, QtCore.Qt.NoModifier
        try:
            app.sendEvent(
                viewport, QtGui.QDragEnterEvent(pos, QtCore.Qt.MoveAction, mime, buttons, mods)
            )
            app.sendEvent(
                viewport, QtGui.QDragMoveEvent(pos, QtCore.Qt.MoveAction, mime, buttons, mods)
            )
            app.sendEvent(
                viewport,
                QtGui.QDropEvent(QtCore.QPointF(pos), QtCore.Qt.MoveAction, mime, buttons, mods),
            )
        finally:
            # The tree's drag key filter and dragging state are only reset by a real QDrag
            app.removeEventFilter(self.tree)
            app.sendEvent(viewport, QtGui.QDragLeaveEvent())
            _process_events(300)

    def test_dropping_on_a_folder_moves_into_its_body(self):
        other = self.doc.addObject("PartDesign::Body", "Body001")
        loose = other.newObject("Sketcher::SketchObject", "Loose")
        self.doc.recompute()
        _process_events(300)
        self.assertTrue(self.body.ViewObject.canDropObject(loose))
        source = self._item_of(loose, self._item_of(other))
        self.tree.setCurrentItem(source)
        _process_events()
        target = self._folder("Sketches")
        pos = self._point_on(target)
        self.assertTrue(source.isSelected())
        self._send_drop(pos)
        self.doc.recompute()
        _process_events(300)
        self.assertIn(loose, self.body.Group)
        self.assertNotIn(loose, other.Group)

    def test_body_inside_a_part_keeps_the_full_subname(self):
        # Review Focus 1
        part = self.doc.addObject("App::Part", "Part")
        part.addObject(self.body)
        self.doc.recompute()
        _process_events(300)
        FreeCADGui.Selection.addSelection(
            self.doc.Name, part.Name, self.body.Name + "." + self.free_sketch.Name + "."
        )
        _process_events(300)
        body_row = self._item_of(self.body, self._item_of(part))
        body_row.setExpanded(True)
        _process_events()
        sketches = None
        for i in range(body_row.childCount()):
            child = body_row.child(i)
            if child.type() == FOLDER_TYPE and child.text(0).startswith("Sketches"):
                sketches = self._hold(child)
        self.assertIsNotNone(sketches)
        row = self._item_of(self.free_sketch, sketches)
        self.assertTrue(row.isSelected())

    def test_a_link_to_a_body_shows_its_children_flat(self):
        # Review Focus 3
        link = self.doc.addObject("App::Link", "BodyLink")
        link.LinkedObject = self.body
        self.doc.recompute()
        _process_events(300)
        rows = self._rows(self._item_of(link))
        self.assertNotIn(FOLDER_TYPE, [k for k, _ in rows])

    def test_deleting_a_body_with_a_current_open_folder_is_safe(self):
        # Review Focus 4
        folder = self._folder("Construction")
        folder.setExpanded(True)
        self.tree.setCurrentItem(folder)
        _process_events()
        name = self.doc.Name
        self.body.removeObjectsFromDocument()
        self.doc.removeObject(self.body.Name)
        _process_events(300)
        FreeCAD.closeDocument(name)
        _process_events(300)
        self.assertNotIn(name, FreeCAD.listDocuments())


class TestFolderEyeAndExpansion(TreeFoldersBase):
    """The eye on a folder row, and whether a folder is open, kept in the saved file."""

    def _eye_point(self, item):
        """The middle of the row's eye, as the tree hit-tests it, or a skip."""
        if QtTest is None:
            self.skipTest("QtTest is not available in this build")
        self.tree.scrollToItem(item)
        _process_events()
        rect = self.tree.visualItemRect(item)
        style = self.tree.style()
        margin = style.pixelMetric(QtWidgets.QStyle.PM_FocusFrameHMargin) + 1
        # iconSize() is (-1, -1) unless the icon height preference is set
        size = self.tree.iconSize().height()
        if size <= 0:
            size = style.pixelMetric(QtWidgets.QStyle.PM_SmallIconSize)
        pos = QtCore.QPoint(rect.left() + margin + size // 2, rect.center().y())
        hit = self._hold(self.tree.itemAt(pos)) if self.tree.isVisible() else None
        if hit is None or hit.type() != item.type() or hit.text(0) != item.text(0):
            self.skipTest("The row is not on screen in this test environment")
        return pos

    def _eye_click(self, item):
        pos = self._eye_point(item)
        QtTest.QTest.mouseClick(
            self.tree.viewport(), QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, pos
        )
        _process_events(200)

    def test_folder_eye_hides_every_sketch_in_one_undo_step(self):
        self.sketch.Visibility = True
        self.free_sketch.Visibility = True
        self.doc.recompute()
        _process_events()
        before = self.doc.UndoCount
        self._eye_click(self._folder("Sketches"))
        self.assertFalse(self.sketch.Visibility)
        self.assertFalse(self.free_sketch.Visibility)
        self.assertEqual(self.doc.UndoCount, before + 1)
        self.doc.undo()
        _process_events(200)
        self.assertTrue(self.sketch.Visibility)
        self.assertTrue(self.free_sketch.Visibility)

    def test_folder_eye_leaves_an_open_transaction_open(self):
        # A task dialog keeps one open until OK or Cancel; the eye must not commit it
        before = self.doc.UndoCount
        self.doc.openTransaction("pending")
        self.pad.Length = 20.0
        self._eye_click(self._folder("Sketches"))
        self.doc.abortTransaction()
        _process_events(200)
        self.assertEqual(self.pad.Length.Value, 10.0)
        self.assertEqual(self.doc.UndoCount, before)

    def test_folder_eye_shows_all_when_all_are_hidden(self):
        self.sketch.Visibility = False
        self.free_sketch.Visibility = False
        _process_events()
        self._eye_click(self._folder("Sketches"))
        self.assertTrue(self.sketch.Visibility)
        self.assertTrue(self.free_sketch.Visibility)

    def test_folder_expansion_survives_save_and_reload(self):
        import os
        import shutil
        import tempfile

        tmp = tempfile.mkdtemp(prefix="TestBrowserFolders")
        self.addCleanup(shutil.rmtree, tmp, True)
        # Both away from their defaults: Construction starts closed, Sketches open
        self._folder("Construction").setExpanded(True)
        self._folder("Sketches").setExpanded(False)
        _process_events()
        # Named after the document, so tearDown's prefix match still closes it
        path = os.path.join(tmp, self.doc_name + ".FCStd")
        self.doc.saveAs(path)
        self._held = []  # as tearDown does, before the rows go
        FreeCAD.closeDocument(self.doc.Name)
        _process_events(200)
        self.doc = FreeCAD.openDocument(path)
        _process_events(500)
        self.body = self.doc.getObject("Body")
        self.assertTrue(self._folder("Construction").isExpanded())
        self.assertFalse(self._folder("Sketches").isExpanded())


class TestOriginNames(TreeFoldersBase):
    """A body's Origin row and its features read by role while folders are shown."""

    def test_origin_rows_show_role_names_and_keep_their_labels(self):
        origin_row = self._item_of(self.body.Origin, self._item_of(self.body), text="Origin")
        self.assertEqual(origin_row.text(0), "Origin")
        texts = sorted(t for _, t in self._rows(origin_row))
        self.assertEqual(
            texts,
            sorted(
                ["X axis", "Y axis", "Z axis", "XY plane", "XZ plane", "YZ plane", "Origin point"]
            ),
        )
        xy = self._origin_feature(self.body, "XY_Plane")
        self.assertNotEqual(xy.Label, "XY plane")  # the document keeps the real label

    def test_role_names_go_away_with_the_preference(self):
        self.params.SetBool("BodyFolders", False)
        _process_events(300)
        origin_row = self._item_of(self.body.Origin, self._item_of(self.body))
        self.assertEqual(origin_row.text(0), self.body.Origin.Label)
