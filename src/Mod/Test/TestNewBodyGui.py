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

"""GUI regression tests for the New body operation of the Extrude panel.

Choosing New body used to make the feature's solid the extrusion alone, so the body
lost everything before it and no new body appeared. Pressing OK now gives the
extrusion a body of its own, makes that body active, and leaves the old one as it
was, all as one undo step.

To run tests:
    FreeCAD -t TestNewBodyGui
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtWidgets

# PartDesign::FeatureAddSub::OperationType, see src/Mod/PartDesign/App/FeatureAddSub.h.
NEW_BODY = 3

CUBE = 1000.0


class TestNewBodyGui(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The extrude task panel needs a main window")

        self.doc = FreeCAD.newDocument("TestNewBodyGui")
        self.doc.UndoMode = 1
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)

        self.body = self.doc.addObject("PartDesign::Body", "Body")
        FreeCADGui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)
        cube = self._sketch("Cube", 0.0)
        pad = self.body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = cube
        pad.Length = 10.0
        self.doc.recompute()
        self.other = self._sketch("Other", 20.0)
        self.doc.recompute()
        self._process_events()
        self.assertAlmostEqual(self.body.Shape.Volume, CUBE, places=3)

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
            self._process_events()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _sketch(self, name, x):
        """A closed 10 x 10 square with its lower left corner at (x, 0)."""
        sketch = self.body.newObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (self.body.Origin.OriginFeatures[3], [""])  # XY_Plane
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
        return sketch

    @staticmethod
    def _find_widget(name):
        main = FreeCADGui.getMainWindow()
        fallback = None
        for widget in main.findChildren(QtWidgets.QWidget, name):
            if widget.isVisible():
                return widget
            if fallback is None:
                fallback = widget
        return fallback

    def _bodies(self):
        return [obj for obj in self.doc.Objects if obj.isDerivedFrom("PartDesign::Body")]

    def _extrude_other_as_new_body(self):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.body.Name, self.other.Name + ".")
        FreeCADGui.runCommand("PartDesign_Extrude")
        self._process_events(100)

        operation = self._find_widget("operationMode")
        if operation is None:
            self.skipTest("The Extrude task panel did not open in this test environment")
        operation.setCurrentIndex(NEW_BODY)
        self._process_events()

        feature = [obj for obj in self.body.Group if obj.isDerivedFrom("PartDesign::Pad")][-1]
        self.assertEqual(feature.Operation, "NewBody")
        # While the panel is open the feature passes the body's cube through. The panel
        # recomputes the feature alone, so the body's own shape is not current yet.
        self.assertAlmostEqual(feature.Shape.Volume, CUBE, places=3)

        FreeCADGui.Control.activeTaskDialog().accept()
        self._process_events(100)
        return feature

    # -- tests -----------------------------------------------------------

    def testOkMakesANewBodyAndKeepsTheOldOne(self):
        feature = self._extrude_other_as_new_body()

        bodies = self._bodies()
        self.assertEqual(len(bodies), 2)
        newBody = [body for body in bodies if body is not self.body][0]
        self.assertIn(feature, newBody.Group)
        self.assertIn(self.other, newBody.Group)
        self.assertAlmostEqual(self.body.Shape.Volume, CUBE, places=3)
        self.assertAlmostEqual(newBody.Shape.Volume, 10.0 * 10.0 * feature.Length.Value, places=3)

    def testTheNewBodyIsActive(self):
        self._extrude_other_as_new_body()

        active = FreeCADGui.ActiveDocument.ActiveView.getActiveObject("pdbody")
        self.assertIsNotNone(active)
        self.assertIsNot(active, self.body)

    def testOldBodyStaysVisible(self):
        self._extrude_other_as_new_body()

        self.assertTrue(self.body.Visibility)
        self.assertTrue(self.body.Tip.Visibility)

    def testOneUndoTakesItAllBack(self):
        self._extrude_other_as_new_body()

        self.doc.undo()
        self.doc.recompute()
        self._process_events()

        self.assertEqual(len(self._bodies()), 1)
        self.assertEqual(
            [obj for obj in self.body.Group if obj.isDerivedFrom("PartDesign::Pad")],
            [self.body.Tip],
        )
        self.assertAlmostEqual(self.body.Shape.Volume, CUBE, places=3)
