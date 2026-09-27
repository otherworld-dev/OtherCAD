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

"""GUI regression tests for a feature panel saying why the feature cannot be built.

A value the feature cannot be built with, or OK pressed on one, only put the reason
in the Report view, and the panel stayed open without a word. The reason now shows
at the top of the panel while the value is wrong, and goes once it is put right.

To run tests:
    FreeCAD -t TestFeaturePanelErrors
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtWidgets

ERROR_LABEL = "FeatureErrorLabel"


class TestFeaturePanelErrors(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("The panel needs a main window")

        self.doc = FreeCAD.newDocument("TestFeaturePanelErrors")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        FreeCADGui.ActiveDocument.ActiveView.setActiveObject("pdbody", self.body)
        sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = (self.body.Origin.OriginFeatures[3], [""])  # XY_Plane
        sketch.MapMode = "FlatFace"
        corners = [
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(10, 0, 0),
            FreeCAD.Vector(10, 6, 0),
            FreeCAD.Vector(0, 6, 0),
        ]
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]), False)
        for index in range(4):
            sketch.addConstraint(Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1))
        self.pad = self.body.newObject("PartDesign::Pad", "Pad")
        self.pad.Profile = sketch
        self.pad.Length = 10
        self.doc.recompute()

        FreeCADGui.ActiveDocument.setEdit(self.pad.Name)
        self._process_events(200)
        self.lengthEdit = self._widget("lengthEdit")
        if self.lengthEdit is None:
            raise unittest.SkipTest("The Pad panel did not open in this test environment")

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

    @staticmethod
    def _widget(name, kind=QtWidgets.QWidget):
        for widget in FreeCADGui.getMainWindow().findChildren(kind, name):
            if widget.isVisible():
                return widget
        return None

    def _set_length(self, value):
        self.lengthEdit.setProperty("rawValue", float(value))
        self._process_events(200)

    def testAWrongValueIsExplainedInThePanel(self):
        self.assertIsNone(self._widget(ERROR_LABEL), "a valid feature shows no message")

        self._set_length(0)

        label = self._widget(ERROR_LABEL, QtWidgets.QLabel)
        self.assertIsNotNone(label, "the panel said nothing about the failed feature")
        self.assertEqual(label.text(), self.pad.getStatusString())

    def testTheMessageGoesOnceTheValueIsPutRight(self):
        self._set_length(0)
        self._set_length(10)

        self.assertIsNone(self._widget(ERROR_LABEL))

    def testOkOnAFailedFeatureKeepsThePanelWithTheReason(self):
        self._set_length(0)

        accepted = FreeCADGui.Control.activeTaskDialog().accept()
        self._process_events(200)

        self.assertFalse(accepted)
        self.assertTrue(FreeCADGui.Control.activeDialog())
        self.assertIsNotNone(self._widget(ERROR_LABEL))
