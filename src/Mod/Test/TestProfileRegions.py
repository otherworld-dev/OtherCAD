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

"""GUI regression tests for when the Extrude panel opens ready to pick regions.

A sketch whose curves cross cannot be extruded as a whole, so the feature starts
on one of its regions as a stand-in and the panel opens ready to pick the real one.
Any other sketch with several regions, such as a square with a hole in it, is
extruded whole, and the panel used to open ready to pick for those as well, which
showed the sketch over the preview and made the first click throw the whole-sketch
profile, or the regions picked earlier, away.

To run tests:
    FreeCAD -t TestProfileRegions
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
from PySide import QtCore, QtWidgets


class TestProfileRegions(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The extrude task panel needs a main window")

        self.doc = FreeCAD.newDocument("TestProfileRegions")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        FreeCADGui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)

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

    def _sketch(self, rectangles, lines=()):
        sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = (self.body.Origin.OriginFeatures[3], [""])  # XY_Plane
        sketch.MapMode = "FlatFace"
        for x0, y0, x1, y1 in rectangles:
            corners = [
                FreeCAD.Vector(x0, y0, 0),
                FreeCAD.Vector(x1, y0, 0),
                FreeCAD.Vector(x1, y1, 0),
                FreeCAD.Vector(x0, y1, 0),
            ]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                sketch.addGeometry(Part.LineSegment(start, end), False)
        for x0, y0, x1, y1 in lines:
            sketch.addGeometry(
                Part.LineSegment(FreeCAD.Vector(x0, y0, 0), FreeCAD.Vector(x1, y1, 0)), False
            )
        self.doc.recompute()
        return sketch

    def _crossed_square(self):
        """A square with a line running right through it: two regions, but no wire of the
        sketch closes around either of them, so it cannot be built from as a whole."""
        return self._sketch([(0, 0, 10, 10)], lines=[(5, -2, 5, 12)])

    def _pick_button(self):
        main = FreeCADGui.getMainWindow()
        for button in main.findChildren(QtWidgets.QToolButton, "ProfilePickButton"):
            if button.isVisible():
                return button
        return None

    def _extrude(self, sketch):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.body.Name, sketch.Name + ".")
        FreeCADGui.runCommand("PartDesign_Extrude")
        self._process_events(200)
        feature = [obj for obj in self.body.Group if obj.isDerivedFrom("PartDesign::Pad")][-1]
        return feature

    # -- tests -----------------------------------------------------------

    def testASketchThatFacesWholeOpensWithoutPicking(self):
        # A square with a square hole: two regions, extruded as a ring
        sketch = self._sketch([(0, 0, 10, 10), (3, 3, 7, 7)])
        feature = self._extrude(sketch)

        button = self._pick_button()
        self.assertIsNotNone(button, "the profile row should show for several regions")
        self.assertFalse(button.isChecked(), "the whole sketch is no stand-in to replace")
        self.assertEqual([sub for sub in feature.Profile[1] if sub], [])

    def testCrossingCurvesOpenReadyToPick(self):
        feature = self._extrude(self._crossed_square())

        self.assertEqual(list(feature.Profile[1]), ["InternalFace1"])
        button = self._pick_button()
        self.assertIsNotNone(button)
        self.assertTrue(button.isChecked(), "the stand-in region is there to be replaced")

    def testEditingChosenRegionsOpensWithoutPicking(self):
        sketch = self._crossed_square()
        pad = self.body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = (sketch, ["InternalFace1", "InternalFace2"])
        pad.Length = 5
        self.doc.recompute()

        FreeCADGui.ActiveDocument.setEdit(pad.Name)
        self._process_events(200)

        button = self._pick_button()
        self.assertIsNotNone(button)
        self.assertFalse(button.isChecked(), "a first click would throw the chosen regions away")
