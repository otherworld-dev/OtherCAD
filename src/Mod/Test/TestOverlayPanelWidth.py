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
    @classmethod
    def setUpClass(cls):
        cls.window = FreeCADGui.getMainWindow() if hasattr(FreeCADGui, "getMainWindow") else None
        cls.params = FreeCAD.ParamGet(RIGHT_OVERLAY)
        cls.oldWidth = cls.params.GetInt("Width", 0)
        cls.toggled = False
        if cls.window is None:
            return
        # Once for the class: taking the panel off the overlay and putting it back
        # between tests leaves it hidden
        if cls._tasks_overlay() is None:
            FreeCADGui.runCommand("Std_DockOverlayToggleRight")
            cls.toggled = True
            cls._process_events(300)

    @classmethod
    def tearDownClass(cls):
        if cls.oldWidth:
            cls.params.SetInt("Width", cls.oldWidth)
        if cls.toggled:
            FreeCADGui.runCommand("Std_DockOverlayToggleRight")
        cls._process_events(200)

    def setUp(self):
        if self.window is None:
            raise unittest.SkipTest("The overlay needs a main window")
        if self._tasks_overlay() is None:
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

    @staticmethod
    def _process_events(wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    @staticmethod
    def _tasks_overlay():
        """The overlay holding the Tasks panel, if one does. It is known by what it holds,
        as a hidden overlay is parked at the top left whatever edge it belongs to."""
        for widget in QtWidgets.QApplication.instance().allWidgets():
            if widget.metaObject().className() != "Gui::OverlayTabWidget":
                continue
            if widget.findChildren(QtWidgets.QDockWidget, "Tasks"):
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

    def testTheOverlayGrowsWhenTheOpenPanelNeedsMore(self):
        """A panel can need more room while the overlay is already on screen, as when a
        dialog adds boxes, and nothing else then puts the overlay in place again."""

        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        overlay = self._tasks_overlay()
        deadline = time.monotonic() + 3.0
        while not overlay.isVisible() and time.monotonic() < deadline:
            self._process_events(100)
        self._process_events(300)
        tasks = overlay.findChild(QtWidgets.QDockWidget, "Tasks")
        self.assertTrue(
            overlay.isVisible(),
            f"the sketch did not show the panel: overlay {overlay.geometry()}, tasks visible "
            f"{tasks.isVisible()}, dialog {FreeCADGui.Control.activeDialog()}, edit "
            f"{FreeCADGui.ActiveDocument.getInEdit()}",
        )
        tasks = overlay.findChild(QtWidgets.QDockWidget, "Tasks")
        wider = overlay.width() + 120

        tasks.widget().setMinimumWidth(wider)
        try:
            self._process_events(500)
            # Its minimumSize(), rather than the hint, is what Qt holds the panel to
            self.assertGreaterEqual(tasks.width(), wider, "the panel did not get its room")
            self.assertLessEqual(tasks.width(), overlay.width(), "the panel is cut off")
            self.assertLessEqual(overlay.geometry().right(), self._mdi().geometry().right())
        finally:
            tasks.widget().setMinimumWidth(0)

    def testTheChosenWidthIsKeptAndComesBack(self):
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self._process_events(500)
        self.assertEqual(self.params.GetInt("Width"), NARROW)

        FreeCADGui.ActiveDocument.resetEdit()
        self._process_events(500)

        self.assertEqual(self.params.GetInt("Width"), NARROW)
