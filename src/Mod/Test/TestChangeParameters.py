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

"""GUI tests for Change Parameters, the Fusion-style parameters dialog (#757).

The dialog lists the document's user parameters, kept in one variable set called
Parameters, and the model's own dimensions: named sketch dimensions, feature sizes and
values that formulas link. Every edit is one undo step and recomputes the model.

To run tests:
    FreeCAD -t TestChangeParameters
"""

import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

COMMAND = "Std_ChangeParameters"
DIALOG = "ChangeParametersDialog"
ADD_FORM = "AddParameterDialog"
# DlgChangeParameters::Column
NAME, UNIT, EXPRESSION, VALUE, COMMENT = range(5)
# The unit list of the add form: Length, Angle, No unit
LENGTH, ANGLE, NO_UNIT = range(3)
MAIN_WINDOW_PARAMS = "User parameter:BaseApp/Preferences/MainWindow"
RIBBON_BUTTON_NAMES = ("RibbonButton", "RibbonPrimaryButton")


def _value(quantity):
    return float(getattr(quantity, "Value", quantity))


class ChangeParametersCase(unittest.TestCase):
    """A 10 mm square sketch, its Side dimension named, padded 10 mm."""

    def setUp(self):
        self.dialog = None
        self._kept = []
        self.doc = FreeCAD.newDocument("TestChangeParameters")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)

        import Part
        import Sketcher

        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (self.doc.XY_Plane, [""])
        self.sketch.MapMode = "FlatFace"
        self.body.addObject(self.sketch)
        points = [FreeCAD.Vector(x, y, 0) for x, y in ((0, 0), (10, 0), (10, 10), (0, 10))]
        for i in range(4):
            self.sketch.addGeometry(Part.LineSegment(points[i], points[(i + 1) % 4]))
        for i in range(4):
            self.sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 0))
        self.sketch.addConstraint(Sketcher.Constraint("Horizontal", 2))
        self.sketch.addConstraint(Sketcher.Constraint("Vertical", 1))
        self.sketch.addConstraint(Sketcher.Constraint("Vertical", 3))
        side = self.sketch.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 10.0))
        self.sketch.renameConstraint(side, "Side")
        self.sketch.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10.0))

        self.pad = self.doc.addObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = 10.0
        self.body.addObject(self.pad)
        self.doc.recompute()
        self._process_events()

    def tearDown(self):
        if self.dialog is not None:
            self.dialog.reject()
            self._process_events()
        if FreeCADGui.Control.activeDialog() is not None:
            FreeCADGui.Control.closeDialog()
        if self.doc is not None and self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    # -- helpers ---------------------------------------------------------

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _wait(self, condition, timeout_ms=3000):
        deadline = time.monotonic() + timeout_ms / 1000.0
        while not condition():
            if time.monotonic() >= deadline:
                return False
            self._process_events(20)
        return True

    def _add_width(self, width=7.0):
        params = self.doc.addObject("App::VarSet", "Parameters")
        params.addProperty("App::PropertyDistance", "Width", "Parameters", "Plate width")
        params.Width = width
        self.doc.recompute()
        return params

    def _find_dialog(self):
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.objectName() == DIALOG and widget.isVisible():
                return widget
        return None

    def _open(self):
        FreeCADGui.runCommand(COMMAND)
        self.assertTrue(self._wait(lambda: self._find_dialog() is not None), "no dialog opened")
        self.dialog = self._find_dialog()
        self.tree = self.dialog.findChild(QtWidgets.QTreeWidget, "ParameterTree")
        self.status = self.dialog.findChild(QtWidgets.QLabel, "ParameterStatus")

    def _children(self, item):
        # The parents are kept: PySide deletes the children of a top-level item whose
        # wrapper it lets go of
        self._kept.append(item)
        return [item.child(i) for i in range(item.childCount())]

    def _user_items(self):
        return {item.text(NAME): item for item in self._children(self.tree.topLevelItem(0))}

    def _model_items(self, label):
        for item in self._children(self.tree.topLevelItem(1)):
            if item.text(NAME) == label:
                return {child.text(NAME): child for child in self._children(item)}
        return {}

    def _edit(self, item, column, text):
        item.setText(column, text)
        # The tree is rebuilt once control is back in the event loop
        self._process_events(100)

    def _add(self, name, unit=LENGTH, expression="", comment=""):
        """Fills in the add form and presses OK; returns what the form said if it stayed open."""

        said = []
        tries = [0]

        def fill():
            form = QtWidgets.QApplication.activeModalWidget()
            if form is None or form.objectName() != ADD_FORM:
                tries[0] += 1
                if tries[0] < 100:
                    QtCore.QTimer.singleShot(20, fill)
                elif form is not None:
                    form.reject()
                return
            try:
                form.findChild(QtWidgets.QLineEdit, "ParameterName").setText(name)
                form.findChild(QtWidgets.QComboBox, "ParameterUnit").setCurrentIndex(unit)
                form.findChild(QtWidgets.QLineEdit, "ParameterExpression").setText(expression)
                form.findChild(QtWidgets.QLineEdit, "ParameterComment").setText(comment)
                buttons = form.findChild(QtWidgets.QDialogButtonBox)
                buttons.button(QtWidgets.QDialogButtonBox.Ok).click()
            finally:
                if form.isVisible():
                    said.append(form.findChild(QtWidgets.QLabel, "AddParameterStatus").text())
                    form.reject()

        QtCore.QTimer.singleShot(0, fill)
        self.dialog.findChild(QtWidgets.QPushButton, "AddParameterButton").click()
        self._process_events()
        return said[0] if said else ""


