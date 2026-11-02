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
another body and back. Every step is one undo entry, and so is a whole drag of
the playhead; undoing it puts the tip where it was.

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


class TimelineTestBase(unittest.TestCase):
    """A document with one body of four features, active and on the strip."""

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
        """With nothing selected the strip shows the active body, so it needs one."""

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

    def _markers_in_order(self):
        found = self.widget.findChildren(QtWidgets.QWidget, MARKER_NAME)
        return sorted((m for m in found if not m.isHidden()), key=lambda m: m.pos().x())

    def _choose_from_marker_menu(self, label, text):
        """Right-click a marker and pick an entry of its menu.

        The menu runs an event loop of its own, so the pick is made from a timer that
        keeps looking until it is open. Returns whether the entry was checked.
        """

        # A popup of an application in the background can close as soon as it opens
        self.window.raise_()
        self.window.activateWindow()
        # A menu that is still closing would take the right-click for itself
        deadline = time.monotonic() + 2.0
        while QtWidgets.QApplication.activePopupWidget() and time.monotonic() < deadline:
            self._process_events(50)

        # A label names a feature's marker; anything else is the widget itself
        marker = self._marker_for(label) if isinstance(label, str) else label
        self.assertIsNotNone(marker, f"Expected a marker for {label}")
        chosen = []
        offered = []
        timer = QtCore.QTimer()
        timer.setInterval(50)
        deadline = time.monotonic() + 5.0

        def pick():
            menu = QtWidgets.QApplication.activePopupWidget()
            if menu is not None:
                timer.stop()
                offered.extend(action.text() for action in menu.actions())
                for action in menu.actions():
                    if action.text() == text:
                        chosen.append(action.isChecked())
                        self.last_menu_entry_enabled = action.isEnabled()
                        if not action.isEnabled():
                            # Enter would leave the menu open, and its event loop with it
                            menu.close()
                            break
                        # Enter on the highlighted entry, as trigger() alone is not
                        # what exec() hands back
                        menu.setActiveAction(action)
                        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                            QtWidgets.QApplication.sendEvent(
                                menu,
                                QtGui.QKeyEvent(kind, QtCore.Qt.Key_Return, QtCore.Qt.NoModifier),
                            )
                        break
                else:
                    menu.close()
            elif time.monotonic() > deadline:
                timer.stop()

        timer.timeout.connect(pick)
        timer.start()
        centre = marker.rect().center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, centre, marker.mapToGlobal(centre)
        )
        QtWidgets.QApplication.instance().sendEvent(marker, event)
        self._process_events(600)
        timer.stop()
        if not offered and QtWidgets.QApplication.activeWindow() is None:
            self.skipTest(
                "This machine did not hand the application the foreground, "
                "so the menu closed as soon as it opened"
            )
        self.assertEqual(len(chosen), 1, f"the menu of {label} had no {text} entry: {offered}")
        return chosen[0]

    @staticmethod
    def _in_front_of(widget):
        """A point just inside the left edge of a marker, which a drop puts in front of it."""

        return widget.mapToGlobal(QtCore.QPoint(2, widget.height() // 2))

    @staticmethod
    def _after(widget):
        """A point just inside the right edge of a marker, which a drop puts after it."""

        return widget.mapToGlobal(QtCore.QPoint(widget.width() - 3, widget.height() // 2))

    @staticmethod
    def _send_mouse(widget, kind, globally, buttons):
        """A left button event at a global point, sent straight to the widget."""

        moving = kind == QtCore.QEvent.MouseMove
        QtWidgets.QApplication.instance().sendEvent(
            widget,
            QtGui.QMouseEvent(
                kind,
                QtCore.QPointF(widget.mapFromGlobal(globally)),
                QtCore.QPointF(globally),
                QtCore.Qt.NoButton if moving else QtCore.Qt.LeftButton,
                buttons,
                QtCore.Qt.NoModifier,
            ),
        )

    def _drag(self, source, target):
        """Press on source, move to the global point target and let go there.

        Every event goes to the source, the way the mouse grab of a real press sends
        them. What the drop indicator showed just before the release is handed back.
        """

        self.assertIsNotNone(source, "Expected a widget to drag")
        app = QtWidgets.QApplication.instance()
        start = source.mapToGlobal(source.rect().center())

        def send(kind, globally, buttons):
            self._send_mouse(source, kind, globally, buttons)

        send(QtCore.QEvent.MouseButtonPress, start, QtCore.Qt.LeftButton)
        steps = 4
        for step in range(1, steps + 1):
            point = QtCore.QPoint(
                start.x() + (target.x() - start.x()) * step // steps,
                start.y() + (target.y() - start.y()) * step // steps,
            )
            send(QtCore.QEvent.MouseMove, point, QtCore.Qt.LeftButton)
        app.processEvents()

        indicator = self.widget.findChild(QtWidgets.QWidget, "TimelineDropIndicator")
        shown = {
            "shown": indicator is not None and indicator.isVisible(),
            "valid": indicator is not None and bool(indicator.property("dropValid")),
        }
        send(QtCore.QEvent.MouseButtonRelease, target, QtCore.Qt.NoButton)
        self._settle()
        return shown

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


class TestTimeline(TimelineTestBase):
    """The timeline has to remember its rollback and undo it one step at a time."""

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

    def test_dragging_the_playhead_rolls_as_it_goes_in_one_undo_entry(self):
        """A scrub back and forth is one entry, as in Fusion, not one per marker passed."""

        playhead = self.widget.findChild(QtWidgets.QWidget, "TimelinePlayhead")
        self.assertIsNotNone(playhead)
        before = self.doc.UndoCount

        self._send_mouse(
            playhead,
            QtCore.QEvent.MouseButtonPress,
            playhead.mapToGlobal(playhead.rect().center()),
            QtCore.Qt.LeftButton,
        )
        self._send_mouse(
            playhead,
            QtCore.QEvent.MouseMove,
            self._in_front_of(self._marker_for("Sketch001")),
            QtCore.Qt.LeftButton,
        )
        self._process_events()
        self.assertIs(self.body.Tip, self.pad, "The model follows the playhead while dragged")
        self.assertFalse(self.sketch2.Visibility)

        self._send_mouse(
            playhead,
            QtCore.QEvent.MouseMove,
            self._in_front_of(self._marker_for("Pad")),
            QtCore.Qt.LeftButton,
        )
        self._process_events()
        self.assertIsNone(self.body.Tip)

        # And back again before letting go
        target = self._after(self._marker_for("Pad"))
        self._send_mouse(playhead, QtCore.QEvent.MouseMove, target, QtCore.Qt.LeftButton)
        self._send_mouse(playhead, QtCore.QEvent.MouseButtonRelease, target, QtCore.Qt.NoButton)
        self._settle()

        self.assertIs(self.body.Tip, self.pad)
        self.assertEqual(self.doc.UndoCount, before + 1)

        self.doc.undo()
        self._settle()
        self.assertIs(self.body.Tip, self.pad2)
        self.assertTrue(self.sketch2.Visibility)

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

    def test_a_feature_failing_on_a_recompute_shows_on_its_marker(self):
        """A feature that fails changes none of its own properties, so the marker has to
        hear about the recompute itself."""

        self.sketch.delGeometry(0)  # the profile is no longer closed
        self._settle()
        self.assertTrue(self.pad.isValid(), "nothing has been recomputed yet")

        self.doc.recompute()
        self._settle()

        self.assertFalse(self.pad.isValid())
        marker = self._marker_for("Pad")
        self.assertIn(self.pad.getStatusString(), marker.toolTip())
        # What the style sheet draws the red border from
        self.assertTrue(marker.property("timelineError"))

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

    def test_suppress_from_the_marker_menu(self):
        full = self.body.Shape.Volume

        was_checked = self._choose_from_marker_menu("Pad001", "Suppress")
        self._settle()

        self.assertFalse(was_checked)
        self.assertTrue(self.pad2.Suppressed)
        self.assertAlmostEqual(self.body.Shape.Volume, 10.0 * 6.0 * 10.0, places=3)
        self.assertIn("Suppressed", self._marker_for("Pad001").toolTip())

        was_checked = self._choose_from_marker_menu("Pad001", "Suppress")
        self._settle()

        self.assertTrue(was_checked)
        self.assertFalse(self.pad2.Suppressed)
        self.assertAlmostEqual(self.body.Shape.Volume, full, places=3)

    def test_suppress_is_one_undo_step(self):
        self.doc.UndoMode = 1
        self._choose_from_marker_menu("Pad001", "Suppress")
        self._settle()

        self.doc.undo()
        self.doc.recompute()
        self._settle()

        self.assertFalse(self.pad2.Suppressed)

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


class TestTimelineReorder(TimelineTestBase):
    """Dragging a marker along the strip moves its feature, unless that breaks the model.

    Sketch001 sits on the XY plane, so it can move in front of Pad; Pad001 is built
    from Sketch001 and Pad from Sketch, so neither pad can move in front of its sketch,
    nor either sketch past its pad.
    """

    def _order(self):
        names = {"Sketch", "Pad", "Sketch001", "Pad001"}
        return [obj.Name for obj in self.body.Group if obj.Name in names]

    def _drop_indicator(self):
        return self.widget.findChild(QtWidgets.QWidget, "TimelineDropIndicator")

    def _status_text(self):
        labels = self.window.statusBar().findChildren(QtWidgets.QLabel)
        return " ".join(label.text() for label in labels)

    def test_dragging_a_sketch_earlier_moves_it_in_one_undo_step(self):
        before = self.doc.UndoCount

        indicator = self._drag(
            self._marker_for("Sketch001"), self._in_front_of(self._marker_for("Pad"))
        )

        self.assertTrue(indicator["shown"], "A drag shows where the marker would land")
        self.assertTrue(indicator["valid"])
        self.assertFalse(self._drop_indicator().isVisible(), "The drop takes the indicator away")
        self.assertEqual(self._order(), ["Sketch", "Sketch001", "Pad", "Pad001"])
        self.assertEqual(self.doc.UndoCount, before + 1)
        self.assertIs(self.body.Tip, self.pad2)
        self.assertTrue(self._wait_for_markers(FEATURE_COUNT))
        self.assertEqual(
            [m.toolTip().split("\n")[0] for m in self._markers_in_order()],
            ["Sketch", "Sketch001", "Pad", "Pad001"],
        )

        self.doc.undo()
        self._settle()
        self.assertEqual(self._order(), ["Sketch", "Pad", "Sketch001", "Pad001"])

    def test_dragging_a_pad_to_the_end_takes_the_tip_with_it(self):
        volume = self.body.Shape.Volume

        self._drag(self._marker_for("Pad"), self._after(self._marker_for("Pad001")))

        self.assertEqual(self._order(), ["Sketch", "Sketch001", "Pad001", "Pad"])
        self.assertIs(self.body.Tip, self.pad)
        self.assertIs(self.pad.BaseFeature, self.pad2)
        self.assertIsNone(self.pad2.BaseFeature)
        self.assertAlmostEqual(self.body.Shape.Volume, volume, places=3)

    def test_a_feature_cannot_move_in_front_of_what_it_is_built_on(self):
        before = self.doc.UndoCount

        indicator = self._drag(
            self._marker_for("Pad001"), self._in_front_of(self._marker_for("Pad"))
        )

        self.assertTrue(indicator["shown"])
        self.assertFalse(indicator["valid"], "The indicator says the drop is refused")
        self.assertEqual(self._order(), ["Sketch", "Pad", "Sketch001", "Pad001"])
        self.assertEqual(self.doc.UndoCount, before)
        self.assertIn("Sketch001", self._status_text())

    def test_a_feature_cannot_move_past_what_is_built_on_it(self):
        before = self.doc.UndoCount

        self._drag(self._marker_for("Sketch"), self._after(self._marker_for("Pad001")))

        self.assertEqual(self._order(), ["Sketch", "Pad", "Sketch001", "Pad001"])
        self.assertEqual(self.doc.UndoCount, before)
        self.assertIn("Pad", self._status_text())

    def test_a_drag_in_place_changes_nothing(self):
        before = self.doc.UndoCount

        marker = self._marker_for("Sketch001")
        self._drag(marker, self._after(marker))

        self.assertEqual(self._order(), ["Sketch", "Pad", "Sketch001", "Pad001"])
        self.assertEqual(self.doc.UndoCount, before)


class TestTimelineGroups(TimelineTestBase):
    """Adjacent markers can be grouped into one that folds and unfolds, as in Fusion.

    Groups live on the body's view provider as key, name and member IDs, so they are
    saved with the document and undone like any other change.
    """

    def _group_markers(self):
        found = self.widget.findChildren(QtWidgets.QWidget, "TimelineGroupMarker")
        return [marker for marker in found if not marker.isHidden()]

    def _wait_for_group_markers(self, count, timeout_ms=3000):
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while len(self._group_markers()) != count and time.monotonic() < deadline:
            self._process_events(50)
        return self._group_markers()

    def _stored(self):
        """The stored groups as (name, member names) pairs."""

        groups = []
        for entry in self.body.ViewObject.TimelineGroups:
            fields = entry.split("\t")
            ids = {int(field) for field in fields[2:]}
            names = sorted(obj.Name for obj in self.doc.Objects if obj.ID in ids)
            groups.append((fields[1], names))
        return groups

    def _store(self, *members):
        """Group features directly, for tests about what a group does rather than its menu."""

        ids = "\t".join(str(obj.ID) for obj in members)
        self.body.ViewObject.TimelineGroups = ["1\tGroup 1\t" + ids]
        self._settle()

    def _order(self):
        names = {"Sketch", "Pad", "Sketch001", "Pad001"}
        return [obj.Name for obj in self.body.Group if obj.Name in names]

    def _double_click(self, widget):
        centre = widget.rect().center()
        QtWidgets.QApplication.instance().sendEvent(
            widget,
            QtGui.QMouseEvent(
                QtCore.QEvent.MouseButtonDblClick,
                QtCore.QPointF(centre),
                QtCore.QPointF(widget.mapToGlobal(centre)),
                QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
            ),
        )
        self._settle()

    def test_grouping_adjacent_markers_folds_them_into_one_undo_step(self):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch2.Name)
        FreeCADGui.Selection.addSelection(self.doc.Name, self.pad2.Name)
        self._process_events()
        before = self.doc.UndoCount

        self._choose_from_marker_menu("Pad001", "Group")
        self._settle()

        self.assertEqual(self._stored(), [("Group 1", ["Pad001", "Sketch001"])])
        self.assertEqual(self.doc.UndoCount, before + 1)
        self.assertEqual(len(self._wait_for_group_markers(1)), 1)
        self.assertIsNone(self._marker_for("Sketch001"), "A folded group hides its members")
        self.assertIsNone(self._marker_for("Pad001"))
        self.assertTrue(self._wait_for_markers(2))

        self.doc.undo()
        self._settle()
        self.assertEqual(self._stored(), [])
        self.assertEqual(len(self._wait_for_group_markers(0)), 0)
        self.assertTrue(self._wait_for_markers(FEATURE_COUNT))

    def test_markers_that_are_not_side_by_side_cannot_be_grouped(self):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name)
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch2.Name)
        self._process_events()

        self._choose_from_marker_menu("Sketch001", "Group")
        self._settle()

        self.assertFalse(self.last_menu_entry_enabled)
        self.assertEqual(self._stored(), [])

    def test_groups_survive_a_save_and_a_reload(self):
        self._store(self.sketch2, self.pad2)
        self.assertEqual(len(self._wait_for_group_markers(1)), 1)

        self._reopen()
        self._activate_body()

        self.assertEqual(self._stored(), [("Group 1", ["Pad001", "Sketch001"])])
        self.assertEqual(len(self._wait_for_group_markers(1)), 1)
        self.assertIsNone(self._marker_for("Pad001"))

    def test_a_double_click_unfolds_and_folds_a_group(self):
        self._store(self.sketch2, self.pad2)
        group = self._wait_for_group_markers(1)[0]

        self._double_click(group)
        self.assertIsNotNone(self._marker_for("Sketch001"), "Unfolded, the members show")
        self.assertIsNotNone(self._marker_for("Pad001"))
        self.assertEqual(len(self._group_markers()), 1, "and the group heads them")

        self._double_click(self._group_markers()[0])
        self.assertIsNone(self._marker_for("Pad001"))

    def test_rename_and_ungroup_from_the_group_menu(self):
        self._store(self.sketch2, self.pad2)
        group = self._wait_for_group_markers(1)[0]

        def answer():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if isinstance(dialog, QtWidgets.QInputDialog):
                timer.stop()
                dialog.setTextValue("Holes")
                dialog.accept()

        timer = QtCore.QTimer()
        timer.setInterval(50)
        timer.timeout.connect(answer)
        timer.start()
        self._choose_from_marker_menu(group, "Rename Group")
        self._settle()
        timer.stop()

        self.assertEqual(self._stored(), [("Holes", ["Pad001", "Sketch001"])])
        self.assertIn("Holes", self._wait_for_group_markers(1)[0].toolTip())

        self._choose_from_marker_menu(self._group_markers()[0], "Ungroup")
        self._settle()

        self.assertEqual(self._stored(), [])
        self.assertTrue(self._wait_for_markers(FEATURE_COUNT))

    def test_a_deleted_member_drops_out_and_an_empty_group_goes(self):
        self._store(self.sketch2, self.pad2)
        self.assertEqual(len(self._wait_for_group_markers(1)), 1)

        self.body.removeObject(self.pad2)
        self.doc.removeObject("Pad001")
        self.doc.recompute()
        self._settle()

        groups = self._wait_for_group_markers(1)
        self.assertEqual(len(groups), 1)
        self.assertIn("1 feature", groups[0].toolTip())

        self.body.removeObject(self.sketch2)
        self.doc.removeObject("Sketch001")
        self.doc.recompute()
        self._settle()

        self.assertEqual(len(self._wait_for_group_markers(0)), 0)

    def test_a_folded_group_is_dragged_as_one(self):
        self._store(self.sketch2, self.pad2)
        group = self._wait_for_group_markers(1)[0]

        self._drag(group, self._in_front_of(self._marker_for("Pad")))

        self.assertEqual(self._order(), ["Sketch", "Sketch001", "Pad001", "Pad"])
        self.assertIs(self.body.Tip, self.pad)
        self.assertEqual(self._stored(), [("Group 1", ["Pad001", "Sketch001"])])

    def test_a_member_dragged_out_of_an_unfolded_group_leaves_it(self):
        self._store(self.sketch2, self.pad2)
        self._double_click(self._wait_for_group_markers(1)[0])

        self._drag(self._marker_for("Sketch001"), self._in_front_of(self._marker_for("Pad")))

        self.assertEqual(self._order(), ["Sketch", "Sketch001", "Pad", "Pad001"])
        self.assertEqual(self._stored(), [("Group 1", ["Pad001"])])

    def test_a_feature_dropped_inside_an_unfolded_group_joins_it(self):
        self._store(self.sketch, self.pad)
        self._double_click(self._wait_for_group_markers(1)[0])

        self._drag(self._marker_for("Sketch001"), self._in_front_of(self._marker_for("Pad")))

        self.assertEqual(self._order(), ["Sketch", "Sketch001", "Pad", "Pad001"])
        self.assertEqual(self._stored(), [("Group 1", ["Pad", "Sketch", "Sketch001"])])

    def test_stepping_back_skips_over_a_folded_group(self):
        self._store(self.sketch2, self.pad2)
        self.assertEqual(len(self._wait_for_group_markers(1)), 1)

        self._invoke("stepBack")

        self.assertIs(self.body.Tip, self.pad)
        self.assertFalse(self.sketch2.Visibility, "The whole group is rolled back")
        groups = self._wait_for_group_markers(1)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].property("timelineState"), "rolledBack")
        self.assertIsNone(self._marker_for("Pad001"), "and it stays folded")


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


