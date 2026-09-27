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

"""GUI regression tests for a task panel wider than the overlay it sits in.

With the Tasks panel on the right-hand overlay, a sketch's panels need more width than
an overlay left narrow, and the panel was laid out at its own minimum inside the
narrower overlay, which cut it off at the edge of the screen. The overlay now grows
to the left while its panels need it, and goes back to the width the user chose.

To run tests:
    FreeCAD -t TestOverlayPanelWidth
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtWidgets

RIGHT_OVERLAY = "User parameter:BaseApp/MainWindow/DockWindows/OverlayRight"
NARROW = 200


class TestOverlayPanelWidth(unittest.TestCase):
    def setUp(self):
        try:
            self.window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            self.window = None
        if self.window is None:
            raise unittest.SkipTest("The overlay needs a main window")

        self.params = FreeCAD.ParamGet(RIGHT_OVERLAY)
        self.oldWidth = self.params.GetInt("Width", 0)
        self.toggled = False
        if self._tasks_overlay() is None:
            FreeCADGui.runCommand("Std_DockOverlayToggleRight")
            self.toggled = True
            self._process_events(300)
        if self._tasks_overlay() is None:
            self._restore()
            raise unittest.SkipTest("The Tasks panel could not be put on the right overlay")
        self.params.SetInt("Width", NARROW)
        self._process_events(200)

        self.doc = FreeCAD.newDocument("TestOverlayPanelWidth")
        body = self.doc.addObject("PartDesign::Body", "Body")
        self.sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (body.Origin.OriginFeatures[3], [""])
        self.sketch.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        if FreeCADGui.ActiveDocument and FreeCADGui.ActiveDocument.getInEdit():
            FreeCADGui.ActiveDocument.resetEdit()
            self._process_events(200)
        if getattr(self, "doc", None) and self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        self._restore()

    def _restore(self):
        if self.oldWidth:
            self.params.SetInt("Width", self.oldWidth)
        if self.toggled:
            FreeCADGui.runCommand("Std_DockOverlayToggleRight")
        self._process_events(200)

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _tasks_overlay(self):
        """The right overlay holding the Tasks panel, if it holds it."""
        for widget in QtWidgets.QApplication.instance().allWidgets():
            if widget.metaObject().className() != "Gui::OverlayTabWidget":
                continue
            docks = widget.findChildren(QtWidgets.QDockWidget, "Tasks")
            if docks and widget.geometry().left() > self.window.width() // 2:
                return widget
        return None

    def _mdi(self):
        return self.window.findChild(QtWidgets.QMdiArea)

    def testTheOverlayIsWideEnoughForTheSketchPanels(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self._process_events(500)
        FreeCADGui.runCommand("Sketcher_CompCreateRectangles", 0)
        self._process_events(500)

        overlay = self._tasks_overlay()
        tasks = overlay.findChild(QtWidgets.QDockWidget, "Tasks")
        self.assertGreater(
            tasks.minimumSizeHint().width(), NARROW, "the sketch panels no longer need more room"
        )
        self.assertGreaterEqual(overlay.width(), tasks.minimumSizeHint().width())
        self.assertLessEqual(tasks.width(), overlay.width(), "the panel is cut off")
        self.assertLessEqual(overlay.geometry().right(), self._mdi().geometry().right())

    def testTheChosenWidthIsKeptAndComesBack(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self._process_events(500)
        self.assertEqual(self.params.GetInt("Width"), NARROW)

        FreeCADGui.ActiveDocument.resetEdit()
        self._process_events(500)

        self.assertEqual(self.params.GetInt("Width"), NARROW)
