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

"""GUI regression tests for finding and fixing a reference that has gone.

A fillet on one corner of a padded square loses its edge when the sketch becomes a
triangle. The fillet's panel used to list the reference as "?Edge5", and the
timeline's tooltip gave the shape's internal name for it. The panel now marks it as
missing, and the timeline says which edge of which feature has gone.

To run tests:
    FreeCAD -t TestMissingReferenceGui
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtWidgets


class TestMissingReferenceGui(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The fillet panel needs a main window")

        self.doc = FreeCAD.newDocument("TestMissingReferenceGui")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        FreeCADGui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)
        self.sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (self.body.Origin.OriginFeatures[3], [""])  # XY_Plane
        self.sketch.MapMode = "FlatFace"
        self._draw([(0, 0), (10, 0), (10, 10), (0, 10)])
        pad = self.body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = self.sketch
        pad.Length = 10
        self.doc.recompute()

        self.edge = None
        for index, edge in enumerate(pad.Shape.Edges, start=1):
            a, b = (vertex.Point for vertex in edge.Vertexes)
            if abs(a.z - b.z) > 5 and abs(a.x - 10) < 1e-6 and abs(a.y - 10) < 1e-6:
                self.edge = f"Edge{index}"
        self.fillet = self.body.newObject("PartDesign::Fillet", "Fillet")
        self.fillet.Base = (pad, [self.edge])
        self.fillet.Radius = 1
        self.doc.recompute()

        self.sketch.deleteAllGeometry()
        self._draw([(0, 0), (10, 0), (0, 10)])
        self.doc.recompute()
        self._process_events(300)

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
            self._process_events()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _draw(self, corners):
        points = [FreeCAD.Vector(x, y, 0) for x, y in corners]
        for start, end in zip(points, points[1:] + points[:1]):
            self.sketch.addGeometry(Part.LineSegment(start, end), False)
        for i in range(len(points)):
            self.sketch.addConstraint(
                Sketcher.Constraint("Coincident", i, 2, (i + 1) % len(points), 1)
            )

    def testThePanelMarksTheReferenceAsMissing(self):
        self.assertFalse(self.fillet.isValid())
        FreeCADGui.ActiveDocument.setEdit(self.fillet.Name)
        self._process_events(300)

        lists = [
            widget
            for widget in FreeCADGui.getMainWindow().findChildren(
                QtWidgets.QListWidget, "listWidgetReferences"
            )
            if widget.isVisible()
        ]
        self.assertEqual(len(lists), 1, "the fillet panel did not open")
        texts = [lists[0].item(row).text() for row in range(lists[0].count())]
        self.assertEqual(texts, [f"{self.edge} (missing)"])
        self.assertIn("no longer exists", lists[0].item(0).toolTip())

    def testTheTimelineSaysWhichEdgeHasGone(self):
        markers = [
            marker
            for marker in FreeCADGui.getMainWindow().findChildren(
                QtWidgets.QWidget, "TimelineMarker"
            )
            if not marker.isHidden() and marker.toolTip().split("\n")[0] == "Fillet"
        ]
        if not markers:
            self.skipTest("The timeline is not shown in this test environment")
        self.assertIn(f"{self.edge} of Pad no longer exists", markers[0].toolTip())
