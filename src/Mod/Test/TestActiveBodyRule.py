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

"""GUI regression tests for the active-body rule.

A new feature used to need an active body before anything else: with none active a
modal picker came up, and a sketch, face or edge of a body other than the active one
was refused or met with a copy/cross-reference question. Now a feature goes into the
body of what it is made from, which becomes the active one; a document without a body
gets one silently; and a reference to another body's face (an up-to face) becomes a
shape binder in the feature's own body. The picker is left only for a document with
several bodies, none active and nothing selected.

To run tests:
    FreeCAD -t TestActiveBodyRule
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtWidgets


def _process_events(wait_ms=50):
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    time.sleep(wait_ms / 1000.0)
    app.processEvents()


class ModalWatch:
    """Records, and closes, every modal dialog that comes up while it runs.

    The behaviour under test is that no dialog appears. Closing one keeps a regression
    a plain failure instead of a test run that waits on a dialog nobody answers.
    """

    def __init__(self):
        self.seen = []
        self.timer = QtCore.QTimer()
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def _poll(self):
        widget = QtWidgets.QApplication.activeModalWidget()
        if widget is None:
            return
        self.seen.append(widget.metaObject().className() + ": " + widget.windowTitle())
        if isinstance(widget, QtWidgets.QDialog):
            widget.reject()
        else:
            widget.close()

    def stop(self):
        self.timer.stop()


class ActiveBodyRuleBase(unittest.TestCase):
    doc_name = "TestActiveBodyRule"

    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The commands under test need a main window")

        self.doc = FreeCAD.newDocument(self.doc_name)
        self.doc.UndoMode = 1
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.watch = ModalWatch()

    def tearDown(self):
        self.watch.stop()
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
            _process_events()
        gui_doc = (
            FreeCADGui.getDocument(self.doc.Name)
            if self.doc.Name in FreeCAD.listDocuments()
            else None
        )
        if gui_doc is not None and gui_doc.getInEdit() is not None:
            gui_doc.resetEdit()
        FreeCADGui.Selection.clearSelection()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        _process_events()

    # -- helpers ---------------------------------------------------------

    def _view(self):
        return FreeCADGui.getDocument(self.doc.Name).ActiveView

    def _active_body(self):
        return self._view().getActiveObject("pdbody")

    def _deactivate(self):
        self._view().setActiveObject("pdbody", None)
        _process_events()
        self.assertIsNone(self._active_body())

    def _bodies(self):
        return [obj for obj in self.doc.Objects if obj.isDerivedFrom("PartDesign::Body")]

    def _body_with_pad(self, name, x):
        """A body with a 10 x 10 x 5 block whose lower corner is at (x, 0, 0)."""
        body = self.doc.addObject("PartDesign::Body", name)
        self.doc.recompute()
        xy = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
        sketch = body.newObject("Sketcher::SketchObject", name + "Sketch")
        sketch.AttachmentSupport = (xy, [""])
        sketch.MapMode = "FlatFace"
        corners = [
            FreeCAD.Vector(x, 0, 0),
            FreeCAD.Vector(x + 10, 0, 0),
            FreeCAD.Vector(x + 10, 10, 0),
            FreeCAD.Vector(x, 10, 0),
        ]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]), False)
        for index in range(4):
            sketch.addConstraint(Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1))
        self.doc.recompute()
        pad = body.newObject("PartDesign::Pad", name + "Pad")
        pad.Profile = sketch
        pad.Length = 5.0
        self.doc.recompute()
        return body, sketch, pad

    @staticmethod
    def _face_at_height(feature, z):
        for index, face in enumerate(feature.Shape.Faces):
            if abs(face.CenterOfMass.z - z) < 1e-6 and abs(face.normalAt(0, 0).z) > 0.99:
                return "Face%d" % (index + 1)
        raise AssertionError("No horizontal face at z = %g" % z)

    def _select(self, body, sub):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, body.Name, sub)
        _process_events()

    def _run(self, command):
        FreeCADGui.runCommand(command, 0)
        _process_events(200)

    def _new_features(self, before, type_name):
        return [
            obj
            for obj in self.doc.Objects
            if obj.Name not in before and obj.isDerivedFrom(type_name)
        ]

    def _close_edit(self, accept=True):
        dialog = FreeCADGui.Control.activeTaskDialog()
        if dialog is not None:
            if accept:
                dialog.accept()
            else:
                dialog.reject()
        _process_events(100)


class TestSelectionPicksTheBody(ActiveBodyRuleBase):
    """A feature goes into the body of the sketch, face or edge it is made from."""

    def setUp(self):
        super().setUp()
        self.a, self.a_sketch, self.a_pad = self._body_with_pad("A", 0.0)
        self.b, self.b_sketch, self.b_pad = self._body_with_pad("B", 20.0)

    def test_extruding_a_sketch_with_no_active_body_uses_its_body(self):
        self._deactivate()
        sketch = self.b.newObject("Sketcher::SketchObject", "Second")
        sketch.AttachmentSupport = self.a_sketch.AttachmentSupport
        sketch.MapMode = "FlatFace"
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(25, 5, 0), FreeCAD.Vector(0, 0, 1), 2), False)
        self.doc.recompute()
        before = {obj.Name for obj in self.doc.Objects}
        self._select(self.b, sketch.Name + ".")
        self._run("PartDesign_Extrude")
        self.assertEqual(self.watch.seen, [])
        self.assertEqual(self._active_body().Name, self.b.Name)
        pads = self._new_features(before, "PartDesign::Pad")
        self.assertEqual(len(pads), 1)
        self.assertTrue(self.b.hasObject(pads[0]))
        self._close_edit()

    def test_extruding_another_bodys_sketch_switches_to_that_body(self):
        self._view().setActiveObject("pdbody", self.a)
        _process_events()
        sketch = self.b.newObject("Sketcher::SketchObject", "Second")
        sketch.AttachmentSupport = self.b_sketch.AttachmentSupport
        sketch.MapMode = "FlatFace"
        sketch.addGeometry(Part.Circle(FreeCAD.Vector(25, 5, 0), FreeCAD.Vector(0, 0, 1), 2), False)
        self.doc.recompute()
        before = {obj.Name for obj in self.doc.Objects}
        self._select(self.b, sketch.Name + ".")
        self._run("PartDesign_Extrude")
        self.assertEqual(self.watch.seen, [])
        self.assertEqual(self._active_body().Name, self.b.Name)
        pads = self._new_features(before, "PartDesign::Pad")
        self.assertEqual(len(pads), 1)
        self.assertTrue(self.b.hasObject(pads[0]))
        # No copy of the sketch was made to bring it into the active body
        self.assertEqual(self._new_features(before, "PartDesign::ShapeBinder"), [])
        self._close_edit()

    def test_sketching_on_another_bodys_face_sketches_in_that_body(self):
        self._view().setActiveObject("pdbody", self.a)
        _process_events()
        top = self._face_at_height(self.b_pad, 5.0)
        before = {obj.Name for obj in self.doc.Objects}
        self._select(self.b, self.b_pad.Name + "." + top)
        self._run("PartDesign_NewSketch")
        self.assertEqual(self.watch.seen, [])
        self.assertEqual(self._active_body().Name, self.b.Name)
        sketches = self._new_features(before, "Sketcher::SketchObject")
        self.assertEqual(len(sketches), 1)
        self.assertTrue(self.b.hasObject(sketches[0]))
        support = sketches[0].AttachmentSupport
        self.assertEqual(support[0][0].Name, self.b_pad.Name)
        self.assertEqual(self._new_features(before, "PartDesign::ShapeBinder"), [])

    def test_filleting_another_bodys_edge_switches_to_that_body(self):
        self._view().setActiveObject("pdbody", self.a)
        _process_events()
        before = {obj.Name for obj in self.doc.Objects}
        self._select(self.b, self.b_pad.Name + ".Edge1")
        self._run("PartDesign_Fillet")
        self.assertEqual(self.watch.seen, [])
        self.assertEqual(self._active_body().Name, self.b.Name)
        fillets = self._new_features(before, "PartDesign::Fillet")
        self.assertEqual(len(fillets), 1)
        self.assertTrue(self.b.hasObject(fillets[0]))
        self._close_edit()

    def test_several_bodies_with_nothing_selected_still_ask(self):
        self._deactivate()
        FreeCADGui.Selection.clearSelection()
        self._run("PartDesign_NewSketch")
        self.assertEqual(len(self.watch.seen), 1, self.watch.seen)
        self.assertIn("DlgActiveBody", self.watch.seen[0])


class TestNoBodyMakesOne(ActiveBodyRuleBase):
    """A document without a body gets one silently, and keeps it in the same undo step."""

    def test_a_datum_plane_in_an_empty_document_makes_a_body(self):
        self._run("PartDesign_Plane")
        self.assertEqual(self.watch.seen, [])
        bodies = self._bodies()
        self.assertEqual(len(bodies), 1)
        self.assertEqual(self._active_body().Name, bodies[0].Name)
        planes = [obj for obj in self.doc.Objects if obj.isDerivedFrom("PartDesign::Plane")]
        self.assertEqual(len(planes), 1)
        self.assertTrue(bodies[0].hasObject(planes[0]))

    def test_cancelling_takes_the_new_body_away_too(self):
        self._run("PartDesign_Plane")
        self.assertEqual(len(self._bodies()), 1)
        self._close_edit(accept=False)
        self.assertEqual(self._bodies(), [])

    def test_a_new_document_starts_without_a_body(self):
        # The design choice: rule 1 covers the first sketch, so Ctrl+N stays empty
        self.assertEqual(self._bodies(), [])


class TestReferenceIntoAnotherBody(ActiveBodyRuleBase):
    """An up-to face on another body becomes a shape binder in the feature's own body."""

    def setUp(self):
        super().setUp()
        self.a, self.a_sketch, self.a_pad = self._body_with_pad("A", 0.0)
        self.b, self.b_sketch, self.b_pad = self._body_with_pad("B", 0.0)
        self.b_pad.Length = 20.0
        self.doc.recompute()
        self._view().setActiveObject("pdbody", self.a)
        _process_events()

    def _pick_up_to_face(self, face):
        self.a_pad.Type = "UpToFace"
        self.doc.recompute()
        # As a double-click on the feature does, so Cancel has something to undo
        self.doc.openTransaction("Edit Pad")
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.a_pad.Name)
        _process_events(200)
        buttons = [
            b
            for b in FreeCADGui.getMainWindow().findChildren(QtWidgets.QToolButton, "buttonFace")
            if b.isVisible()
        ]
        if not buttons:
            self.skipTest("The extrude panel did not open in this test environment")
        buttons[0].setChecked(True)
        _process_events()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.b.Name, self.b_pad.Name + "." + face)
        _process_events(200)

    def test_an_up_to_face_on_another_body_becomes_a_binder(self):
        before = {obj.Name for obj in self.doc.Objects}
        self._pick_up_to_face(self._face_at_height(self.b_pad, 20.0))
        self.assertEqual(self.watch.seen, [])
        binders = self._new_features(before, "PartDesign::ShapeBinder")
        self.assertEqual(len(binders), 1)
        binder = binders[0]
        self.assertTrue(self.a.hasObject(binder))
        self.assertEqual(binder.Support[0][0].Name, self.b_pad.Name)
        # Before the feature that uses it, so the history reads in order
        group = self.a.Group
        self.assertLess(group.index(binder), group.index(self.a_pad))
        self.assertEqual(self.a_pad.UpToFace[0].Name, binder.Name)
        self._close_edit()
        self.assertAlmostEqual(self.a_pad.Shape.Volume, 10 * 10 * 20, places=3)
        self.assertEqual(self._active_body().Name, self.a.Name)

    def test_cancelling_the_panel_takes_the_binder_away(self):
        before = {obj.Name for obj in self.doc.Objects}
        self._pick_up_to_face(self._face_at_height(self.b_pad, 20.0))
        self.assertEqual(len(self._new_features(before, "PartDesign::ShapeBinder")), 1)
        self._close_edit(accept=False)
        self.assertEqual(self._new_features(before, "PartDesign::ShapeBinder"), [])
