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

"""GUI tests for the values shown on feature gizmos in the 3D view.

While a feature is edited, each drag handle carries a dimension with an editable box
on it, the way Fusion shows an extrude's distance: the box has the keyboard, Enter
finishes the feature, Tab moves between boxes and Esc cancels.

To run tests:
    FreeCAD -t TestGizmoValueLabels
"""

import importlib
import math
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

import TestExtrudeFlip as extrude

# FreeCAD's PySide shim does not re-export QtTest (see TestFusionShortcuts).
QtTest = None
# Only the Qt6 binding is tried. A machine can carry a half-installed PySide2
# beside it, whose import raises something other than ImportError, and anything
# raised here happens while the whole -t 0 run is still loading its tests, so it
# takes every suite down rather than this one. Whatever a candidate throws, it
# is not usable, and QtTest of None already skips the tests that need it.
for _binding in ("PySide6.QtTest", "PySide.QtTest"):
    try:
        QtTest = importlib.import_module(_binding)
        break
    except Exception:  # pragma: no cover - depends on which binding is installed
        continue

GIZMO_PARAMS = "User parameter:BaseApp/Preferences/Gui/Gizmos"
# Gui::GizmoValueLabel::nodeName and ::boxName.
LABEL_NODE = "GizmoValueLabel"
BOX_NAME = "GizmoValueBox"
# Gui::SoDatumLabel::Type.
ANGLE = 0
DISTANCE = 1
# ui->sidesMode, see TaskExtrudeParameters::translateSidesList.
TWO_SIDES = 1
SO_SWITCH_ALL = -3