class TestChangeParameters(ChangeParametersCase):
    def test_the_dialog_lists_user_parameters_and_the_model_dimensions(self):
        self._add_width()
        self.pad.setExpression("Length", "Parameters.Width * 2")
        self.doc.recompute()
        self._open()

        width = self._user_items()["Width"]
        self.assertEqual(width.text(UNIT), "mm")
        self.assertEqual(width.text(COMMENT), "Plate width")
        self.assertIn("7", width.text(VALUE))

        sketch = self._model_items(self.sketch.Label)
        self.assertIn("Side", sketch, "the named dimension is not listed")
        self.assertEqual(
            len(sketch), 1, f"only named dimensions belong in the list: {list(sketch)}"
        )
        pad = self._model_items(self.pad.Label)
        self.assertEqual(pad["Length"].text(EXPRESSION), "Width * 2")
        self.assertIn("14", pad["Length"].text(VALUE))
        self.assertNotIn("Length2", pad, "a size a one-sided pad does not use is listed")

    def test_adding_a_parameter_makes_one_parameters_object_as_one_undo_step(self):
        self._open()
        undo = self.doc.UndoCount
        self.assertEqual(self._add("Width", LENGTH, "12", "Plate width"), "")
        params = self.doc.getObject("Parameters")
        self.assertIsNotNone(params, "no parameters object was made")
        self.assertAlmostEqual(_value(params.Width), 12.0)
        self.assertEqual(self.doc.UndoCount, undo + 1)
        self.assertIn("Width", self._user_items())

        self.assertEqual(self._add("Turn", ANGLE, "Width / 1 mm * 5 deg"), "")
        self.assertEqual(len(self.doc.findObjects("App::VarSet")), 1)
        self.assertAlmostEqual(_value(params.Turn), 60.0)
        self.assertEqual(self.doc.UndoCount, undo + 2)

    def test_a_name_that_cannot_be_used_is_refused_in_the_add_form(self):
        self._open()
        self.assertTrue(self._add("2wide", LENGTH, "12"), "the form took a bad name")
        self.assertIsNone(self.doc.getObject("Parameters"), "a refused parameter left an object")
        self.assertTrue(self._add("Width", LENGTH, "12 deg"), "the form took an angle for a length")

    def test_editing_a_parameter_recomputes_the_model_as_one_undo_step(self):
        self._add_width()
        self.pad.setExpression("Length", "Parameters.Width * 2")
        self.doc.recompute()
        self._open()
        undo = self.doc.UndoCount

        self._edit(self._user_items()["Width"], EXPRESSION, "8 mm")
        self.assertEqual(self.status.text(), "")
        self.assertAlmostEqual(_value(self.pad.Length), 16.0)
        self.assertAlmostEqual(self.pad.Shape.Volume, 10 * 10 * 16, places=3)
        self.assertEqual(self.doc.UndoCount, undo + 1)
        self.assertIn("16", self._model_items(self.pad.Label)["Length"].text(VALUE))

        self.doc.undo()
        self.doc.recompute()
        self.assertAlmostEqual(_value(self.pad.Length), 14.0)

    def test_a_parameter_can_be_a_formula_of_another(self):
        params = self._add_width()
        self._open()
        self.assertEqual(self._add("Gap", LENGTH, "Width / 2"), "")
        self.assertEqual(dict(params.ExpressionEngine).get("Gap"), "Width / 2")
        self.assertAlmostEqual(_value(params.Gap), 3.5)
        self.assertEqual(self._user_items()["Gap"].text(EXPRESSION), "Width / 2")

    def test_renaming_a_parameter_rewrites_the_formulas_that_use_it(self):
        params = self._add_width()
        self.pad.setExpression("Length", "Parameters.Width * 2")
        self.doc.recompute()
        self._open()

        self._edit(self._user_items()["Width"], NAME, "Breadth")
        self.assertEqual(self.status.text(), "")
        self.assertIn("Breadth", params.PropertiesList)
        self.assertNotIn("Width", params.PropertiesList)
        self.assertEqual(dict(self.pad.ExpressionEngine).get("Length"), "Parameters.Breadth * 2")
        self.assertEqual(
            self._model_items(self.pad.Label)["Length"].text(EXPRESSION), "Breadth * 2"
        )

    def test_a_parameter_in_use_is_not_deleted(self):
        params = self._add_width()
        self.pad.setExpression("Length", "Parameters.Width * 2")
        self.doc.recompute()
        self._open()

        self.tree.setCurrentItem(self._user_items()["Width"])
        self.dialog.findChild(QtWidgets.QPushButton, "DeleteParameterButton").click()
        self._process_events()
        self.assertIn("Width", params.PropertiesList)
        self.assertIn(self.pad.Label, self.status.text())

    def test_an_unused_parameter_is_deleted(self):
        params = self._add_width()
        self._open()
        undo = self.doc.UndoCount

        delete = self.dialog.findChild(QtWidgets.QPushButton, "DeleteParameterButton")
        self.tree.setCurrentItem(self._model_items(self.pad.Label)["Length"])
        self.assertFalse(delete.isEnabled(), "a model dimension can be deleted")
        self.tree.setCurrentItem(self._user_items()["Width"])
        delete.click()
        self._process_events()
        self.assertNotIn("Width", params.PropertiesList)
        self.assertNotIn("Width", self._user_items())
        self.assertEqual(self.doc.UndoCount, undo + 1)

    def test_editing_a_named_dimension_changes_the_sketch(self):
        self._open()
        self._edit(self._model_items(self.sketch.Label)["Side"], EXPRESSION, "25 mm")
        self.assertEqual(self.status.text(), "")
        self.assertAlmostEqual(_value(self.sketch.getDatum("Side")), 25.0)
        self.assertAlmostEqual(self.pad.Shape.Volume, 25 * 10 * 10, places=3)

    def test_a_feature_size_takes_a_formula(self):
        self._add_width()
        self._open()
        self._edit(self._model_items(self.pad.Label)["Length"], EXPRESSION, "Width * 3")
        self.assertEqual(self.status.text(), "")
        self.assertEqual(dict(self.pad.ExpressionEngine).get("Length"), "Parameters.Width * 3")
        self.assertAlmostEqual(_value(self.pad.Length), 21.0)

    def test_a_value_that_cannot_be_used_is_refused_and_shown_again(self):
        self._open()
        self._edit(self._model_items(self.pad.Label)["Length"], EXPRESSION, "Nope * 2")
        self.assertNotEqual(self.status.text(), "", "the refusal was not explained")
        self.assertAlmostEqual(_value(self.pad.Length), 10.0)
        self.assertIn("10", self._model_items(self.pad.Label)["Length"].text(EXPRESSION))

    def test_the_command_is_off_while_a_feature_is_edited(self):
        command = FreeCADGui.Command.get(COMMAND)
        self.assertTrue(command.isActive())
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pad.Name)
        self._process_events(100)
        try:
            self.assertFalse(command.isActive())
        finally:
            FreeCADGui.getDocument(self.doc.Name).resetEdit()
            self._process_events()


