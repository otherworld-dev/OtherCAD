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

"""GUI regression tests for the Fusion style timeline dock.

Rolling the history back moves the tip of the body and hides the sketches and
datums the playhead has not reached yet. Which ones the strip hid is kept on the
body's view provider, so it travels with the document: saving while rolled back
and opening the file again still knows what to put back, and so does a switch to
another body and back. Every step is one undo entry, and undoing it puts the tip
where it was.

To run tests:
    FreeCAD -t TestTimeline
"""

import os
import shutil
import tempfile
import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtGui, QtWidgets

# The strip and the dock that holds it share this object name, so the class name
# is what tells them apart. Both are set in Gui::Timeline::TimelineWidget.
TIMELINE_NAME = "Timeline"
TIMELINE_CLASS = "Gui::Timeline::TimelineWidget"
MARKER_NAME = "TimelineMarker"

# Sketch, Pad, Sketch001, Pad001.
FEATURE_COUNT = 4


class TestTimeline(unittest.TestCase):
    """The timeline has to remember its rollback and undo it one step at a time."""

    def setUp(self):
        self.window = FreeCADGui.getMainWindow()
        if self.window is None:
            raise unittest.SkipTest("The timeline dock needs a main window")

        self.widget = self._find_timeline()
        if self.widget is None:
            raise unittest.SkipTest("The timeline dock is not installed in this test environment")

        self.tempdir = tempfile.mkdtemp(prefix="TestTimeline")
        self.doc = FreeCAD.newDocument("TestTimeline")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self._build_body()
        self._activate_body()

        if not self._wait_for_markers(FEATURE_COUNT):
            raise unittest.SkipTest("The timeline strip never filled in this test environment")

    def tearDown(self):
        FreeCADGui.Selection.clearSelection()
        for name in list(FreeCAD.listDocuments()):
            if name.startswith("TestTimeline"):
                FreeCAD.closeDocument(name)
        self._process_events()
        shutil.rmtree(getattr(self, "tempdir", ""), ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _find_timeline(self):
        """The dock container carries the same object name as the strip inside it."""

        for candidate in self.window.findChildren(QtWidgets.QWidget, TIMELINE_NAME):
            if candidate.metaObject().className() == TIMELINE_CLASS:
                return candidate
        return None

    def _build_body(self):
        doc = self.doc
        self.body = doc.addObject("PartDesign::Body", "Body")
        doc.recompute()

        self.sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (doc.XY_Plane, [""])
        self.sketch.MapMode = "FlatFace"
        self.body.addObject(self.sketch)
        self._draw_rectangle(self.sketch, 10.0, 6.0)
        doc.recompute()

        self.pad = doc.addObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = 10.0
        self.body.addObject(self.pad)
        doc.recompute()

        # Both sketches sit on the XY plane. A second sketch on the pad's top face
        # would break as soon as the history rolled back past the pad, which is not
        # what these tests are about.
        self.sketch2 = doc.addObject("Sketcher::SketchObject", "Sketch001")
        self.sketch2.AttachmentSupport = (doc.XY_Plane, [""])
        self.sketch2.MapMode = "FlatFace"
        self.body.addObject(self.sketch2)
        self._draw_rectangle(self.sketch2, 4.0, 3.0)
        doc.recompute()

        self.pad2 = doc.addObject("PartDesign::Pad", "Pad001")
        self.pad2.Profile = self.sketch2
        self.pad2.Length = 20.0
        self.body.addObject(self.pad2)
        doc.recompute()

        self.sketch.Visibility = True
        self.sketch2.Visibility = True
        self._process_events()

    def _active_view(self, doc, timeout_ms=3000):
        """A freshly opened document takes a moment to get its 3D view."""

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            view = FreeCADGui.getDocument(doc.Name).ActiveView
            if view is not None:
                return view
            if time.monotonic() >= deadline:
                self.fail("The reopened document never got a 3D view")
            self._process_events(50)

    def _activate_body(self, body=None):
        """Only the active body fills the strip, so the timeline needs one either way."""

        target = self.body if body is None else body
        self._active_view(target.Document).setActiveObject("pdbody", target)
        self._process_events(200)

    def _wait_for_markers(self, count, timeout_ms=5000):
        """The strip is rebuilt from a timer, so it trails the document by a tick.

        Markers taken off the strip are hidden before they are deleted, and the ones
        on it are shown, so the explicit hide is what tells a live marker from a
        leftover no matter whether the dock itself is on screen.
        """

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            found = self.widget.findChildren(QtWidgets.QWidget, MARKER_NAME)
            if len([marker for marker in found if not marker.isHidden()]) == count:
                return True
            if time.monotonic() >= deadline:
                return False
            self._process_events(50)

    def _settle(self):
        """Long enough for the recompute, the deferred rebuild and its repaint."""

        self._process_events(300)
        self._process_events(100)

    def _invoke(self, slot):
        """Drive the strip through the slot its buttons and arrow keys share."""

        self.assertTrue(
            QtCore.QMetaObject.invokeMethod(self.widget, slot),
            "The timeline has no invokable " + slot + "()",
        )
        self._settle()

    def _focus(self, widget, timeout_ms=2000):
        """Hand the keyboard to one of the strip's own widgets, as Tab would.

        Whether this machine will give the application the keyboard at all is not
        something the timeline decides, and a window that reports itself active can
        still be waiting on the window manager, so the focus is asked for and then
        waited on rather than demanded in one go. What the strip *is* responsible
        for - the widget existing, being visible, and accepting focus at all - is
        asserted first, so a marker that stopped being reachable by keyboard still
        fails rather than quietly skipping.
        """

        self.assertIsNotNone(widget, "Expected a widget to put the focus on")
        self.assertTrue(
            widget.isVisible(),
            "A widget the keyboard can reach has to be on screen",
        )
        self.assertNotEqual(
            widget.focusPolicy(),
            QtCore.Qt.NoFocus,
            "The strip's widgets have to accept the keyboard to be reachable by Tab",
        )

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            if self.window.isActiveWindow():
                widget.setFocus(QtCore.Qt.OtherFocusReason)
            self._process_events()
            if QtWidgets.QApplication.focusWidget() is widget:
                return widget
            if time.monotonic() >= deadline:
                break

        raise unittest.SkipTest(
            "This machine did not hand the application the keyboard "
            "(window active: {}, focus went to: {!r})".format(
                self.window.isActiveWindow(),
                QtWidgets.QApplication.focusWidget(),
            )
        )

    def _focus_a_marker(self, label="Sketch"):
        """Put the keyboard on a marker, which is one of the two ways into the strip.

        Every step rebuilds the strip, so the marker that held the focus is gone by the
        time the next key is sent and a fresh one has to be picked up each time.
        """

        return self._focus(self._marker_for(label))

    def _step_button(self, index=0):
        """The back arrow, or the forward one at index 1."""

        buttons = self.widget.findChildren(QtWidgets.QToolButton, "TimelineStepButton")
        self.assertEqual(len(buttons), 2)
        return buttons[index]

    def _press(self, key):
        """Send the key where a real one goes: through the application, to the focus.

        Home is the shortcut of the Home view command and a shortcut is answered before
        the focused widget sees the key, so this only reaches the strip because the strip
        claims the key from the shortcut first.
        """

        marker = self._focus_a_marker()
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.instance().sendEvent(marker, event)
        self._settle()

    def _claims(self, key, target):
        """Whether the strip takes the key off whatever command shortcut owns it."""

        override = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, key, QtCore.Qt.NoModifier)
        override.ignore()
        QtWidgets.QApplication.instance().sendEvent(target, override)
        return override.isAccepted()

    def _click(self, widget):
        """A plain left click, press and release, on the middle of a widget."""

        centre = widget.rect().center()
        globally = widget.mapToGlobal(centre)
        for kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
            QtWidgets.QApplication.instance().sendEvent(
                widget,
                QtGui.QMouseEvent(
                    kind,
                    QtCore.QPointF(centre),
                    QtCore.QPointF(globally),
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.NoModifier,
                ),
            )
        self._process_events()

    def _marker_for(self, label):
        """Markers carry the feature's label as the first line of their tooltip."""

        for marker in self.widget.findChildren(QtWidgets.QWidget, MARKER_NAME):
            if marker.isHidden():
                continue
            if marker.toolTip().split("\n")[0] == label:
                return marker
        return None

    @staticmethod
    def _draw_rectangle(sketch, width, height):
        """A closed rectangle, the smallest profile a Pad will accept."""

        corners = [
            FreeCAD.Vector(0.0, 0.0, 0.0),
            FreeCAD.Vector(width, 0.0, 0.0),
            FreeCAD.Vector(width, height, 0.0),
            FreeCAD.Vector(0.0, height, 0.0),
        ]
        first = int(sketch.GeometryCount)
        for index in range(4):
            sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]), False)
        for index in range(4):
            sketch.addConstraint(
                Sketcher.Constraint("Coincident", first + index, 2, first + (index + 1) % 4, 1)
            )

    def _reopen(self):
        """Save, close and open again, and pick the reloaded objects back up."""

        path = os.path.join(self.tempdir, "TestTimeline.FCStd")
        name = self.doc.Name
        self.doc.saveAs(path)
        FreeCAD.closeDocument(name)
        self._process_events(200)

        self.doc = FreeCAD.openDocument(path)
        self._process_events(300)
        self.body = self.doc.getObject("Body")
        self.sketch = self.doc.getObject("Sketch")
        self.pad = self.doc.getObject("Pad")
        self.sketch2 = self.doc.getObject("Sketch001")
        self.pad2 = self.doc.getObject("Pad001")

    def _hidden_by_rollback(self):
        return list(self.body.ViewObject.RollbackHidden)

    # -- tests -----------------------------------------------------------

    def test_rollback_survives_a_save_and_a_reload(self):
        """The hidden list lives on the body, not in the widget, so a reload keeps it."""

        self.assertIs(self.body.Tip, self.pad2)
        self.assertTrue(self.sketch2.Visibility)

        # The first step lands on Sketch001 itself, which is still in front of the
        # playhead; the second puts the playhead behind it and takes it off screen.
        self._invoke("stepBack")
        self.assertIs(self.body.Tip, self.pad)
        self._invoke("stepBack")
        self.assertFalse(self.sketch2.Visibility)
        self.assertIn("Sketch001", self._hidden_by_rollback())

        self._reopen()

        # The widget was never told what it had hidden: the document was.
        self.assertIn("Sketch001", self.body.ViewObject.RollbackHidden)
        self.assertFalse(self.sketch2.Visibility)

        self._activate_body()
        self.assertTrue(self._wait_for_markers(FEATURE_COUNT))

        # The strip has rebuilt itself around the reloaded body, and the rollback is still
        # on: the playhead has to come back behind Sketch001 rather than snapping to the
        # tip and showing it again.
        self.assertFalse(self.sketch2.Visibility)
        self.assertIn("Sketch001", self._hidden_by_rollback())

        self._invoke("stepForward")

        self.assertTrue(self.sketch2.Visibility)
        self.assertNotIn("Sketch001", self._hidden_by_rollback())

    def test_rollback_survives_a_switch_to_another_body(self):
        """Leaving the body must not let go of what the rollback hid."""

        self._invoke("stepBack")
        self._invoke("stepBack")
        self.assertFalse(self.sketch2.Visibility)

        other = self.doc.addObject("PartDesign::Body", "Other")
        self.doc.recompute()
        self._activate_body(other)
        self._settle()

        self.assertIn("Sketch001", self._hidden_by_rollback())

        self._activate_body()
        self.assertTrue(self._wait_for_markers(FEATURE_COUNT))

        # Coming back to the body has to come back to the rollback as well.
        self.assertFalse(self.sketch2.Visibility)
        self.assertIn("Sketch001", self._hidden_by_rollback())

        self._invoke("stepForward")

        self.assertTrue(self.sketch2.Visibility)
        self.assertNotIn("Sketch001", self._hidden_by_rollback())

    def test_a_step_is_a_single_undo_entry(self):
        """Undo has to answer a step with a step, not with half of one."""

        before = self.doc.UndoCount
        self._invoke("stepBack")

        self.assertEqual(self.doc.UndoCount, before + 1)
        self.assertIs(self.body.Tip, self.pad)

    def test_undo_puts_back_the_tip_and_what_the_roll_hid(self):
        """Rolling to the start moves the tip and hides both sketches in one entry."""

        before = self.doc.UndoCount
        self._invoke("rollToStart")

        self.assertEqual(self.doc.UndoCount, before + 1)
        self.assertIsNone(self.body.Tip)
        self.assertFalse(self.sketch.Visibility)
        self.assertFalse(self.sketch2.Visibility)

        self.doc.undo()
        self._settle()

        self.assertIs(self.body.Tip, self.pad2)
        self.assertTrue(self.sketch.Visibility)
        self.assertTrue(self.sketch2.Visibility)
        self.assertEqual(self._hidden_by_rollback(), [])

    def test_rolling_back_to_the_end_shows_everything_again(self):
        self._invoke("rollToStart")
        self.assertIsNone(self.body.Tip)

        self._invoke("rollToEnd")

        self.assertIs(self.body.Tip, self.pad2)
        self.assertTrue(self.sketch.Visibility)
        self.assertTrue(self.sketch2.Visibility)
        self.assertEqual(self._hidden_by_rollback(), [])

    def test_the_steps_of_a_multitransform_are_not_markers(self):
        """The steps are edited through the MultiTransform and make no shape of their own,
        so the playhead must never stop on one and make it the tip."""

        # A MultiTransform with no originals yet passes for one of its own steps, so it
        # only becomes the body's next solid once it has them.
        multi = self.doc.addObject("PartDesign::MultiTransform", "MultiTransform")
        multi.Originals = [self.pad2]
        self.body.addObject(multi)
        step = self.body.newObject("PartDesign::LinearPattern", "LinearPattern")
        step.Direction = (self.sketch2, ["H_Axis"])
        step.Length = 30.0
        step.Occurrences = 2
        multi.Transformations = [step]
        self.doc.recompute()
        self.assertIs(self.body.Tip, multi)

        self.assertTrue(self._wait_for_markers(FEATURE_COUNT + 1))
        self.assertIsNone(self._marker_for("LinearPattern"))

        self._press(QtCore.Qt.Key_Left)
        self.assertIs(self.body.Tip, self.pad2)
        self._press(QtCore.Qt.Key_Right)
        self.assertIs(self.body.Tip, multi)

    def test_arrow_keys_roll_the_history(self):
        """Left and right step one feature, Home and End run to the ends of the strip."""

        self._press(QtCore.Qt.Key_Left)
        self.assertIs(self.body.Tip, self.pad)

        self._press(QtCore.Qt.Key_Right)
        self.assertIs(self.body.Tip, self.pad2)

        self._press(QtCore.Qt.Key_Home)
        self.assertIsNone(self.body.Tip)

        self._press(QtCore.Qt.Key_End)
        self.assertIs(self.body.Tip, self.pad2)

    def test_the_strip_claims_home_from_the_home_view_shortcut(self):
        """Home already belongs to Std_ViewHome, and a command shortcut is answered before
        the focused widget ever sees the key. Qt offers that widget the first refusal
        through a shortcut override, and the strip has to take it wherever inside itself
        the focus happens to be, or its Home is dead."""

        marker = self._focus_a_marker()
        button = self._step_button()

        for target in (marker, button):
            for key in (
                QtCore.Qt.Key_Home,
                QtCore.Qt.Key_End,
                QtCore.Qt.Key_Left,
                QtCore.Qt.Key_Right,
            ):
                self.assertTrue(
                    self._claims(key, target),
                    "The strip has to claim key {0} at {1}".format(
                        key, target.metaObject().className()
                    ),
                )

            # Everything the strip does not roll with is left to whoever else wants it.
            self.assertFalse(self._claims(QtCore.Qt.Key_Up, target))
            self.assertFalse(self._claims(QtCore.Qt.Key_F5, target))

    def test_pressing_home_on_a_focused_marker_rolls_the_history(self):
        """The whole way a real Home arrives: Qt offers the override to the marker that
        has the keyboard, the strip claims it, and the press then reaches the strip
        through the event filter it keeps on its markers."""

        marker = self._focus_a_marker()
        self.assertIs(self.body.Tip, self.pad2)

        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Home, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.instance().sendEvent(marker, event)
        self._settle()

        self.assertIsNone(self.body.Tip)

    def test_pressing_home_on_a_focused_step_button_rolls_the_history(self):
        """Tab lands on the arrows as readily as on a marker, so Home has to reach the
        strip from a focused button too rather than going to the Home view command."""

        button = self._focus(self._step_button())
        self.assertIs(self.body.Tip, self.pad2)

        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Home, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.instance().sendEvent(button, event)
        self._settle()

        self.assertIsNone(self.body.Tip)

    def test_a_click_does_not_leave_the_keyboard_in_the_strip(self):
        """Tab is the only way into the strip. Nothing around the markers may take the
        focus on a click, or an ordinary click on a marker would leave the keyboard in
        the timeline and it would go on answering keys, the claimed Home among them,
        that the user meant for the rest of the window."""

        scroll = self.widget.findChild(QtWidgets.QScrollArea, "TimelineScroll")
        self.assertIsNotNone(scroll)
        # A scroll area is Qt::WheelFocus by default, and the focus walk from a clicked
        # marker climbs to it: this is the one that has to be turned off by hand.
        self.assertEqual(scroll.focusPolicy(), QtCore.Qt.NoFocus)
        self.assertEqual(scroll.viewport().focusPolicy(), QtCore.Qt.NoFocus)
        strip = self.widget.findChild(QtWidgets.QWidget, "TimelineStrip")
        self.assertEqual(strip.focusPolicy(), QtCore.Qt.NoFocus)
        self.assertEqual(self.widget.focusPolicy(), QtCore.Qt.NoFocus)

        # Start with the keyboard in the 3D view, so the check below is about what the
        # click did rather than about wherever the focus happened to be.
        mdi = self.window.findChild(QtWidgets.QMdiArea)
        if mdi is not None and mdi.activeSubWindow() is not None:
            mdi.activeSubWindow().widget().setFocus()
            self._process_events()
        focus = QtWidgets.QApplication.focusWidget()
        self.assertFalse(
            focus is not None and self.widget.isAncestorOf(focus),
            "The keyboard was already inside the timeline before the click",
        )

        before = self.body.Tip
        self._click(self._marker_for("Sketch001"))

        focus = QtWidgets.QApplication.focusWidget()
        self.assertFalse(
            focus is not None and self.widget.isAncestorOf(focus),
            "A click must not leave the keyboard inside the timeline",
        )

        # And with the keyboard outside it, Home belongs to whoever else wants it.
        event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Home, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.instance().sendEvent(focus or self.window, event)
        self._settle()

        self.assertIs(self.body.Tip, before)

    def test_markers_and_step_buttons_can_be_reached_by_tab(self):
        marker = self._marker_for("Sketch001")
        self.assertIsNotNone(marker, "Expected a marker for Sketch001")
        self.assertEqual(marker.focusPolicy(), QtCore.Qt.TabFocus)

        buttons = self.widget.findChildren(QtWidgets.QToolButton, "TimelineStepButton")
        self.assertEqual(len(buttons), 2)
        for button in buttons:
            self.assertEqual(button.focusPolicy(), QtCore.Qt.TabFocus)

    def test_right_clicking_a_marker_leaves_the_selection_alone(self):
        """The menu belongs to the marker under the cursor, not to the selection."""

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.pad.Name)
        self._process_events()

        marker = self._marker_for("Sketch001")
        self.assertIsNotNone(marker, "Expected a marker for Sketch001")

        centre = marker.rect().center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, centre, marker.mapToGlobal(centre)
        )
        app = QtWidgets.QApplication.instance()
        app.sendEvent(marker, event)

        # The menu itself is opened through a queued connection and would spin its own
        # event loop, so it is dropped before anything gets a chance to run it.
        app.removePostedEvents(self.widget)

        selected = [obj.Name for obj in FreeCADGui.Selection.getSelection()]
        self.assertEqual(selected, [self.pad.Name])