class GizmoLabelCase(extrude.ExtrudePanelCase):
    """The 10 mm Pad panel of TestExtrudeFlip, with ways to find and drive the value boxes."""

    ARROW_BASE = extrude.TestExtrudeDrag.ARROW_BASE
    ARROW_TIP = extrude.TestExtrudeDrag.ARROW_TIP
    SO_SWITCH_NONE = extrude.TestExtrudeDrag.SO_SWITCH_NONE
    DragStep = extrude.TestExtrudeDrag.DragStep

    # Borrowed rather than inherited, so this suite does not run TestExtrudeDrag's tests again.
    _refresh_view_widgets = extrude.TestExtrudeDrag._refresh_view_widgets
    _settle_view = extrude.TestExtrudeDrag._settle_view
    _pixels = extrude.TestExtrudeDrag._pixels
    _qt_pos = extrude.TestExtrudeDrag._qt_pos
    _arrow_grip = extrude.TestExtrudeDrag._arrow_grip
    _switches_above_arrow = extrude.TestExtrudeDrag._switches_above_arrow
    _arrow_hidden = extrude.TestExtrudeDrag._arrow_hidden
    _mouse = extrude.TestExtrudeDrag._mouse
    _drag_arrow = extrude.TestExtrudeDrag._drag_arrow

    def setUp(self):
        super().setUp()
        main = FreeCADGui.getMainWindow()
        main.raise_()
        main.activateWindow()
        self._refresh_view_widgets()
        self._settle_view()

    # -- helpers ---------------------------------------------------------

    def _wait(self, condition, timeout_ms=3000):
        deadline = time.monotonic() + timeout_ms / 1000.0
        while not condition():
            if time.monotonic() >= deadline:
                return False
            self._process_events(20)
        return True

    def _boxes(self):
        """The value boxes on screen, whatever they hold."""

        main = FreeCADGui.getMainWindow()
        return [
            box
            for box in main.findChildren(QtWidgets.QAbstractSpinBox, BOX_NAME)
            if box.isVisible()
        ]

    def _distance_boxes(self):
        """The value boxes of distance arrows: an angle box shows a degree sign."""

        return [box for box in self._boxes() if "°" not in box.text()]

    def _wait_for_distance_boxes(self, count):
        self._wait(lambda: len(self._distance_boxes()) == count)
        boxes = self._distance_boxes()
        self.assertEqual(
            len(boxes), count, f"expected {count} distance boxes in the view, saw {len(boxes)}"
        )
        return boxes

    def _wait_for_focus(self, box):
        self.assertTrue(self._wait(box.hasFocus), "the value box did not get the keyboard")

    def _labels(self, shown_only=True):
        """The gizmo value labels in the scene, by default only those not switched off."""

        from pivy import coin

        search = coin.SoSearchAction()
        search.setName(LABEL_NODE)
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        paths = search.getPaths()
        labels = []
        for index in range(paths.getLength()):
            path = paths[index]
            if shown_only and not self._path_is_on(path):
                continue
            labels.append(path.getTail())
        return labels

    def _distance_labels(self):
        return [label for label in self._labels() if label.datumtype.getValue() == DISTANCE]

    @staticmethod
    def _path_is_on(path):
        """No switch on the path hides the rest of it."""

        from pivy import coin

        for depth in range(path.getLength() - 1):
            node = path.getNode(depth)
            if node.isOfType(coin.SoSwitch.getClassTypeId()):
                which = coin.cast(node, "SoSwitch").whichChild.getValue()
                if which not in (SO_SWITCH_ALL, path.getIndex(depth + 1)):
                    return False
        return True

    def _box_centre_on_screen(self, box):
        """The box's centre in the viewport's Qt coordinates."""

        return self.viewport.mapFromGlobal(box.mapToGlobal(box.rect().center()))

    def _screen_point(self, point):
        pos = self._qt_pos(self._pixels(point))
        return QtCore.QPoint(round(pos.x()), round(pos.y()))

    def _press(self, widget, key, modifiers=QtCore.Qt.NoModifier):
        for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            QtWidgets.QApplication.sendEvent(widget, QtGui.QKeyEvent(kind, key, modifiers))
        self._process_events()

    def _type(self, widget, text):
        """Keystrokes handed straight to the widget; they skip the shortcut machinery."""

        for ch in text:
            key = QtCore.Qt.Key(ord(ch.upper()))
            for kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
                QtWidgets.QApplication.sendEvent(
                    widget, QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier, ch)
                )
        self._process_events()

    def _select_all(self, box):
        box.findChild(QtWidgets.QLineEdit).selectAll()

    def _value_labels_off(self):
        params = FreeCAD.ParamGet(GIZMO_PARAMS)
        had = "ShowValueLabels" in params.GetBools()
        old = params.GetBool("ShowValueLabels", True)
        params.SetBool("ShowValueLabels", False)

        def restore():
            if had:
                params.SetBool("ShowValueLabels", old)
            else:
                params.RemBool("ShowValueLabels")

        self.addCleanup(restore)

    def _reopen(self, name=None):
        """Close the panel and open it again, e.g. after a preference changed."""

        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(name or self.pad.Name)
        self._process_events(200)
        self._refresh_view_widgets()
        self.lengthEdit = self._find_widget("lengthEdit")
        self.operationMode = self._find_widget("operationMode")
        self.checkBoxReversed = self._find_widget("checkBoxReversed")