class TestTimelineFollowsSelection(TimelineTestBase):
    """The strip shows the body the user last pointed at, active or not."""

    def setUp(self):
        super().setUp()
        doc = self.doc
        self.other = doc.addObject("PartDesign::Body", "Body001")
        doc.recompute()
        xy = [f for f in self.other.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
        self.other_sketch = self.other.newObject("Sketcher::SketchObject", "OtherSketch")
        self.other_sketch.AttachmentSupport = (xy, [""])
        self.other_sketch.MapMode = "FlatFace"
        self._draw_rectangle(self.other_sketch, 5.0, 5.0)
        doc.recompute()
        self.other_pad = self.other.newObject("PartDesign::Pad", "OtherPad")
        self.other_pad.Profile = self.other_sketch
        self.other_pad.Length = 3.0
        doc.recompute()
        self._activate_body()  # self.body is active
        self._settle()

    def _labels(self):
        return [
            m.toolTip().split("\n")[0]
            for m in self.widget.findChildren(QtWidgets.QWidget, MARKER_NAME)
            if not m.isHidden()
        ]

    def _inactive_label(self):
        return self.widget.findChild(QtWidgets.QLabel, "TimelineBodyLabel")

    def _select(self, obj):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, obj.Name)
        self._settle()

    def test_selecting_in_another_body_shows_its_history_without_activating_it(self):
        self._select(self.other_pad)
        self.assertEqual(self._labels(), ["OtherSketch", "OtherPad"])
        view = FreeCADGui.getDocument(self.doc.Name).ActiveView
        self.assertEqual(view.getActiveObject("pdbody").Name, self.body.Name)
        label = self._inactive_label()
        self.assertIsNotNone(label)
        # Hidden rather than visible, like the markers: the label is the strip's to show,
        # whether or not the dock itself is on screen
        self.assertFalse(label.isHidden())
        self.assertIn("Body001", label.text())

    def test_renaming_the_shown_body_renames_its_label(self):
        self._select(self.other_pad)
        self.other.Label = "Bracket"
        self._settle()
        self.assertIn("Bracket", self._inactive_label().text())

    def test_clearing_the_selection_keeps_the_body(self):
        self._select(self.other_pad)
        FreeCADGui.Selection.clearSelection()
        self._settle()
        self.assertEqual(self._labels(), ["OtherSketch", "OtherPad"])

    def test_a_selection_outside_any_body_does_not_switch(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        self._select(self.other_pad)
        self._select(box)
        self.assertEqual(self._labels(), ["OtherSketch", "OtherPad"])

    def test_activating_a_body_by_hand_wins_over_an_older_selection(self):
        self._select(self.other_pad)
        self._activate_body(self.body)
        self._activate_body(self.other)
        self._activate_body(self.body)
        self._settle()
        self.assertEqual(len(self._labels()), FEATURE_COUNT)
        self.assertTrue(self._inactive_label().isHidden())

    def test_while_editing_the_strip_stays_on_the_edited_body(self):
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.sketch.Name)
        self._settle()
        try:
            FreeCADGui.Selection.addSelection(self.doc.Name, self.other_pad.Name)
            self._settle()
            # Or the check below would pass whatever the strip did with a selection
            self.assertTrue(FreeCADGui.Selection.isSelected(self.other_pad))
            self.assertEqual(len(self._labels()), FEATURE_COUNT)
        finally:
            gui_doc.resetEdit()
            self._settle()

    def test_a_pick_during_an_edit_does_not_move_the_strip_afterwards(self):
        # Picking another body's face for a feature's "up to face" is a selection too. A
        # feature's panel, unlike the sketcher, selects nothing of its own on closing.
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.pad.Name)
        self._settle()
        try:
            self.assertIsNotNone(gui_doc.getInEdit())
            FreeCADGui.Selection.addSelection(self.doc.Name, self.other_pad.Name)
            self._settle()
            self.assertTrue(FreeCADGui.Selection.isSelected(self.other_pad))
        finally:
            if FreeCADGui.Control.activeDialog():
                FreeCADGui.Control.closeDialog()
            gui_doc.resetEdit()
            self._settle()
        self.assertEqual(len(self._labels()), FEATURE_COUNT)
        self.assertTrue(self._inactive_label().isHidden())

    def test_opening_an_edit_takes_the_strip_to_the_edited_body(self):
        self._select(self.other_pad)
        FreeCADGui.Selection.clearSelection()
        self.assertEqual(self._labels(), ["OtherSketch", "OtherPad"])
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.sketch.Name)
        self._settle()
        try:
            self.assertEqual(len(self._labels()), FEATURE_COUNT)
            self.assertTrue(self._inactive_label().isHidden())
        finally:
            gui_doc.resetEdit()
            self._settle()

    def test_closing_an_edit_leaves_the_strip_on_the_edited_body(self):
        # The edit is what was pointed at last, even though it was opened with no selection
        self._select(self.other_pad)
        FreeCADGui.Selection.clearSelection()
        self.assertEqual(self._labels(), ["OtherSketch", "OtherPad"])
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.pad.Name)
        self._settle()
        try:
            self.assertIsNotNone(gui_doc.getInEdit())
        finally:
            if FreeCADGui.Control.activeDialog():
                FreeCADGui.Control.closeDialog()
            gui_doc.resetEdit()
            self._settle()
        self.assertEqual(len(self._labels()), FEATURE_COUNT)
        self.assertTrue(self._inactive_label().isHidden())

    def test_edit_from_an_inactive_body_marker_activates_it_and_opens_the_feature(self):
        self._select(self.other_pad)
        marker = self._marker_for("OtherPad")
        self.assertIsNotNone(marker)
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        centre = marker.rect().center()
        try:
            QtWidgets.QApplication.instance().sendEvent(
                marker,
                QtGui.QMouseEvent(
                    QtCore.QEvent.MouseButtonDblClick,
                    QtCore.QPointF(centre),
                    QtCore.QPointF(marker.mapToGlobal(centre)),
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.LeftButton,
                    QtCore.Qt.NoModifier,
                ),
            )
            self._settle()
            view = gui_doc.ActiveView
            self.assertEqual(view.getActiveObject("pdbody").Name, self.other.Name)
            in_edit = gui_doc.getInEdit()
            self.assertIsNotNone(in_edit, "the marker opened no edit")
            self.assertEqual(in_edit.Object.Name, self.other_pad.Name)
        finally:
            if FreeCADGui.Control.activeDialog():
                FreeCADGui.Control.closeDialog()
            gui_doc.resetEdit()
            self._settle()

    def test_rolling_an_inactive_body_activates_it_in_one_undo_step(self):
        self._select(self.other_pad)
        self._invoke("stepBack")
        view = FreeCADGui.getDocument(self.doc.Name).ActiveView
        self.assertEqual(view.getActiveObject("pdbody").Name, self.other.Name)
        self.assertNotEqual(self.other.Tip, self.other_pad)
        self.doc.undo()
        self.doc.recompute()
        self._settle()
        self.assertEqual(self.other.Tip, self.other_pad)
        # Activating is not an edit of the document, so undo leaves the body active
        self.assertEqual(view.getActiveObject("pdbody").Name, self.other.Name)

    def test_deleting_the_shown_body_falls_back_to_the_active_one(self):
        self._select(self.other_pad)
        FreeCADGui.Selection.clearSelection()
        self.other.removeObjectsFromDocument()
        self.doc.removeObject(self.other.Name)
        self._settle()
        self.assertEqual(len(self._labels()), FEATURE_COUNT)


