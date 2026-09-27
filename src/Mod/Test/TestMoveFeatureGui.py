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

"""GUI regression tests for moving a feature to another body.

Only a feature with nothing before it can be moved, the first solid of a body.
PartDesign_MoveFeature took it out with the group's removeObjects(), which does
not know about a body's chain of features, so the solid after it still took the
moved one as its base, across the two bodies. The body's own removeObject()
hands that solid the base the moved one had, which is none.

To run tests:
    FreeCAD -t TestMoveFeatureGui
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
from PySide import QtCore, QtWidgets


class TestMoveFeatureGui(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("Moving a feature asks for the body in a dialog")

        self.doc = FreeCAD.newDocument("TestMoveFeatureGui")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.source = self.doc.addObject("PartDesign::Body", "Source")
        self.target = self.doc.addObject("PartDesign::Body", "Target")

        self.sketch1 = self._sketch("Sketch1", 0)
        self.pad1 = self._pad("Pad1", self.sketch1, 10)
        self.sketch2 = self._sketch("Sketch2", 20)
        self.pad2 = self._pad("Pad2", self.sketch2, 5)
        self.doc.recompute()

    def tearDown(self):
        FreeCADGui.Selection.clearSelection()
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _sketch(self, name, x):
        sketch = self.source.newObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (self.source.Origin.OriginFeatures[3], [""])  # XY_Plane
        sketch.MapMode = "FlatFace"
        corners = [
            FreeCAD.Vector(x, 0, 0),
            FreeCAD.Vector(x + 10, 0, 0),
            FreeCAD.Vector(x + 10, 10, 0),
            FreeCAD.Vector(x, 10, 0),
        ]
        for start, end in zip(corners, corners[1:] + corners[:1]):
            sketch.addGeometry(Part.LineSegment(start, end), False)
        return sketch

    def _pad(self, name, sketch, length):
        pad = self.source.newObject("PartDesign::Pad", name)
        pad.Profile = sketch
        pad.Length = length
        return pad

    def _move(self, feature):
        """Run the command, taking the only other body the dialog offers."""

        tries = [40]

        def accept():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is not None:
                dialog.accept()
            elif tries[0] > 0:
                tries[0] -= 1
                QtCore.QTimer.singleShot(50, accept)

        QtCore.QTimer.singleShot(100, accept)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, feature.Name)
        FreeCADGui.runCommand("PartDesign_MoveFeature")
        self._process_events(200)
        self.doc.recompute()

    def testTheSolidAfterItNoLongerBuildsOnIt(self):
        self._move(self.pad1)

        self.assertEqual([obj.Name for obj in self.source.Group], ["Sketch2", "Pad2"])
        self.assertIsNone(self.pad2.BaseFeature)
        self.assertIs(self.source.Tip, self.pad2)
        self.assertAlmostEqual(self.source.Shape.Volume, 500.0, places=3)

    def testTheFeatureArrivesWithItsSketchFirst(self):
        self._move(self.pad1)

        self.assertEqual([obj.Name for obj in self.target.Group], ["Sketch1", "Pad1"])
        self.assertIs(self.target.Tip, self.pad1)
        self.assertAlmostEqual(self.target.Shape.Volume, 1000.0, places=3)
        for obj in self.doc.Objects:
            self.assertTrue(obj.isValid(), f"{obj.Name}: {obj.getStatusString()}")