class TestTimelineDock(unittest.TestCase):
    """The timeline is a strip along the bottom, as Fusion draws it, not a captioned dock.

    Its dock drew a title bar, so "Timeline" sat in the middle of the strip with the
    dock's own buttons at the far end. The dock still has to answer the View menu,
    since nothing else is left on screen to bring it back with.
    """

    def setUp(self):
        window = FreeCADGui.getMainWindow()
        if window is None:
            raise unittest.SkipTest("The timeline dock needs a main window")

        self.dock = None
        for dock in window.findChildren(QtWidgets.QDockWidget):
            widget = dock.widget()
            if widget is not None and widget.metaObject().className() == TIMELINE_CLASS:
                self.dock = dock
                break
        if self.dock is None:
            raise unittest.SkipTest("The timeline dock is not installed in this test environment")

        self.was_visible = self.dock.isVisible()
        self.dock.show()
        self._process_events()

    def tearDown(self):
        self.dock.setVisible(self.was_visible)
        self._process_events()

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def test_the_dock_draws_no_title_bar(self):
        bar = self.dock.titleBarWidget()
        self.assertIsNotNone(bar, "the dock draws Qt's own title bar")
        self.assertNotEqual(
            bar.metaObject().className(),
            "Gui::OverlayTitleBar",
            "the dock draws the overlay's title bar",
        )
        # Measured from the strip rather than the bar: an empty title widget has no size
        # hint, so Qt lays it out at a height of -1, which draws nothing.
        self.assertEqual(
            self.dock.widget().geometry().top(), 0, "the dock's title bar still takes up room"
        )

    def test_the_view_menu_still_hides_and_shows_it(self):
        action = self.dock.toggleViewAction()

        action.trigger()
        self._process_events()
        self.assertFalse(self.dock.isVisible(), "the View menu did not hide the timeline")

        action.trigger()
        self._process_events()
        self.assertTrue(self.dock.isVisible(), "the View menu did not bring the timeline back")