class TestGizmoValueLabels(GizmoLabelCase):
    """An extrude's length shown and edited in the 3D view."""

    def test_an_extrude_opens_with_its_length_in_a_focused_box(self):
        box = self._wait_for_distance_boxes(1)[0]
        self.assertAlmostEqual(box.property("rawValue"), 10.0)
        self._wait_for_focus(box)

    def test_the_dimension_runs_from_the_profile_to_the_arrow(self):
        labels = self._distance_labels()
        self.assertEqual(len(labels), 1)
        label = labels[0]
        self.assertEqual(label.pnts.getNum(), 2)
        self.assertAlmostEqual(label.pnts[1][0] - label.pnts[0][0], 10.0, places=4)

    def test_the_box_sits_halfway_along_the_dimension(self):
        box = self._wait_for_distance_boxes(1)[0]
        middle = self._screen_point((self.ARROW_BASE + self.ARROW_TIP) * 0.5)
        centre = self._box_centre_on_screen(box)
        self.assertLessEqual(
            (centre - middle).manhattanLength(),
            12,
            f"box centred at {centre}, the dimension's middle is at {middle}",
        )

    def test_closing_the_panel_leaves_no_value_labels_behind(self):
        self.assertTrue(self._labels(shown_only=False), "no value labels to begin with")
        self._close_editing()
        self.assertEqual(self._labels(shown_only=False), [])
        self.assertEqual(self._boxes(), [])

    def test_no_boxes_when_values_in_the_view_are_turned_off(self):
        self._value_labels_off()
        self._reopen()
        self.assertEqual(self._boxes(), [])
        self.assertEqual(self._labels(shown_only=False), [])

    # -- typing ----------------------------------------------------------

    def _focused_length_box(self):
        box = self._wait_for_distance_boxes(1)[0]
        self._wait_for_focus(box)
        self._select_all(box)
        return box

    def test_typing_in_the_box_sets_the_length_as_you_go(self):
        box = self._focused_length_box()
        self._type(box, "45")
        self.assertAlmostEqual(self._length(), 45.0)
        self.assertAlmostEqual(self.lengthEdit.property("rawValue"), 45.0)

    def test_enter_finishes_the_extrude(self):
        box = self._focused_length_box()
        self._type(box, "45")
        self._press(box, QtCore.Qt.Key_Return)
        self.assertTrue(
            self._wait(lambda: FreeCADGui.Control.activeTaskDialog() is None),
            "Enter in the box did not finish the extrude",
        )
        self.assertAlmostEqual(self._length(), 45.0)

    def test_escape_cancels_the_extrude(self):
        # The panel's Cancel rolls back the document's open transaction.
        FreeCAD.setActiveTransaction("Edit Pad")
        box = self._focused_length_box()
        self._type(box, "25")
        self.assertAlmostEqual(self._length(), 25.0)
        self._press(box, QtCore.Qt.Key_Escape)
        self.assertTrue(
            self._wait(lambda: FreeCADGui.Control.activeTaskDialog() is None),
            "Esc in the box did not close the extrude",
        )
        self.assertAlmostEqual(self._length(), 10.0)

    def test_tab_moves_between_the_two_sides(self):
        self._find_widget("sidesMode").setCurrentIndex(TWO_SIDES)
        self._process_events(100)
        self._find_widget("lengthEdit2").setProperty("rawValue", 4.0)
        self._process_events(100)
        boxes = self._wait_for_distance_boxes(2)
        first = next(box for box in boxes if abs(box.property("rawValue") - 10.0) < 1e-6)
        second = next(box for box in boxes if abs(box.property("rawValue") - 4.0) < 1e-6)

        first.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(first)
        self._press(first, QtCore.Qt.Key_Tab)
        self._wait_for_focus(second)
        self._press(second, QtCore.Qt.Key_Backtab, QtCore.Qt.ShiftModifier)
        self._wait_for_focus(first)

    def test_letters_typed_in_the_box_reach_it_not_the_shortcuts(self):
        """Keys go in through the window, so the shortcut machinery sees them first."""

        if QtTest is None:
            self.skipTest("This PySide build has no QtTest")
        window = FreeCADGui.getMainWindow().windowHandle()
        if window is None:
            self.skipTest("The main window has no native handle in this environment")

        box = self._focused_length_box()
        for key in (
            QtCore.Qt.Key_1,
            QtCore.Qt.Key_2,
            QtCore.Qt.Key_Space,
            QtCore.Qt.Key_M,
            QtCore.Qt.Key_M,
        ):
            QtTest.QTest.keyClick(window, key, QtCore.Qt.NoModifier, 0)
        self._process_events(100)

        self.assertEqual(box.text().replace(" ", ""), "12mm")
        self.assertAlmostEqual(self._length(), 12.0)
        self.assertIsNotNone(FreeCADGui.Control.activeTaskDialog())

    # -- dragging --------------------------------------------------------

    def test_after_a_drag_the_box_has_the_keyboard_and_the_new_length(self):
        self._drag_arrow([8.0, 6.0])
        box = self._wait_for_distance_boxes(1)[0]
        self.assertLess(self._length(), 10.0)
        self.assertAlmostEqual(box.property("rawValue"), self._length(), places=4)
        self._wait_for_focus(box)

    # -- special cases ---------------------------------------------------

    def test_a_symmetric_extrude_shows_its_full_length_on_a_half_length_line(self):
        self._find_widget("sidesMode").setCurrentIndex(extrude.SYMMETRIC)
        self._process_events(100)
        box = self._wait_for_distance_boxes(1)[0]
        self.assertAlmostEqual(box.property("rawValue"), 10.0)
        label = self._distance_labels()[0]
        self.assertAlmostEqual(label.pnts[1][0] - label.pnts[0][0], 5.0, places=4)

    def test_a_zero_length_draws_no_line_and_keeps_the_box_at_the_profile(self):
        box = self._focused_length_box()
        self._type(box, "0")
        self._process_events(100)
        label = self._distance_labels()[0]
        # A degenerate pair, not no points at all: SoDatumLabel::GLRender warns "Too few
        # points to render distance label" on every redraw of a shown DISTANCE-type label
        # with fewer than 2 points, so a zero-length label still carries 2, coincident.
        self.assertEqual(label.pnts.getNum(), 2)
        self.assertAlmostEqual(label.pnts[1][0] - label.pnts[0][0], 0.0, places=4)
        base = self._screen_point(self.ARROW_BASE)
        self.assertLessEqual((self._box_centre_on_screen(box) - base).manhattanLength(), 12)

    def test_a_box_being_typed_in_survives_a_failed_recompute(self):
        switches = self._switches_above_arrow()
        box = self._focused_length_box()
        # A direction across the profile cannot be extruded along, so every recompute fails.
        self.pad.UseCustomVector = True
        self.pad.Direction = FreeCAD.Vector(1.0, 0.0, 0.0)
        self._type(box, "7")
        self.assertFalse(self.pad.isValid(), "the extrude was expected to fail")
        # Re-placing the gizmos on a failed extrude hides them.
        self.checkBoxReversed.setChecked(not self.checkBoxReversed.isChecked())
        self._process_events(100)
        self.assertTrue(self._arrow_hidden(switches), "the panel was expected to hide its gizmos")

        self.assertIn(box, self._boxes(), "the box vanished while it was being typed in")
        self.assertTrue(box.hasFocus())

    # -- angles ----------------------------------------------------------

    def _dragger_under(self, box, type_name):
        """Whether any part of a dragger of this type lies under the box on screen."""

        from pivy import coin

        manager = self.viewer.getSoRenderManager()
        ratio = self.viewport.devicePixelRatioF()
        corner = self.viewport.mapFromGlobal(box.mapToGlobal(QtCore.QPoint(0, 0)))
        for across in (0.1, 0.3, 0.5, 0.7, 0.9):
            for down in (0.2, 0.5, 0.8):
                x = (corner.x() + box.width() * across) * ratio
                y = (self.viewport.height() - (corner.y() + box.height() * down)) * ratio
                pick = coin.SoRayPickAction(manager.getViewportRegion())
                pick.setPoint(coin.SbVec2s(int(x), int(y)))
                pick.setRadius(2)
                pick.setPickAll(True)
                pick.apply(manager.getSceneGraph())
                picked = pick.getPickedPointList()
                for index in range(picked.getLength()):
                    path = picked[index].getPath()
                    for depth in range(path.getLength()):
                        if path.getNode(depth).getTypeId().getName().getString() == type_name:
                            return True
        return False

    def test_the_taper_box_leaves_its_handle_free(self):
        self._wait(lambda: len(self._boxes()) == 2)
        taper = next(box for box in self._boxes() if "°" in box.text())
        self.assertFalse(
            self._dragger_under(taper, "SoRotationDraggerContainer"),
            "the taper angle's box covers the handle that changes it",
        )

    def test_the_length_box_leaves_its_arrow_free(self):
        box = self._wait_for_distance_boxes(1)[0]
        self.assertFalse(
            self._dragger_under(box, "SoLinearDraggerContainer"),
            "the length box covers the arrow that changes it",
        )

    def test_an_extrude_shows_its_taper_angle_in_a_second_box(self):
        self._wait(lambda: len(self._boxes()) == 2)
        angle_boxes = [box for box in self._boxes() if "°" in box.text()]
        self.assertEqual(len(angle_boxes), 1, "expected one taper angle box")
        self.assertAlmostEqual(angle_boxes[0].property("rawValue"), 0.0)


