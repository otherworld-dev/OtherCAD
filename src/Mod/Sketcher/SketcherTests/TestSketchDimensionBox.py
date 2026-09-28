# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI tests for typing a sketch dimension's value in the 3D view.

Placing a dimension, or editing one, opens a box on the dimension's own label instead of
the modal datum dialog: Enter applies the value, Esc keeps the dimension as it is, and
leaving the sketch applies what was typed.
"""

import FreeCAD
import Part
import Sketcher
import SketcherGui
from PySide import QtCore, QtGui, QtWidgets
from SketcherTests.GuiTestCase import FreeCADGui, SketcherGuiTestCase

SKETCHER_PARAMS = "User parameter:BaseApp/Preferences/Mod/Sketcher"
# SketcherGui::DimensionValueEditor::boxName
BOX_NAME = "SketchDimensionBox"


class TestSketchDimensionBox(SketcherGuiTestCase):
    """A 10 mm line in an open sketch, ready to be dimensioned."""

    def setUp(self):
        super().setUp()
        self._set_param("ShowDialogOnDistanceConstraint", True)
        self._set_param("EditDimensionsInView", True)
        # Constraint tools opened with nothing selected wait for picks only in this mode
        self._set_param("ContinuousConstraintMode", True)

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.doc = FreeCAD.newDocument("TestSketchDimensionBox")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(10, 0, 0)), False
        )
        self.doc.recompute()

        main = FreeCADGui.getMainWindow()
        main.show()
        main.raise_()
        main.activateWindow()
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name)
        self.flush_gui(200)

    # -- helpers ---------------------------------------------------------

    def _set_param(self, name, value):
        params = FreeCAD.ParamGet(SKETCHER_PARAMS)
        had = name in params.GetBools()
        old = params.GetBool(name, True)
        params.SetBool(name, value)

        def restore():
            if had:
                params.SetBool(name, old)
            else:
                params.RemBool(name)

        self.addCleanup(restore)

    def boxes(self):
        main = FreeCADGui.getMainWindow()
        return [
            box
            for box in main.findChildren(QtWidgets.QAbstractSpinBox, BOX_NAME)
            if box.isVisible()
        ]

    def wait_for_box(self):
        self.assertTrue(
            self.wait_until(lambda: len(self.boxes()) == 1, timeout_ms=2000),
            f"expected one dimension box, saw {len(self.boxes())}",
        )
        return self.boxes()[0]

    def wait_for_focus(self, box):
        self.assertTrue(
            self.wait_until(box.hasFocus, timeout_ms=2000),
            "the dimension box did not get the keyboard",
        )

    def assert_value_selected(self, box):
        """The whole value is selected, so typing replaces it."""
        edit = box.findChild(QtWidgets.QLineEdit)
        self.assertTrue(
            self.wait_until(
                lambda: edit.text() and edit.selectedText() == edit.text(), timeout_ms=1000
            ),
            f"the box's value was not selected (text {edit.text()!r}, selected {edit.selectedText()!r})",
        )

    def place_length_dimension(self):
        """Dimension the line through its command, the way a user would with it selected."""

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Edge1")
        FreeCADGui.runCommand("Sketcher_ConstrainDistance")
        self.flush_gui(150)
        self.assertEqual(len(self.sketch.Constraints), 1, "the distance was not placed")
        return 0

    def type_into(self, box, text):
        box.findChild(QtWidgets.QLineEdit).selectAll()
        for ch in text:
            self.key_click(box, QtCore.Qt.Key(ord(ch.upper())), ch)

    def value(self, index):
        return float(self.sketch.Constraints[index].Value)

    # -- placing ---------------------------------------------------------

    def test_placing_a_dimension_opens_a_focused_box_with_its_length(self):
        self.place_length_dimension()
        box = self.wait_for_box()
        self.assertAlmostEqual(box.property("rawValue"), 10.0)
        self.wait_for_focus(box)
        self.assert_value_selected(box)

    def test_enter_applies_the_typed_value(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.type_into(box, "25")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.assertAlmostEqual(self.value(index), 25.0)
        self.assertEqual(self.boxes(), [])

    def test_typing_straight_away_replaces_the_value(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.wait_for_focus(box)
        for ch in "25":
            self.key_click(box, QtCore.Qt.Key(ord(ch)), ch)
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.assertAlmostEqual(self.value(index), 25.0)

    def test_the_value_is_undone_before_the_dimension(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.type_into(box, "25")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)

        self.doc.undo()
        self.flush_gui(150)
        self.assertEqual(
            len(self.sketch.Constraints), 1, "undo took the dimension away with its value"
        )
        self.assertAlmostEqual(self.value(index), 10.0)

    def test_escape_keeps_the_dimension_as_measured(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.type_into(box, "25")
        self.key_click(box, QtCore.Qt.Key_Escape)
        self.flush_gui(150)
        self.assertEqual(len(self.sketch.Constraints), 1)
        self.assertAlmostEqual(self.value(index), 10.0)
        self.assertEqual(self.boxes(), [])
        self.assertIsNotNone(
            FreeCADGui.ActiveDocument.getInEdit(), "Esc in the box left the sketch"
        )

    def test_units_can_be_typed(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.type_into(box, "1 in")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.assertAlmostEqual(self.value(index), 25.4, places=6)

    # -- over-constraining -----------------------------------------------

    def _fix_the_length(self):
        """Dimension the line already, so a second length dimension is one too many."""
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
        self.doc.recompute()
        self.flush_gui(150)

    def _place_second_length(self):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Edge1")
        FreeCADGui.runCommand("Sketcher_ConstrainDistance")
        self.flush_gui(300)
        self.assertEqual(len(self.sketch.Constraints), 2, "the second distance was not placed")

    def test_an_over_constraining_dimension_is_added_as_driven(self):
        self._fix_the_length()
        self._place_second_length()

        self.assertTrue(self.sketch.Constraints[0].Driving)
        self.assertFalse(self.sketch.Constraints[1].Driving)
        self.assertEqual(self.sketch.RedundantConstraints, [])
        self.assertEqual(self.sketch.ConflictingConstraints, [])
        self.assertEqual(self.boxes(), [], "a driven dimension has no value to type")

    def test_the_sketch_stays_editable_after_an_over_constraining_dimension(self):
        self._fix_the_length()
        self._place_second_length()

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Constraint1")
        FreeCADGui.runCommand("Sketcher_ChangeDimensionConstraint")
        box = self.wait_for_box()
        self.type_into(box, "20")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.doc.recompute()
        self.flush_gui(150)

        self.assertAlmostEqual(self.value(0), 20.0)
        self.assertAlmostEqual(self.value(1), 20.0, msg="the driven dimension follows the geometry")

    def test_one_undo_takes_the_driven_dimension_away(self):
        self._fix_the_length()
        self._place_second_length()

        self.doc.undo()
        self.flush_gui(150)

        self.assertEqual(len(self.sketch.Constraints), 1)
        self.assertTrue(self.sketch.Constraints[0].Driving)

    # -- editing ---------------------------------------------------------

    def test_editing_an_existing_dimension_opens_the_box(self):
        index = self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 7.0))
        self.doc.recompute()
        self.flush_gui(150)

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name, f"Constraint{index + 1}")
        FreeCADGui.runCommand("Sketcher_ChangeDimensionConstraint")
        box = self.wait_for_box()
        self.assertAlmostEqual(box.property("rawValue"), 7.0)
        self.wait_for_focus(box)
        self.assert_value_selected(box)

        self.type_into(box, "9")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.assertAlmostEqual(self.value(index), 9.0)

    def test_reference_from_the_box_menu(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.wait_for_focus(box)

        chosen = []

        def choose():
            menu = QtWidgets.QApplication.activePopupWidget()
            if menu is None:
                return
            for action in menu.actions():
                if action.text() == "Reference":
                    chosen.append(action.text())
                    action.trigger()
                    break
            menu.close()

        QtCore.QTimer.singleShot(300, choose)
        edit = box.findChild(QtWidgets.QLineEdit)
        centre = edit.rect().center()
        event = QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse, centre, edit.mapToGlobal(centre)
        )
        QtWidgets.QApplication.sendEvent(edit, event)
        self.flush_gui(200)

        self.assertEqual(chosen, ["Reference"], "the box's menu had no Reference entry")
        self.assertFalse(self.sketch.Constraints[index].Driving)
        self.assertEqual(self.boxes(), [])

    def test_leaving_the_sketch_applies_what_was_typed(self):
        index = self.place_length_dimension()
        box = self.wait_for_box()
        self.type_into(box, "30")
        FreeCADGui.ActiveDocument.resetEdit()
        self.flush_gui(200)
        self.assertAlmostEqual(self.value(index), 30.0)
        self.assertEqual(self.boxes(), [])

    def test_with_the_setting_off_the_dialog_opens_instead(self):
        self._set_param("EditDimensionsInView", False)
        seen = []

        def dismiss():
            dialog = QtWidgets.QApplication.activeModalWidget()
            if dialog is not None:
                seen.append(dialog.windowTitle())
                dialog.reject()

        QtCore.QTimer.singleShot(400, dismiss)
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.sketch.Name, "Edge1")
        FreeCADGui.runCommand("Sketcher_ConstrainDistance")
        self.flush_gui(150)

        self.assertEqual(len(seen), 1, "the datum dialog did not open")
        self.assertEqual(self.boxes(), [])

    # -- editing with the Dimension tool open ----------------------------

    def viewport(self):
        return FreeCADGui.ActiveDocument.ActiveView.graphicsView().viewport()

    def add_distance(self, value):
        """A distance on the line with its value 5 mm off it, and a second line to pick."""

        index = self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, value))
        self.sketch.setLabelDistance(index, 5.0)
        self.sketch.addGeometry(
            Part.LineSegment(FreeCAD.Vector(20, 0, 0), FreeCAD.Vector(20, 10, 0)), False
        )
        self.doc.recompute()

        view = FreeCADGui.ActiveDocument.ActiveView
        view.viewTop()
        self.flush_gui(300)
        view.fitAll()
        self.flush_gui(300)
        return index

    def screen_point(self, point):
        view = FreeCADGui.ActiveDocument.ActiveView
        return self.viewport_to_qpoint(view, self.viewport(), view.getPointOnViewport(point))

    def label_hits(self, name):
        """Viewport points on the constraint's label, probing both sides of the line."""

        view = FreeCADGui.ActiveDocument.ActiveView
        for seed in (FreeCAD.Vector(5, 5, 0), FreeCAD.Vector(5, -5, 0)):
            centre = view.getPointOnViewport(seed)
            hits = []
            for dy in range(-48, 49, 4):
                for dx in range(-48, 49, 4):
                    point = (int(centre[0]) + dx, int(centre[1]) + dy)
                    info = SketcherGui.getActiveSketchPreselection(point)
                    if info and name in (info.get("SubElementNames") or []):
                        hits.append(point)
            if hits:
                return hits
        return []

    def label_point(self, index):
        """A point on the dimension's value, found by probing where its label can sit."""

        view = FreeCADGui.ActiveDocument.ActiveView
        name = f"Constraint{index + 1}"
        hits = []

        # The view can still be settling after the fit: probe until the value is there
        def found():
            hits[:] = self.label_hits(name)
            return bool(hits)

        self.assertTrue(
            self.wait_until(found, timeout_ms=3000, step_ms=100),
            f"{name}'s value was not found on screen",
        )

        # The hit nearest the middle of them all: on the value, not out on an arrow
        mid_x = sum(x for x, _ in hits) / len(hits)
        mid_y = sum(y for _, y in hits) / len(hits)
        best = min(hits, key=lambda p: (p[0] - mid_x) ** 2 + (p[1] - mid_y) ** 2)
        return self.viewport_to_qpoint(view, self.viewport(), best)

    def double_click(self, widget, pos):
        """The events Qt sends for a double-click: press, release, double-click, release."""

        self.move(widget, pos)
        presel = FreeCADGui.Selection.getPreselection()
        self.hovered = list(presel.SubElementNames) if presel.ObjectName else []
        left, none = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        for event_type, buttons in (
            (QtCore.QEvent.MouseButtonPress, left),
            (QtCore.QEvent.MouseButtonRelease, none),
            (QtCore.QEvent.MouseButtonDblClick, left),
            (QtCore.QEvent.MouseButtonRelease, none),
        ):
            self.send_mouse(widget, event_type, pos, left, buttons)
            self.pump(30)

    def open_tool(self, command):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.runCommand(command)
        self.flush_gui(150)

    def edit_by_double_click(self, command):
        """With the tool open, double-click the distance's value and type 9 into the box."""

        index = self.add_distance(7.0)
        label = self.label_point(index)
        self.open_tool(command)

        self.double_click(self.viewport(), label)
        self.assertIn(
            f"Constraint{index + 1}",
            self.hovered,
            f"{command} did not preselect the value under the cursor",
        )
        box = self.wait_for_box()
        self.assertAlmostEqual(box.property("rawValue"), 7.0)
        self.wait_for_focus(box)
        self.assert_value_selected(box)

        self.type_into(box, "9")
        self.key_click(box, QtCore.Qt.Key_Return)
        self.flush_gui(150)
        self.assertAlmostEqual(self.value(index), 9.0)
        self.assertEqual(self.boxes(), [])
        self.assertEqual(len(self.sketch.Constraints), 1, "double-clicking placed a constraint")

    def assert_the_tool_still_picks(self, command):
        """The tool is still open after the box closed: picking the other line constrains it."""

        # Found from the line itself: setting a sketch's only dimension scales the whole sketch,
        # and the view refits to it
        view = FreeCADGui.ActiveDocument.ActiveView
        line = self.sketch.Geometry[1]
        middle = (line.StartPoint + line.EndPoint) * 0.5

        def line_on_screen():
            info = SketcherGui.getActiveSketchPreselection(view.getPointOnViewport(middle))
            return bool(info) and "Edge2" in (info.get("SubElementNames") or [])

        self.assertTrue(
            self.wait_until(line_on_screen, timeout_ms=2000),
            "the other line never settled on screen",
        )
        other_line = self.screen_point(middle)
        self.move(self.viewport(), other_line)
        presel = FreeCADGui.Selection.getPreselection()
        hovered = list(presel.SubElementNames) if presel.ObjectName else []
        self.click(self.viewport(), other_line)
        self.assertTrue(
            self.wait_until(lambda: len(self.sketch.Constraints) == 2, timeout_ms=1000),
            f"{command} did not pick a line after the box closed (under the cursor: {hovered})",
        )

    def test_double_clicking_a_dimension_with_the_tool_open_edits_it(self):
        self.edit_by_double_click("Sketcher_Dimension")
        self.assert_the_tool_still_picks("Sketcher_Dimension")

    def test_double_clicking_a_dimension_in_the_distance_tool_edits_it(self):
        self.edit_by_double_click("Sketcher_ConstrainDistance")
        self.assert_the_tool_still_picks("Sketcher_ConstrainDistance")

    def test_double_clicking_a_dimension_in_the_parallel_tool_edits_it(self):
        # A tool that makes no dimension edits one all the same
        self.edit_by_double_click("Sketcher_ConstrainParallel")

    def test_one_click_on_a_dimension_with_the_tool_open_opens_nothing(self):
        index = self.add_distance(7.0)
        label = self.label_point(index)
        self.open_tool("Sketcher_Dimension")

        self.move(self.viewport(), label)
        self.click(self.viewport(), label)
        self.flush_gui(QtWidgets.QApplication.doubleClickInterval() + 200)
        self.assertEqual(self.boxes(), [])
        self.assertEqual(len(self.sketch.Constraints), 1)
        self.assertAlmostEqual(self.value(index), 7.0)
