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

"""GUI regression tests for Select Other run from outside the 3D view.

Select Other looks under the pointer. Run from the ribbon, a menu or the command
palette the pointer is over the button, not the view, so it used to find nothing
and quietly do nothing. It now waits for the next click in the view and opens its
menu there, and Esc gives up waiting.

The tests move the real pointer off the view and put it back afterwards.

To run tests:
    FreeCAD -t TestSelectOther
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets


class TestSelectOther(unittest.TestCase):
    def setUp(self):
        try:
            main_window = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main_window = None
        if main_window is None:
            raise unittest.SkipTest("Select Other needs a main window")

        self.doc = FreeCAD.newDocument("TestSelectOther")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        box = self.doc.addObject("Part::Box", "Box")
        box.Length = box.Width = box.Height = 10
        self.doc.recompute()
        self.view = FreeCADGui.getDocument(self.doc.Name).ActiveView
        self.view.viewIsometric()
        self.view.fitAll()
        self._process_events(200)
        FreeCADGui.Selection.clearSelection()

        self.saved_cursor = QtGui.QCursor.pos()
        # Over the window's frame, the way it is when a ribbon button is clicked
        QtGui.QCursor.setPos(main_window.mapToGlobal(QtCore.QPoint(2, 2)))
        self._process_events()
        self.popup_actions = None

    def tearDown(self):
        closer = getattr(self, "closer", None)
        if closer is not None:
            closer.stop()
        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        QtGui.QCursor.setPos(self.saved_cursor)
        self._send_key(QtCore.Qt.Key_Escape)
        FreeCADGui.Selection.clearSelection()
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        self._process_events()

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _viewport(self):
        return self.view.graphicsView().viewport()

    def _send_key(self, key):
        app = QtWidgets.QApplication.instance()
        target = QtWidgets.QApplication.focusWidget() or FreeCADGui.getMainWindow()
        for event_type in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            app.sendEvent(target, QtGui.QKeyEvent(event_type, key, QtCore.Qt.NoModifier))

    def _click_view_centre(self):
        viewport = self._viewport()
        local = QtCore.QPointF(viewport.width() / 2.0, viewport.height() / 2.0)
        glob = QtCore.QPointF(viewport.mapToGlobal(local.toPoint()))
        app = QtWidgets.QApplication.instance()
        for event_type in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            buttons = (
                QtCore.Qt.LeftButton
                if event_type == QtCore.QEvent.MouseButtonPress
                else QtCore.Qt.NoButton
            )
            event = QtGui.QMouseEvent(
                event_type, local, glob, QtCore.Qt.LeftButton, buttons, QtCore.Qt.NoModifier
            )
            app.sendEvent(viewport, event)

    def _close_popup_soon(self):
        """Note what the menu offers and close it, as it runs an event loop of its own.

        The menu opens a moment after the click, so this keeps looking for a while
        rather than trusting one timer to land after it.
        """

        self.closer = QtCore.QTimer()
        self.closer.setInterval(50)
        deadline = time.monotonic() + 5.0

        def close():
            popup = QtWidgets.QApplication.activePopupWidget()
            if popup is not None:
                if self.popup_actions is None:
                    self.popup_actions = [action.text() for action in popup.actions()]
                popup.close()
            elif time.monotonic() > deadline:
                self.closer.stop()

        self.closer.timeout.connect(close)
        self.closer.start()

    # -- tests -----------------------------------------------------------

    def testFromOutsideTheViewItWaitsForAClick(self):
        FreeCADGui.runCommand("Std_ClarifySelection")
        self._process_events()
        self.assertIsNone(QtWidgets.QApplication.activePopupWidget())

        self._close_popup_soon()
        self._click_view_centre()
        self._process_events(600)

        self.assertIsNotNone(self.popup_actions, "The click should have opened the menu")
        self.assertTrue(self.popup_actions, "The box is under the view's centre")

    def testTheWaitingClickDoesNotSelect(self):
        FreeCADGui.runCommand("Std_ClarifySelection")
        self._process_events()

        self._close_popup_soon()
        self._click_view_centre()
        self._process_events(600)

        self.assertEqual(FreeCADGui.Selection.getSelectionEx(), [])

    def testEscapeGivesUp(self):
        FreeCADGui.runCommand("Std_ClarifySelection")
        self._process_events()
        self._send_key(QtCore.Qt.Key_Escape)
        self._process_events()

        self._close_popup_soon()
        self._click_view_centre()
        self._process_events(600)

        self.assertIsNone(self.popup_actions, "After Esc a click in the view is a plain click")
