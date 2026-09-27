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

"""GUI regression tests for starting Extrude with nothing selected.

Extrude with nothing selected used to list the document's sketches by name, with
the ones already used hidden. It now waits for a click in the 3D view, as Fusion
does: a region of a sketch starts the feature on that region, a curve on the whole
sketch. The body's sketches are shown while it waits, so another region of a sketch
already used is one click away.

The picks are made through the selection, the same way a click in the view reaches
the command.

To run tests:
    FreeCAD -t TestProfilePick
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
from PySide import QtCore, QtGui, QtWidgets

PICK_PANEL = "PartDesignGui__TaskProfilePick"


class TestProfilePick(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The pick waits in the task panel")

        self.doc = FreeCAD.newDocument("TestProfilePick")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        FreeCADGui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)

        # Two separate squares, so two regions
        self.sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (self.body.Origin.OriginFeatures[3], [""])  # XY_Plane
        self.sketch.MapMode = "FlatFace"
        for x in (0, 20):
            corners = [
                FreeCAD.Vector(x, 0, 0),
                FreeCAD.Vector(x + 10, 0, 0),
                FreeCAD.Vector(x + 10, 10, 0),
                FreeCAD.Vector(x, 10, 0),
            ]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                self.sketch.addGeometry(Part.LineSegment(start, end), False)
        self.doc.recompute()
        FreeCADGui.Selection.clearSelection()
        self._process_events()

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
            self._process_events()
        QtWidgets.QApplication.sendPostedEvents(None, QtCore.QEvent.DeferredDelete)
        FreeCADGui.Selection.clearSelection()
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _widget(self, name, kind=QtWidgets.QWidget):
        main = FreeCADGui.getMainWindow()
        for widget in main.findChildren(kind, name):
            if widget.isVisible():
                return widget
        return None

    def _pads(self):
        return [obj for obj in self.body.Group if obj.isDerivedFrom("PartDesign::Pad")]

    def _start_extrude(self):
        FreeCADGui.runCommand("PartDesign_Extrude")
        self._process_events(150)
        self.assertIsNotNone(self._widget(PICK_PANEL), "Extrude did not wait for a pick")

    def _pick(self, sub):
        FreeCADGui.Selection.addSelection(
            self.doc.Name, self.body.Name, f"{self.sketch.Name}.{sub}"
        )
        self._process_events(300)

    # -- tests -----------------------------------------------------------

    def testWithNothingSelectedExtrudeWaitsForAPick(self):
        self.sketch.Visibility = False
        self._start_extrude()

        self.assertEqual(self._pads(), [], "nothing is built before the pick")
        self.assertTrue(self.sketch.Visibility, "the body's sketches are shown to pick from")

    def testARegionStartsTheFeatureOnThatRegion(self):
        self._start_extrude()
        self._pick("InternalFace2")

        pads = self._pads()
        self.assertEqual(len(pads), 1)
        self.assertIs(pads[0].Profile[0], self.sketch)
        self.assertEqual(list(pads[0].Profile[1]), ["InternalFace2"])
        button = self._widget("ProfilePickButton", QtWidgets.QToolButton)
        self.assertIsNotNone(button)
        self.assertTrue(button.isChecked(), "more regions can be added straight away")

    def testACurveStartsTheFeatureOnTheWholeSketch(self):
        self._start_extrude()
        self._pick("Edge1")

        pads = self._pads()
        self.assertEqual(len(pads), 1)
        self.assertEqual([sub for sub in pads[0].Profile[1] if sub], [])

    def testAnotherRegionOfAUsedSketchIsOneClickAway(self):
        first = self.body.newObject("PartDesign::Pad", "Pad")
        first.Profile = (self.sketch, ["InternalFace1"])
        first.Length = 5
        self.doc.recompute()
        self.sketch.Visibility = False
        self._process_events()

        self._start_extrude()
        self.assertTrue(self.sketch.Visibility)
        self._pick("InternalFace2")

        pads = self._pads()
        self.assertEqual(len(pads), 2)
        self.assertEqual(list(pads[1].Profile[1]), ["InternalFace2"])

    def testAClickInTheViewPicksTheRegionUnderIt(self):
        """A real click, as the others go through the selection. The first square is already
        a pad, so this also checks the sketch can be picked where no solid covers it."""

        first = self.body.newObject("PartDesign::Pad", "Pad")
        first.Profile = (self.sketch, ["InternalFace1"])
        first.Length = 5
        self.doc.recompute()
        self.sketch.Visibility = False
        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        view.fitAll()
        self._process_events(300)

        self._start_extrude()
        self._process_events(300)

        viewport = view.graphicsView().viewport()
        px, py = view.getPointOnScreen(FreeCAD.Vector(25, 5, 0))
        dpr = viewport.devicePixelRatioF()
        local = QtCore.QPointF(px / dpr, viewport.height() - 1 - py / dpr)
        glob = QtCore.QPointF(viewport.mapToGlobal(local.toPoint()))
        app = QtWidgets.QApplication.instance()
        app.sendEvent(
            viewport,
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseMove,
                local,
                glob,
                QtCore.Qt.NoButton,
                QtCore.Qt.NoButton,
                QtCore.Qt.NoModifier,
            ),
        )
        self._process_events(100)
        for kind, buttons in (
            (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
            (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
        ):
            app.sendEvent(
                viewport,
                QtGui.QMouseEvent(
                    kind, local, glob, QtCore.Qt.LeftButton, buttons, QtCore.Qt.NoModifier
                ),
            )
        self._process_events(400)

        pads = self._pads()
        self.assertEqual(len(pads), 2, "the click did not start a feature")
        self.assertIs(pads[1].Profile[0], self.sketch)
        self.assertEqual(list(pads[1].Profile[1]), ["InternalFace2"])

    def testEscapeGivesUpAndHidesTheSketchesAgain(self):
        self.sketch.Visibility = False
        self._start_extrude()

        viewport = FreeCADGui.ActiveDocument.ActiveView.graphicsView().viewport()
        app = QtWidgets.QApplication.instance()
        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            app.sendEvent(
                viewport, QtGui.QKeyEvent(kind, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier)
            )
        self._process_events(300)

        self.assertIsNone(self._widget(PICK_PANEL))
        self.assertEqual(self._pads(), [])
        self.assertFalse(self.sketch.Visibility)