class TestTimelineReferenceWarnings(TimelineTestBase):
    """A feature that still builds, but only because the naming code had to find one of
    its edges again by where it lies, is drawn in yellow with what changed in its
    tooltip (#754). Fusion does the same and offers to reselect."""

    _choose_from_marker_menu = TestTimeline._choose_from_marker_menu

    def setUp(self):
        super().setUp()
        self.edge = None
        for index, edge in enumerate(self.pad2.Shape.Edges, start=1):
            a, b = (vertex.Point for vertex in edge.Vertexes)
            if abs(a.z - b.z) > 5 and abs(a.x - 10) < 1e-6 and abs(a.y - 6) < 1e-6:
                self.edge = f"Edge{index}"
        self.assertIsNotNone(self.edge, "the pad has no vertical edge at its far corner")
        self.fillet = self.body.newObject("PartDesign::Fillet", "Fillet")
        self.fillet.Base = (self.pad2, [self.edge])
        self.fillet.Radius = 1.0
        self.doc.recompute()
        if not self._wait_for_markers(FEATURE_COUNT + 1):
            self.skipTest("The fillet never reached the timeline strip")
        self.assertTrue(self.fillet.isValid())

    def tearDown(self):
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        gui_doc = (
            FreeCADGui.getDocument(self.doc.Name)
            if self.doc.Name in FreeCAD.listDocuments()
            else None
        )
        if gui_doc is not None and gui_doc.getInEdit():
            gui_doc.resetEdit()
        self._process_events()
        super().tearDown()

    def _redraw_the_first_profile(self):
        """Redrawn lines are new lines to the sketch, so every name the shape gave the
        fillet's edge is gone, while an edge in the same place is still there."""

        self.sketch.deleteAllGeometry()
        self._draw_rectangle(self.sketch, 10.0, 6.0)
        self.doc.recompute()
        self._settle()

    def test_a_rematched_edge_turns_the_marker_yellow(self):
        self._redraw_the_first_profile()

        self.assertTrue(self.fillet.isValid(), self.fillet.getStatusString())
        marker = self._marker_for("Fillet")
        self.assertIsNotNone(marker)
        # What the style sheet draws the yellow border from
        self.assertTrue(marker.property("timelineWarning"))
        self.assertFalse(marker.property("timelineError"))
        self.assertIn(f"{self.edge} of Pad001 was lost", marker.toolTip())
        self.assertIn("Edit Fillet", marker.toolTip())

    def test_a_plain_change_leaves_the_marker_alone(self):
        """An edge that keeps its name is no guess."""

        self.pad2.Length = 25.0
        self.doc.recompute()
        self._settle()

        self.assertTrue(self.fillet.isValid())
        self.assertFalse(self._marker_for("Fillet").property("timelineWarning"))

    def test_a_failure_wins_over_a_warning(self):
        self._redraw_the_first_profile()
        self.fillet.Radius = 50.0  # far too big for the edge
        self.doc.recompute()
        self._settle()

        self.assertFalse(self.fillet.isValid())
        marker = self._marker_for("Fillet")
        self.assertTrue(marker.property("timelineError"))
        self.assertFalse(marker.property("timelineWarning"))

    def test_editing_the_feature_clears_the_warning(self):
        """Opening the feature is where the user checks or reselects the edge, so once
        that edit is over there is nothing left to warn about."""

        self._redraw_the_first_profile()
        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.fillet.Name)
        self._settle()
        self.assertTrue(self._marker_for("Fillet").property("timelineWarning"))

        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        gui_doc.resetEdit()
        self._settle()

        self.assertFalse(self._marker_for("Fillet").property("timelineWarning"))

    def test_undoing_the_change_takes_the_warning_back(self):
        """Undo puts the link back on the name it had, so it no longer points at the
        edge it was moved to."""

        self.doc.openTransaction("Redraw")
        self._redraw_the_first_profile()
        self.doc.commitTransaction()
        self._settle()
        self.assertTrue(self._marker_for("Fillet").property("timelineWarning"))

        self.doc.undo()
        self._settle()

        self.assertTrue(self.fillet.isValid())
        self.assertFalse(self._marker_for("Fillet").property("timelineWarning"))

    def test_the_marker_menu_offers_to_reselect(self):
        self._redraw_the_first_profile()

        self._choose_from_marker_menu("Fillet", "Edit to Reselect")
        self._settle()

        in_edit = FreeCADGui.getDocument(self.doc.Name).getInEdit()
        self.assertIsNotNone(in_edit)
        self.assertEqual(in_edit.Object.Name, self.fillet.Name)

    def _tree_icon(self, label):
        for tree in self.window.findChildren(QtWidgets.QTreeWidget):
            flags = QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive
            for item in tree.findItems(label, flags, 0):
                return item.icon(0).pixmap(16, 16).toImage()
        return None

    def test_the_model_tree_badges_the_feature_too(self):
        before = self._tree_icon("Fillet")
        if before is None:
            self.skipTest("The model tree is not shown in this test environment")

        self._redraw_the_first_profile()
        self.assertNotEqual(self._tree_icon("Fillet"), before, "no warning badge in the tree")

        gui_doc = FreeCADGui.getDocument(self.doc.Name)
        gui_doc.setEdit(self.fillet.Name)
        self._settle()
        if FreeCADGui.Control.activeDialog():
            FreeCADGui.Control.closeDialog()
        gui_doc.resetEdit()
        self._settle()
        self.assertEqual(self._tree_icon("Fillet"), before, "the badge outlived the edit")