class TestGizmoValueLabelsOnOtherFeatures(GizmoLabelCase):
    """Features other than the extrude, built on the same Pad."""

    def _edit(self, feature):
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(feature.Name)
        self._process_events(200)
        self._refresh_view_widgets()
        # Frame the new feature and its gizmos: a handle scaled for the Pad's view can sit
        # off screen, and its box then waits at the edge of the view.
        self._settle_view()

    def _dress_up(self, type_name, name):
        feature = self.doc.addObject(type_name, name)
        feature.Base = (self.pad, ["Edge1"])
        self.body.addObject(feature)
        self.doc.recompute()
        return feature

    def test_a_fillet_shows_one_box_for_its_two_arrows(self):
        fillet = self._dress_up("PartDesign::Fillet", "Fillet")
        fillet.Radius = 1.0
        self.doc.recompute()
        self._edit(fillet)
        box = self._wait_for_distance_boxes(1)[0]
        self.assertAlmostEqual(box.property("rawValue"), 1.0)
        self.assertEqual(len(self._distance_labels()), 1)

    def test_a_two_distance_chamfer_shows_a_box_per_distance(self):
        chamfer = self._dress_up("PartDesign::Chamfer", "Chamfer")
        self._edit(chamfer)
        self._wait_for_distance_boxes(1)
        # TaskChamferParameters: 0 equal distance, 1 two distances, 2 distance and angle.
        self._find_widget("chamferType").setCurrentIndex(1)
        self._process_events(100)
        self._wait_for_distance_boxes(2)

    def test_a_revolve_shows_its_angle_on_an_arc_at_the_handle(self):
        revolution = self.doc.addObject("PartDesign::Revolution", "Revolution")
        revolution.Profile = self.sketch
        revolution.ReferenceAxis = (self.sketch, ["V_Axis"])
        revolution.Angle = 90.0
        self.body.addObject(revolution)
        self.doc.recompute()
        self._edit(revolution)

        self._wait(lambda: len(self._boxes()) == 1)
        boxes = self._boxes()
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        self.assertAlmostEqual(box.property("rawValue"), 90.0)

        labels = self._labels()
        self.assertEqual(len(labels), 1)
        label = labels[0]
        self.assertEqual(label.datumtype.getValue(), ANGLE)
        radius = 2.0 * label.param1.getValue()
        self.assertGreater(radius, 0.0)

        # The arc turns about the sketch's vertical axis (x = 0) at the height of the
        # profile's centre, from the profile (+X) round 90 degrees, so its middle is 45
        # degrees round, towards +Z or -Z depending on the axis' sense.
        centre = FreeCAD.Vector(0.0, 3.0, 0.0)
        quarter = math.pi / 4.0
        candidates = [
            centre + FreeCAD.Vector(math.cos(quarter), 0.0, side * math.sin(quarter)) * radius
            for side in (1.0, -1.0)
        ]
        box_centre = self._box_centre_on_screen(box)
        misses = [
            (box_centre - self._screen_point(point)).manhattanLength() for point in candidates
        ]
        self.assertLessEqual(min(misses), 15, f"box at {box_centre} is not halfway round the arc")