class TestChangeParametersOnTheRibbon(unittest.TestCase):
    def test_the_solid_tab_has_change_parameters(self):
        if not FreeCAD.ParamGet(MAIN_WINDOW_PARAMS).GetBool("UseRibbon", True):
            raise unittest.SkipTest("The ribbon shell is switched off in this build")
        window = FreeCADGui.getMainWindow()
        tab_bar = window.findChild(QtWidgets.QTabBar, "RibbonTabBar")
        if tab_bar is None:
            raise unittest.SkipTest("The ribbon shell is not installed in this test environment")
        FreeCADGui.activateWorkbench("PartDesignWorkbench")
        index = next(
            (i for i in range(tab_bar.count()) if tab_bar.tabText(i).replace("&", "") == "SOLID"),
            -1,
        )
        self.assertGreaterEqual(index, 0, "Expected a SOLID tab on the ribbon")
        tab_bar.setCurrentIndex(index)

        def found():
            QtWidgets.QApplication.processEvents()
            return any(
                button.property("command") == COMMAND
                for button in window.findChildren(QtWidgets.QToolButton)
                if button.objectName() in RIBBON_BUTTON_NAMES
            )

        deadline = time.monotonic() + 3
        while not found() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(found(), "no Change Parameters button on the SOLID tab")
