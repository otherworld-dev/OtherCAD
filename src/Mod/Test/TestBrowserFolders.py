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

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtGui, QtWidgets

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

    def _item_of(self, obj, root=None):
        """First row (depth first) whose text is the object's label."""
        stack = [root or self._doc_item()]
        while stack:
            item = self._hold(stack.pop(0))
            for i in range(item.childCount()):
                child = item.child(i)
                if child.type() == OBJECT_TYPE and child.text(0) == obj.Label:
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
        self.assertEqual(rows[0][1], self.body.Origin.Label)
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