class TestGizmoValueExpressions(GizmoLabelCase):
    """Formulas in the value boxes, the way Fusion takes one in its distance box (#757)."""

    _focused_length_box = TestGizmoValueLabels._focused_length_box

    def _add_width(self, width=7.0):
        """A user parameter, Width, in the document's parameters object."""

        self._close_editing()
        params = self.doc.addObject("App::VarSet", "Parameters")
        params.addProperty("App::PropertyDistance", "Width", "Parameters")
        params.Width = width
        self.doc.recompute()
        return params

    def _bind_length(self, formula):
        self.pad.setExpression("Length", formula)
        self.doc.recompute()

    def _expressions(self):
        return dict(self.pad.ExpressionEngine)

    def test_a_length_set_by_a_formula_keeps_its_box_and_shows_the_formula(self):
        self._add_width()
        self._bind_length("Parameters.Width * 2")
        self._reopen()
        box = self._wait_for_distance_boxes(1)[0]
        self.assertEqual(box.findChild(QtWidgets.QLineEdit).text(), "Width * 2")
        self.assertIn("14", box.toolTip(), "the box's tooltip does not give the formula's value")

    def test_a_formula_typed_in_the_box_drives_the_length(self):
        self._add_width()
        self._reopen()
        box = self._focused_length_box()
        self._type(box, "Width * 2")
        self._press(box, QtCore.Qt.Key_Return)
        self.assertTrue(
            self._wait(lambda: FreeCADGui.Control.activeTaskDialog() is None),
            "Enter did not take the formula and finish the extrude",
        )
        self.assertEqual(self._expressions().get("Length"), "Parameters.Width * 2")
        self.assertAlmostEqual(self._length(), 14.0)

    def test_tab_takes_a_formula_and_moves_on(self):
        self._add_width()
        self._reopen()
        box = self._focused_length_box()
        self._type(box, "Width + 1 mm")
        self._press(box, QtCore.Qt.Key_Tab)
        self.assertEqual(self._expressions().get("Length"), "Parameters.Width + 1 mm")
        self.assertIsNotNone(FreeCADGui.Control.activeTaskDialog())
        self.assertTrue(
            self._wait(lambda: box.findChild(QtWidgets.QLineEdit).text() == "Width + 1 mm"),
            "the box does not show the formula it took",
        )

    def test_a_formula_that_cannot_be_used_keeps_the_box_open(self):
        self._add_width()
        self._reopen()
        box = self._focused_length_box()
        self._type(box, "Nope * 2")
        self._press(box, QtCore.Qt.Key_Return)
        self._process_events(100)
        self.assertIsNotNone(
            FreeCADGui.Control.activeTaskDialog(), "a broken formula finished the extrude"
        )
        self.assertTrue(box.toolTip(), "the box does not say why the formula was refused")
        self.assertNotIn("Length", self._expressions())

    def test_a_number_typed_over_a_formula_replaces_it(self):
        self._add_width()
        self._bind_length("Parameters.Width * 2")
        self._reopen()
        box = self._focused_length_box()
        self._type(box, "30")
        self.assertAlmostEqual(self._length(), 30.0)
        self._press(box, QtCore.Qt.Key_Return)
        self.assertTrue(self._wait(lambda: FreeCADGui.Control.activeTaskDialog() is None))
        self.assertNotIn("Length", self._expressions())
        self.assertAlmostEqual(self._length(), 30.0)

    def test_dragging_an_arrow_that_a_formula_drives_replaces_the_formula(self):
        self._add_width()
        self._bind_length("Parameters.Width * 2")
        self._reopen()
        self._settle_view()
        # The arrow's tip sits at the formula's 14 mm, not the fixture's 10 mm, which
        # _drag_arrow's heights are measured from: these take it down by about 8 mm
        self.ARROW_TIP = FreeCAD.Vector(5.0, 3.0, 14.0)
        self._drag_arrow([6.0, 4.0])
        self.assertNotIn("Length", self._expressions())
        self.assertLess(self._length(), 14.0)
        box = self._wait_for_distance_boxes(1)[0]
        self.assertAlmostEqual(box.property("rawValue"), self._length(), places=4)
