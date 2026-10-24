# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD contributors
# SPDX-FileNotice: Part of the FreeCAD project.

"""GUI tests for the Linear and Polar Pattern tools.

The tools start sized to what they copy, pick features and directions by clicking
in the view, and drive distance, angle and count from handles and boxes in the view.

To run tests:
    FreeCAD -t TestPatternPanel
"""

import os
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

import TestExtrudeFlip as extrude
import TestGizmoValueLabels as gizmo_labels

# Gui::GizmoValueLabel::boxName and ::countBoxName.
BOX_NAME = "GizmoValueBox"
COUNT_BOX_NAME = "GizmoCountBox"
PAD_VOLUME = 10.0 * 6.0 * 10.0


class PatternPanelCase(unittest.TestCase):
    """A 10 x 6 x 10 mm Pad in the active Body, ready for a pattern command."""

    # Borrowed rather than inherited, so this suite runs none of their tests again.
    _process_events = extrude.ExtrudePanelCase._process_events
    _close_editing = extrude.ExtrudePanelCase._close_editing
    _draw_rectangle = staticmethod(extrude.ExtrudePanelCase._draw_rectangle)
    _find_widget = staticmethod(extrude.ExtrudePanelCase._find_widget)
    _refresh_view_widgets = extrude.TestExtrudeDrag._refresh_view_widgets
    _pixels = extrude.TestExtrudeDrag._pixels
    _qt_pos = extrude.TestExtrudeDrag._qt_pos
    _mouse = extrude.TestExtrudeDrag._mouse
    _wait = gizmo_labels.GizmoLabelCase._wait
    _press = gizmo_labels.GizmoLabelCase._press
    _type = gizmo_labels.GizmoLabelCase._type
    _select_all = gizmo_labels.GizmoLabelCase._select_all
    _screen_point = gizmo_labels.GizmoLabelCase._screen_point
    _box_centre_on_screen = gizmo_labels.GizmoLabelCase._box_centre_on_screen
    _dragger_under = gizmo_labels.TestGizmoValueLabels._dragger_under
    SO_SWITCH_NONE = extrude.TestExtrudeDrag.SO_SWITCH_NONE
    _switches_above_arrow = extrude.TestExtrudeDrag._switches_above_arrow
    _arrow_hidden = extrude.TestExtrudeDrag._arrow_hidden
    _boxes = gizmo_labels.GizmoLabelCase._boxes
    _path_is_on = staticmethod(gizmo_labels.GizmoLabelCase._path_is_on)

    def setUp(self):
        try:
            main = FreeCADGui.getMainWindow()
        except (AttributeError, RuntimeError):
            main = None
        if main is None:
            raise unittest.SkipTest("The pattern tools need a main window")
        import PartDesignGui  # noqa: F401  registers the PartDesign commands

        self.doc = FreeCAD.newDocument("TestPatternPanel")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (self.doc.XY_Plane, [""])
        self.sketch.MapMode = "FlatFace"
        self.body.addObject(self.sketch)
        self._draw_rectangle(self.sketch, 10.0, 6.0)
        self.doc.recompute()
        self.pad = self.doc.addObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = 10.0
        self.body.addObject(self.pad)
        self.doc.recompute()
        self._process_events()
        self._refresh_view_widgets()
        self.view.setActiveObject("pdbody", self.body)
        main.raise_()
        main.activateWindow()
        self.pattern = None

    def tearDown(self):
        self._close_editing()
        FreeCADGui.Selection.clearSelection()
        if self.doc is not None and self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)

    # -- helpers ---------------------------------------------------------

    def _run(self, command, select_pad=True):
        """Run a pattern command the way the ribbon does and return the new pattern."""

        FreeCADGui.Selection.clearSelection()
        if select_pad:
            FreeCADGui.Selection.addSelection(self.doc.Name, self.pad.Name)
        FreeCADGui.runCommand(command, 0)
        self._process_events(300)
        self.pattern = self.body.Tip
        return self.pattern

    @staticmethod
    def _value(quantity):
        return float(getattr(quantity, "Value", quantity))

    def _click(self, widget):
        """A left click in the middle of a widget."""

        from PySide import QtGui

        centre = QtCore.QPointF(widget.rect().center())
        for kind, buttons in (
            (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
            (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
        ):
            event = QtGui.QMouseEvent(
                kind, centre, widget.mapToGlobal(centre.toPoint()),
                QtCore.Qt.LeftButton, buttons, QtCore.Qt.NoModifier,
            )
            QtWidgets.QApplication.sendEvent(widget, event)
        self._process_events(100)

    def _direction_widget(self, number):
        return self._find_widget(f"patternDirection{number}")

    def _direction_field(self, number):
        return self._direction_widget(number).findChild(QtWidgets.QFrame, "pickDirection")

    def _edge_along(self, axis):
        """The name of a straight Pad edge running along axis."""

        for index, edge in enumerate(self.pad.Shape.Edges):
            direction = edge.Vertexes[-1].Point - edge.Vertexes[0].Point
            if direction.Length > 1e-6 and abs(abs(direction.normalize().dot(axis)) - 1.0) < 1e-6:
                return f"Edge{index + 1}"
        self.fail(f"the Pad has no edge along {axis}")

    def _pick(self, subname, obj=None):
        """What a click on an element in the view does to the selection."""

        FreeCADGui.Selection.addSelection(self.doc.Name, (obj or self.pad).Name, subname)
        self._process_events(300)

    def _escape(self):
        """Press and release Escape in the 3D view, with a real gap between them
        (a physical key stays down for roughly 100 ms), not back-to-back."""

        QtWidgets.QApplication.sendEvent(
            self.viewport,
            QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier),
        )
        self._process_events(150)
        QtWidgets.QApplication.sendEvent(
            self.viewport,
            QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier),
        )
        self._process_events(300)

    @staticmethod
    def _tr(context, text):
        return QtCore.QCoreApplication.translate(context, text)

    def _search_paths(self, type_name, interest=None):
        """A configured, already-applied SoSearchAction over the 3D view's scene graph.

        The setup (setType/setInterest/setSearchingAll/apply) is the same in every
        caller; only the node type, and whether one hit is enough, ever differ.

        Kept alive on self rather than handed back as a bare local: getPaths()/
        getPath() return paths owned by the action itself, and a chained
        self._search_paths(...).getPaths() would otherwise drop the only reference
        to the action - and so, in pivy, the paths it returned - the moment this
        call returns, before the caller ever reads them."""

        from pivy import coin

        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName(type_name))
        search.setInterest(coin.SoSearchAction.ALL if interest is None else interest)
        search.setSearchingAll(True)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        self._last_search_action = search
        return search

    # -- the task panel's width ----------------------------------------------

    def _tasks_viewport(self, widget):
        """The part of the task panel in sight: the viewport of the scroll area the
        widget sits in, which never scrolls sideways (TaskPanel).

        Taken from the widget's own parents rather than from
        QAbstractScrollArea.viewport(): PySide ties the wrapper that hands out to the
        scroll area's own wrapper, so it reads as deleted once that one is let go,
        though the viewport itself lives on."""

        child, parent = widget, widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QtWidgets.QAbstractScrollArea):
                return child
            child, parent = parent, parent.parentWidget()
        self.fail("the widget is not in a scroll area")

    def _task_view(self, widget):
        """The Tasks panel (Gui::TaskView::TaskView) the widget sits in."""

        parent = widget.parentWidget()
        while parent is not None:
            if parent.metaObject().className() == "Gui::TaskView::TaskView":
                return parent
            parent = parent.parentWidget()
        self.fail("the widget is not in the Tasks panel")

    def _narrow_the_tasks_panel(self, widget):
        """Makes the Tasks panel the widget sits in as narrow as it goes, and lets it
        widen again after the test. The cap is put on the panel itself, so it holds
        whether its dock is in the main window or in an overlay (where the main window's
        resizeDocks() has no say)."""

        tasks = self._task_view(widget)
        narrowest = tasks.minimumWidth() or tasks.minimumSizeHint().width()
        self.addCleanup(self._cap_width, tasks, tasks.maximumWidth())
        self._cap_width(tasks, narrowest)

    def _cap_width(self, widget, width):
        widget.setMaximumWidth(width)
        self._process_events(300)

    @staticmethod
    def _save_grab(widget, name):
        """Keeps a picture of widget for a person to look at, when OTHERCAD_TEST_GRAB_DIR
        names a folder for it."""

        folder = os.environ.get("OTHERCAD_TEST_GRAB_DIR")
        if folder:
            widget.grab().save(os.path.join(folder, name))

    def _assert_inside_the_panel(self, widgets):
        """Each (name, widget) is shown and ends inside the part of the task panel in
        sight; anything past its right edge is cut off, as the panel never scrolls
        sideways."""

        for name, widget in widgets:
            self.assertIsNotNone(widget, f"there is no {name}")
            self.assertTrue(widget.isVisible(), f"{name} is hidden")
            viewport = self._tasks_viewport(widget)
            right = widget.mapTo(viewport, QtCore.QPoint(widget.width(), 0)).x()
            self.assertLessEqual(
                right,
                viewport.width(),
                f"{name} ends at {right} px, past the panel's edge at {viewport.width()} px",
            )


class TestStartValues(PatternPanelCase):
    """What the tools start with when a feature is selected."""

    def test_a_linear_pattern_starts_sized_to_its_feature(self):
        pattern = self._run("PartDesign_LinearPattern")
        self.assertEqual(pattern.Mode, "Spacing")
        # The Pad is 10 mm along the sketch's horizontal axis: 1.5 x 10.
        self.assertAlmostEqual(self._value(pattern.Offset), 15.0)
        self.assertEqual(pattern.Occurrences, 3)
        self.assertEqual(pattern.Direction[0], self.sketch)
        self.assertEqual(pattern.Direction[1], ["H_Axis"])

    def test_a_linear_pattern_leaves_its_second_direction_empty(self):
        pattern = self._run("PartDesign_LinearPattern")
        self.assertIsNone(pattern.Direction2)
        self.assertEqual(pattern.Occurrences2, 1)

    def test_the_copies_come_out_whole(self):
        pattern = self._run("PartDesign_LinearPattern")
        self.assertTrue(pattern.isValid(), pattern.getStatusString())
        self.assertAlmostEqual(pattern.Shape.Volume, 3 * PAD_VOLUME, places=3)

    def test_a_body_that_must_stay_one_solid_gets_touching_copies(self):
        self.body.AllowCompound = False
        self.doc.recompute()
        pattern = self._run("PartDesign_LinearPattern")
        self.assertAlmostEqual(self._value(pattern.Offset), 10.0)
        self.assertEqual(len(pattern.Shape.Solids), 1)

    def test_a_polar_pattern_starts_with_four_copies_round_a_full_circle(self):
        pattern = self._run("PartDesign_PolarPattern")
        self.assertAlmostEqual(self._value(pattern.Angle), 360.0)
        self.assertEqual(pattern.Occurrences, 4)
        self.assertEqual(pattern.Axis[0], self.sketch)
        self.assertEqual(pattern.Axis[1], ["N_Axis"])


class TestDirectionFields(PatternPanelCase):
    """Directions are picked in fields, not chosen from a drop-down with a special item."""

    def setUp(self):
        super().setUp()
        self._run("PartDesign_LinearPattern")

    def test_the_direction_field_names_the_sketch_axis(self):
        field = self._direction_field(1)
        self.assertEqual(
            field.property("summary"),
            self._tr("PartDesignGui::TaskTransformedParameters", "Horizontal sketch axis"),
        )

    def test_the_quick_picks_offer_axes_but_no_select_reference_item(self):
        menu = self._direction_field(1).findChild(QtWidgets.QToolButton, "pickFieldMenu").menu()
        texts = [action.text() for action in menu.actions()]
        self.assertIn(self._tr("PartDesignGui::TaskTransformedParameters", "Base Y-axis"), texts)
        self.assertNotIn(
            self._tr("PartDesignGui::TaskTransformedParameters", "Select reference…"), texts
        )

    def test_a_quick_pick_sets_the_direction(self):
        menu = self._direction_field(1).findChild(QtWidgets.QToolButton, "pickFieldMenu").menu()
        wanted = self._tr("PartDesignGui::TaskTransformedParameters", "Base Y-axis")
        next(action for action in menu.actions() if action.text() == wanted).trigger()
        self._process_events(300)
        self.assertEqual(getattr(self.pattern.Direction[0], "Role", ""), "Y_Axis")

    def test_the_reverse_button_turns_the_direction_round(self):
        self._click(self._direction_field(1).findChild(QtWidgets.QToolButton, "pickFieldReverse"))
        self.assertTrue(self.pattern.Reversed)

    def test_clicking_the_field_waits_for_an_edge(self):
        field = self._direction_field(1)
        self._click(field)
        self.assertTrue(field.property("active"))
        edge = self._edge_along(FreeCAD.Vector(0, 1, 0))
        self._pick(edge)
        self.assertEqual(self.pattern.Direction[0], self.pad)
        self.assertEqual(self.pattern.Direction[1], [edge])
        self.assertFalse(field.property("active"))

    def test_direction_2_starts_empty_and_says_how_to_add_one(self):
        field = self._direction_field(2)
        self.assertEqual(
            field.property("summary"),
            self._tr("PartDesignGui::TaskPatternParameters", "Click an edge to add"),
        )
        values = self._direction_widget(2).findChild(QtWidgets.QWidget, "valuesRow")
        self.assertFalse(values.isVisible())

    def test_picking_an_edge_turns_direction_2_on_sized_to_the_feature(self):
        self._click(self._direction_field(2))
        edge = self._edge_along(FreeCAD.Vector(0, 1, 0))
        self._pick(edge)
        self.assertEqual(self.pattern.Direction2[1], [edge])
        self.assertEqual(self.pattern.Occurrences2, 2)
        self.assertEqual(self.pattern.Mode2, "Spacing")
        # The Pad is 6 mm along Y: 1.5 x 6.
        self.assertAlmostEqual(self._value(self.pattern.Offset2), 9.0)
        values = self._direction_widget(2).findChild(QtWidgets.QWidget, "valuesRow")
        self.assertTrue(values.isVisible())

    def test_the_cross_turns_direction_2_off_again(self):
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        self._click(self._direction_field(2).findChild(QtWidgets.QToolButton, "pickFieldClear"))
        self.assertIsNone(self.pattern.Direction2)
        self.assertEqual(self.pattern.Occurrences2, 1)

    def test_a_quick_pick_turns_direction_2_on_sized_to_the_feature(self):
        """Direction 2 starts the same whichever way it is first filled."""

        menu = self._direction_field(2).findChild(QtWidgets.QToolButton, "pickFieldMenu").menu()
        wanted = self._tr("PartDesignGui::TaskTransformedParameters", "Base Y-axis")
        next(action for action in menu.actions() if action.text() == wanted).trigger()
        self._process_events(300)
        self.assertEqual(getattr(self.pattern.Direction2[0], "Role", ""), "Y_Axis")
        self.assertEqual(self.pattern.Occurrences2, 2)
        self.assertEqual(self.pattern.Mode2, "Spacing")
        # The Pad is 6 mm along Y: 1.5 x 6.
        self.assertAlmostEqual(self._value(self.pattern.Offset2), 9.0)
        values = self._direction_widget(2).findChild(QtWidgets.QWidget, "valuesRow")
        self.assertTrue(values.isVisible())

    def test_a_whole_body_pattern_sizes_direction_2_from_the_body(self):
        """Whole-body mode has nothing in Originals to size Direction 2 from
        (getOriginals() is empty once TransformMode is Whole shape), so starting
        Direction 2 must fall back to the base shape instead - the same fallback
        getStartPoint() already uses - rather than the 10 mm default for an
        empty list."""

        self._find_widget("optionWholeBody").setChecked(True)
        self._process_events(300)
        self.assertEqual(self.pattern.TransformMode, "Whole shape")

        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        self.assertEqual(self.pattern.Mode2, "Spacing")
        # The Pad is 6 mm along Y: 1.5 x 6.
        self.assertAlmostEqual(self._value(self.pattern.Offset2), 9.0)

    def test_a_finished_pick_hands_the_keyboard_back_to_a_value_box(self):
        """Direction 2's field takes the keyboard while its pick lasts; ending it must
        hand the keyboard back to a value box, the way the panel does when it first
        opens - not leave it on the now-inactive field. _pick() adds straight to the
        selection rather than clicking in the 3D view, so nothing else moves the
        keyboard off the field on its own; the fix must do it.

        Seen fail once, intermittently, in a full-suite sweep (passing again on an
        immediate rerun, in isolation and as part of this class) - no widget-level
        cause reproduced under repeated runs here. main.activateWindow() only runs
        once, in setUp(), and Qt cannot hand real keyboard focus to any child widget
        at all once the top-level window itself has lost OS activation (a stray
        Remote Desktop or focus blip, say) - reasserting it here, right before the
        wait, closes that one gap without loosening what is actually asserted (a
        real value box must still end up holding focus)."""

        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))

        main = FreeCADGui.getMainWindow()
        main.raise_()
        main.activateWindow()

        self.assertTrue(
            self._wait(lambda: any(box.hasFocus() for box in self._boxes()), timeout_ms=5000),
            "no value box took the keyboard back after the pick",
        )

    def test_a_pick_leaves_the_preview_showing_what_it_showed(self):
        """The Preview panel's "Show final result" decides whether the pattern or the
        feature before it is shown; a pick shows the originals only while it lasts."""

        before = (self.pattern.Visibility, self.pad.Visibility)
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        self.assertFalse(self._direction_field(2).property("active"))
        self.assertEqual((self.pattern.Visibility, self.pad.Visibility), before)

    def test_nothing_runs_off_the_narrowest_tasks_panel(self):
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        first, second = self._direction_widget(1), self._direction_widget(2)
        self._narrow_the_tasks_panel(first)
        self._save_grab(self._task_view(first), "pattern-panel-narrow-linear.png")
        field = self._direction_field(2)
        self._assert_inside_the_panel(
            [
                ("Direction 2's quick picks", field.findChild(QtWidgets.QToolButton, "pickFieldMenu")),
                ("Direction 2's reverse button", field.findChild(QtWidgets.QToolButton, "pickFieldReverse")),
                ("Direction 2's clear button", field.findChild(QtWidgets.QToolButton, "pickFieldClear")),
                ("Direction 1's count", first.findChild(QtWidgets.QSpinBox, "spinOccurrences")),
                ("Direction 2's count", second.findChild(QtWidgets.QSpinBox, "spinOccurrences")),
            ]
        )


class TestFeaturesField(PatternPanelCase):
    """What is copied is picked in a field too, and can never become nothing."""

    def _features_field(self):
        return self._find_widget("pickFeatures")

    def _add_cylinder(self):
        cylinder = self.doc.addObject("PartDesign::AdditiveCylinder", "Cylinder")
        self.body.addObject(cylinder)
        cylinder.Radius = 2.0
        cylinder.Height = 4.0
        cylinder.Placement.Base = FreeCAD.Vector(30.0, 3.0, 0.0)
        self.doc.recompute()
        return cylinder

    def test_the_field_names_the_features_being_copied(self):
        self._run("PartDesign_LinearPattern")
        self.assertEqual(self._features_field().property("summary"), self.pad.Label)

    def test_the_summary_follows_an_external_change_to_originals(self):
        """updateFeaturesField() used to run only from the panel's own paths, so an
        undo, a Python edit or a deleted feature left the summary showing stale
        labels. A Python edit to Originals is the cheapest of those three to drive
        here; all three go through the same property change, observed the same way."""

        cylinder = self._add_cylinder()
        self._run("PartDesign_LinearPattern")
        self.pattern.Originals = [self.pad, cylinder]
        self._process_events(300)
        self.assertEqual(
            self._features_field().property("summary"),
            f"{self.pad.Label}, {cylinder.Label}",
        )

    def test_the_old_feature_list_is_gone(self):
        self._run("PartDesign_LinearPattern")
        self.assertFalse(self._find_widget("listWidgetFeatures").isVisible())

    def test_clicks_add_and_remove_features(self):
        cylinder = self._add_cylinder()
        self._run("PartDesign_LinearPattern")
        field = self._features_field()
        self._click(field)
        self.assertTrue(field.property("active"))
        self._pick("Face1", cylinder)
        self.assertEqual(self.pattern.Originals, [self.pad, cylinder])
        self._pick("Face1", self.pad)
        self.assertEqual(self.pattern.Originals, [cylinder])
        self.assertTrue(field.property("active"), "the Features field stays on for more clicks")

    def test_the_last_feature_stays(self):
        self._run("PartDesign_LinearPattern")
        self._click(self._features_field())
        self._pick("Face1")
        self.assertEqual(self.pattern.Originals, [self.pad])

    def test_a_feature_of_another_body_is_not_taken(self):
        other_body = self.doc.addObject("PartDesign::Body", "OtherBody")
        box = self.doc.addObject("PartDesign::AdditiveBox", "Box")
        other_body.addObject(box)
        self.doc.recompute()
        self._run("PartDesign_LinearPattern")
        self._click(self._features_field())
        FreeCADGui.Selection.addSelection(self.doc.Name, box.Name, "Face1")
        self._process_events(300)
        self.assertEqual(self.pattern.Originals, [self.pad])

    def test_the_whole_body_option_copies_the_body(self):
        self._run("PartDesign_LinearPattern")
        self._find_widget("optionWholeBody").setChecked(True)
        self._process_events(300)
        self.assertEqual(self.pattern.TransformMode, "Whole shape")
        self.assertFalse(self._features_field().isEnabled())

    def test_the_options_toggle_shows_and_hides_the_box(self):
        """The Options box (holding "Copy the whole body" and "Recompute on change")
        starts collapsed and has no object name of its own to find directly; a child
        that does (optionUpdateView) is only ever visible when its parent box is, so
        checking it is the same as checking the box itself."""

        self._run("PartDesign_LinearPattern")
        check = self._find_widget("optionUpdateView")
        self.assertFalse(check.isVisible(), "the options box should start collapsed")

        self._click(self._find_widget("optionsToggle"))
        self.assertTrue(check.isVisible(), "the options box did not open")

        self._click(self._find_widget("optionsToggle"))
        self.assertFalse(check.isVisible(), "the options box did not close again")

    def test_unticking_recompute_on_change_stops_the_recompute(self):
        """optionUpdateView only gates TaskPatternParameters::blockUpdate, which
        onUpdateViewTimer() checks before calling recomputeFeature() - the panel
        widget itself still writes the property straight through regardless (its
        own, differently-named blockUpdate is just a recursion guard around
        updateUI(), unrelated to this checkbox). So unticking it must leave the
        property changed but the object's own shape stale (still "Touched", not
        recomputed) until it is ticked back on."""

        self._run("PartDesign_LinearPattern")
        self._click(self._find_widget("optionsToggle"))
        self._find_widget("optionUpdateView").setChecked(False)
        self.assertEqual(self.pattern.getStatusString(), "Valid")

        # A Gui::UIntSpinBox: stepUp(), not setValue(), see
        # TestLinearArrows.test_the_preview_follows_a_change_within_a_quarter_second.
        count = self._direction_widget(1).findChild(QtWidgets.QSpinBox, "spinOccurrences")
        count.stepUp()
        self.assertEqual(self.pattern.Occurrences, 4, "the property itself must still update")
        self._process_events(300)

        self.assertEqual(
            self.pattern.getStatusString(),
            "Touched",
            "the pattern was recomputed with Update view off",
        )
        self.assertAlmostEqual(self.pattern.Shape.Volume, 3 * PAD_VOLUME, places=3)

        self._find_widget("optionUpdateView").setChecked(True)
        self._process_events(300)
        self.assertEqual(self.pattern.getStatusString(), "Valid")
        self.assertAlmostEqual(self.pattern.Shape.Volume, 4 * PAD_VOLUME, places=3)

    def test_only_one_field_is_active_at_a_time(self):
        self._run("PartDesign_LinearPattern")
        self._click(self._features_field())
        self._click(self._direction_field(1))
        self.assertFalse(self._features_field().property("active"))
        self.assertTrue(self._direction_field(1).property("active"))

    def test_escape_turns_a_field_off_and_keeps_the_tool_open(self):
        self._run("PartDesign_LinearPattern")
        field = self._direction_field(1)
        self._click(field)
        self._escape()
        self.assertFalse(field.property("active"))
        # Control.activeDialog() reports whether a dialog is active, as a bool.
        self.assertTrue(FreeCADGui.Control.activeDialog())

    def test_escape_on_the_features_field_keeps_the_tool_open(self):
        self._run("PartDesign_LinearPattern")
        field = self._features_field()
        self._click(field)
        self._escape()
        self.assertFalse(field.property("active"))
        self.assertIsNotNone(FreeCADGui.Control.activeTaskDialog())

    def test_a_lost_escape_release_does_not_eat_the_next_one(self):
        """eatEscapeRelease stays set from a press until its matching release is seen,
        so the filter knows to eat that release too rather than let the view take it
        as Cancel. If the release never arrives - focus lost to another window
        mid-press, say - the flag used to stay stuck, and the very next Esc release
        anywhere in the app, unrelated or not, was silently eaten by a filter that
        should already be gone.

        A plain QWidget's own event() returns True for a recognised key event whether
        or not it was accepted, so QApplication.sendEvent()'s return value alone
        cannot tell "delivered" from "eaten" - confirmed empirically (a bare press and
        release sent to a widget with no filters installed at all still both come
        back True). An event filter installed on the probe itself is not fooled by
        that: application-level filters (ours among them) run before an object's own
        installed filters and before event() is ever called, so the spy only sees a
        release that got past every application-level filter first."""

        class ReleaseSpy(QtCore.QObject):
            def __init__(self):
                super().__init__()
                self.saw_release = False

            def eventFilter(self, watched, event):
                if event.type() == QtCore.QEvent.KeyRelease:
                    self.saw_release = True
                return False  # never consumes; only observes

        def key_event(kind):
            return QtGui.QKeyEvent(kind, QtCore.Qt.Key_Escape, QtCore.Qt.NoModifier)

        self._run("PartDesign_LinearPattern")
        probe = QtWidgets.QWidget()  # never shown; app filters still see events sent to it
        spy = ReleaseSpy()
        probe.installEventFilter(spy)

        self._click(self._direction_field(2))
        QtWidgets.QApplication.sendEvent(self.viewport, key_event(QtCore.QEvent.KeyPress))
        self._process_events(100)  # the pick ends; the matching release never arrives

        # The next, unrelated Esc press and release: sent to the probe, not the
        # viewport, so a correctly passed-through one cannot reach the view and close
        # the dialog mid-test.
        QtWidgets.QApplication.sendEvent(probe, key_event(QtCore.QEvent.KeyPress))
        QtWidgets.QApplication.sendEvent(probe, key_event(QtCore.QEvent.KeyRelease))
        self.assertTrue(spy.saw_release, "a later Esc release was eaten by a lost one's flag")


class TestNothingSelected(PatternPanelCase):
    """With nothing selected the tool asks for the feature to copy before it makes anything."""

    PICK_PANEL = "PartDesignGui__TaskPatternFeaturePick"

    def _panel_title(self):
        """The pattern panel widget's own title, once one is open. It carries no object
        name of its own, so this walks up from a known child (present for both Linear
        and Polar) by its Qt class name."""

        widget = self._direction_widget(1)
        while widget is not None:
            if widget.metaObject().className() == "PartDesignGui::TaskPatternParameters":
                return widget.windowTitle()
            widget = widget.parentWidget()
        self.fail("could not find the pattern panel")

    def test_the_linear_pickers_title_matches_the_panel_that_follows(self):
        """The picker shown with nothing selected used to say "Linear Pattern" while the
        panel that follows a pick is titled "Rectangular Pattern": title the picker from
        the same source as the panel, not a name of its own that can drift from it."""

        self._run("PartDesign_LinearPattern", select_pad=False)
        pick_title = self._find_widget(self.PICK_PANEL).windowTitle()
        self._pick("Face1")
        self.assertTrue(self._wait(lambda: self.body.Tip is not self.pad), "no pattern was made")
        self.assertEqual(self._panel_title(), pick_title)

    def test_the_polar_pickers_title_matches_the_panel_that_follows(self):
        """Polar said "Polar Pattern" in the picker and "Polar Pattern Parameters" in
        the panel that follows a pick; same fix and same check as the Linear case."""

        self._run("PartDesign_PolarPattern", select_pad=False)
        pick_title = self._find_widget(self.PICK_PANEL).windowTitle()
        self._pick("Face1")
        self.assertTrue(self._wait(lambda: self.body.Tip is not self.pad), "no pattern was made")
        self.assertEqual(self._panel_title(), pick_title)

    def test_the_tool_asks_for_a_feature_first(self):
        self._run("PartDesign_LinearPattern", select_pad=False)
        self.assertIs(self.body.Tip, self.pad, "a pattern was made before anything was picked")
        self.assertIsNotNone(self._find_widget(self.PICK_PANEL))

    def test_clicking_a_feature_starts_the_pattern_with_it(self):
        self._run("PartDesign_LinearPattern", select_pad=False)
        self._pick("Face1")
        self.assertTrue(self._wait(lambda: self.body.Tip is not self.pad), "no pattern was made")
        pattern = self.body.Tip
        self.assertEqual(pattern.TypeId, "PartDesign::LinearPattern")
        self.assertEqual(pattern.Originals, [self.pad])
        self.assertAlmostEqual(self._value(pattern.Offset), 15.0)
        self.assertTrue(self._wait(lambda: self._find_widget("pickFeatures") is not None))
        self.assertTrue(self._find_widget("pickFeatures").property("active"))

    def test_escape_before_picking_makes_nothing(self):
        self._run("PartDesign_PolarPattern", select_pad=False)
        self._escape()
        # Control.activeDialog() reports whether a dialog is active, as a bool,
        # not the dialog itself (that's activeTaskDialog()).
        self.assertTrue(self._wait(lambda: not FreeCADGui.Control.activeDialog()))
        self.assertIs(self.body.Tip, self.pad)
        self.assertEqual(
            [obj for obj in self.doc.Objects if obj.TypeId == "PartDesign::PolarPattern"], []
        )

    def test_the_cancel_button_makes_nothing(self):
        """The picker offers only a Cancel button (TaskDlgPatternFeaturePick::
        getStandardButtons() returns just QDialogButtonBox::Cancel). Reject the
        dialog the same way a click on it does - TaskDialogPy.reject() finds the
        panel's own QDialogButtonBox and calls click() on its Cancel button, not
        just the dialog's reject() method directly - and check the body ends up
        exactly as Esc already leaves it (test_escape_before_picking_makes_nothing,
        above): nothing created, nothing changed."""

        before = list(self.doc.Objects)
        self._run("PartDesign_LinearPattern", select_pad=False)

        FreeCADGui.Control.activeTaskDialog().reject()

        self.assertTrue(self._wait(lambda: not FreeCADGui.Control.activeDialog()))
        self.assertIs(self.body.Tip, self.pad)
        self.assertEqual(list(self.doc.Objects), before)
        self.assertEqual(
            [obj for obj in self.doc.Objects if obj.TypeId == "PartDesign::LinearPattern"], []
        )


class TestLinearArrows(PatternPanelCase):
    """Each direction of a linear pattern has an arrow to drag, with its value on it."""

    # The Pad's bounding box centre, where the arrows start; the first copy is 15 mm along X.
    BASE = FreeCAD.Vector(5.0, 3.0, 5.0)

    def setUp(self):
        super().setUp()
        self._run("PartDesign_LinearPattern")
        self._refresh_view_widgets()
        self.view.viewIsometric()
        # viewIsometric() only sets the camera's orientation (View3DPy.cpp), not its
        # type; the drag math in _drag_arrow_by below assumes an orthographic one
        # (screen position affine in world position, no perspective divide), so it
        # is made explicit here rather than assumed.
        self.view.setCameraType("Orthographic")
        self.view.fitAll()
        self._process_events(300)

    def _tip(self):
        return self.BASE + FreeCAD.Vector(self._value(self.pattern.Offset), 0.0, 0.0)

    def _distance_boxes(self):
        return [box for box in self._boxes() if "°" not in box.text()]

    def _arrow_grip(self):
        """A point on the arrow near its tip, found by asking the scene what is under
        it. The candidate points come from _pixels() (view.getPointOnScreen(), i.e.
        View3DInventorViewer::getPointOnViewport), the product's own screen
        projection - correct at any viewport shape."""

        from pivy import coin

        manager = self.viewer.getSoRenderManager()
        tip, base = self._pixels(self._tip()), self._pixels(self.BASE)
        for along in (0.0, 0.03, 0.06, 0.1, 0.15, 0.2):
            pixels = (tip[0] + (base[0] - tip[0]) * along, tip[1] + (base[1] - tip[1]) * along)
            pick = coin.SoRayPickAction(manager.getViewportRegion())
            pick.setPoint(coin.SbVec2s(int(pixels[0]), int(pixels[1])))
            pick.setRadius(6)
            pick.setPickAll(True)
            pick.apply(manager.getSceneGraph())
            picked = pick.getPickedPointList()
            for index in range(picked.getLength()):
                path = picked[index].getPath()
                for depth in range(path.getLength()):
                    if path.getNode(depth).getTypeId().getName().getString() == "SoLinearDraggerContainer":
                        return self._qt_pos(pixels)
        self.fail("the arrow is not under any of the points tried")

    def _drag_arrow_by(self, millimetres, hold_ms=0):
        """Press on the arrow and pull it along X by millimetres, keep the button down
        for hold_ms, then let go. Returns whether the arrow was hidden after each move
        (and after the hold), while the button was still down."""

        switches = self._switches_above_arrow()
        grip = self._arrow_grip()
        # start/end pin down the on-screen per-mm rate for the drag below, through
        # _pixels() - the product's own projection, correct at any viewport shape.
        start = self._qt_pos(self._pixels(self.BASE))
        end = self._qt_pos(self._pixels(self.BASE + FreeCAD.Vector(10.0, 0.0, 0.0)))
        per_mm = (end - start) / 10.0
        self._mouse(QtCore.QEvent.MouseMove, grip, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self._process_events()
        self._mouse(QtCore.QEvent.MouseButtonPress, grip, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._process_events(100)
        pos = grip
        hidden = []
        try:
            for step in range(1, 6):
                pos = grip + per_mm * (millimetres * step / 5.0)
                self._mouse(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
                self._process_events(60)
                hidden.append(self._arrow_hidden(switches))
            if hold_ms:
                self._process_events(hold_ms)
                hidden.append(self._arrow_hidden(switches))
        finally:
            self._mouse(QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
            self._process_events(300)
        return hidden

    def test_the_arrow_carries_the_spacing_in_a_box(self):
        self.assertTrue(self._wait(lambda: len(self._distance_boxes()) == 1))
        self.assertAlmostEqual(self._distance_boxes()[0].property("rawValue"), 15.0)

    def test_dragging_the_arrow_changes_the_spacing(self):
        self._drag_arrow_by(-5.0)
        self.assertLess(abs(self._value(self.pattern.Offset) - 10.0), 1.0)

    def test_dragging_the_arrow_to_its_base_keeps_it_under_the_pointer(self):
        """Pulled back past its base, the spacing reaches zero and the pattern breaks;
        the arrow stays under the pointer until it is let go, as on Extrude."""

        # Held long enough at the end for the preview to recompute under the drag
        hidden = self._drag_arrow_by(-16.0, hold_ms=400)
        self.assertFalse(any(hidden), f"the arrow was hidden while dragged: {hidden}")
        offset = self._value(self.pattern.Offset)
        self.assertTrue(0.0 <= offset <= 15.0, f"the spacing ended at {offset}")
        if not self.pattern.isValid():
            self.assertTrue(self._arrow_hidden(self._switches_above_arrow()))

    def test_clicking_the_arrow_turns_the_pattern_round(self):
        grip = self._arrow_grip()
        self._mouse(QtCore.QEvent.MouseButtonPress, grip, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._process_events(100)
        self._mouse(QtCore.QEvent.MouseButtonRelease, grip, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self._process_events(300)
        self.assertTrue(self.pattern.Reversed)

    def test_in_total_length_mode_the_box_holds_the_total_length(self):
        combo = self._direction_widget(1).findChild(QtWidgets.QComboBox, "comboMode")
        combo.setCurrentIndex(0)
        combo.activated.emit(0)
        self._process_events(300)
        self.assertTrue(self._wait(lambda: len(self._distance_boxes()) == 1))
        self.assertAlmostEqual(self._distance_boxes()[0].property("rawValue"), 30.0)

    def test_the_arrows_hide_while_a_field_is_being_picked_in(self):
        switches = self._switches_above_arrow()
        self._click(self._direction_field(1))
        self.assertTrue(self._arrow_hidden(switches))
        self.assertEqual(self._distance_boxes(), [])

    def test_direction_2_has_no_arrow_until_it_is_picked(self):
        self.assertEqual(len(self._distance_boxes()), 1)
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        self.assertTrue(self._wait(lambda: len(self._distance_boxes()) == 2))

    def test_the_gaps_after_the_first_keep_their_own_labels(self):
        """Only the first gap's label is replaced by the arrow's box."""

        paths = self._search_paths("SoDatumLabel").getPaths()
        gap_labels = [
            paths[index]
            for index in range(paths.getLength())
            if paths[index].getTail().getName() != "GizmoValueLabel" and self._path_is_on(paths[index])
        ]
        # Three copies make two gaps; the first is the arrow's.
        self.assertEqual(len(gap_labels), 1)

    def test_a_first_gap_with_its_own_override_keeps_its_label(self):
        """The arrow's box always shows the global Offset, never a per-gap value, so an
        unoverridden first gap can safely be left to it - but a first gap with its own
        override needs a label of its own, or that value is never shown anywhere."""

        self.pattern.Spacings = [20.0, -1.0]
        # Nudges the panel to refresh from what was just set from Python, the way any
        # panel-driven change normally would; Reversed's own value is incidental here.
        self._direction_field(1).reverseClicked.emit()
        self._process_events(300)

        paths = self._search_paths("SoDatumLabel").getPaths()
        gap_labels = [
            paths[index]
            for index in range(paths.getLength())
            if paths[index].getTail().getName() != "GizmoValueLabel" and self._path_is_on(paths[index])
        ]
        # Both gaps now show their own label: the first because it has an override, the
        # second because it always did (only the first can ever be the arrow's own).
        self.assertEqual(len(gap_labels), 2)

    def test_with_recompute_off_a_mode_switch_still_rebinds_the_arrow(self):
        """With "Recompute on change" off, onParameterWidgetParametersChanged() used to
        return before setGizmoPositions() ever ran, so a mode switch left the arrow
        bound to the box it no longer drives. Length is kept in sync with Occurrences
        and Offset synchronously (LinearPatternExtension::extensionOnChanged), not by
        a recompute, so the rebound box already holds the right value (2 x 15 mm =
        30 mm) - no recompute is needed to show it, only the same ~100 ms debounce
        the recomputing path already uses (onUpdateViewTimer() skips the recompute
        itself but still rebinds the gizmos when blocked). There is always exactly
        one distance box here, before and after, so the wait is on the rebound value
        rather than a box count that never changes."""

        self._find_widget("optionUpdateView").setChecked(False)
        combo = self._direction_widget(1).findChild(QtWidgets.QComboBox, "comboMode")
        combo.setCurrentIndex(0)
        combo.activated.emit(0)

        def rebound_to_total_length():
            boxes = self._distance_boxes()
            return len(boxes) == 1 and abs(boxes[0].property("rawValue") - 30.0) < 1e-6

        self.assertTrue(self._wait(rebound_to_total_length), "the arrow was not rebound")

    def test_the_preview_follows_a_change_within_a_quarter_second(self):
        count = self._direction_widget(1).findChild(QtWidgets.QSpinBox, "spinOccurrences")
        # One click on the up arrow. The box is a Gui::UIntSpinBox, which keeps its count
        # shifted by INT_MIN inside QSpinBox; Python only reaches QSpinBox::setValue(int),
        # so setValue(4) would clamp to the top and ask for 2147483647 copies.
        count.stepUp()
        self.assertEqual(self.pattern.Occurrences, 4)
        self._process_events(250)
        self.assertAlmostEqual(self.pattern.Shape.Volume, 4 * PAD_VOLUME, places=3)

    def test_the_arrow_is_grabbable_in_a_tall_view(self):
        """The grips are found through the product's own projection at any view shape -
        this is what _calibrated_pixels() used to work around."""

        window = FreeCADGui.getMainWindow()
        original = window.size()
        # tearDown() closes self.doc unconditionally, and unittest always runs
        # tearDown() before any addCleanup (doCleanups() only runs after it) - so an
        # addCleanup alone cannot make the restore below happen before the document
        # closes. Taking the close over ourselves through addCleanup instead, and
        # blanking self.doc so tearDown()'s own close is a no-op (its
        # "if self.doc is not None" guard, and _close_editing()'s AttributeError
        # catch, both already allow for that), lets the window-restore - registered
        # after, so addCleanup's LIFO order runs it first - resize the window while
        # the document and its camera still exist. TestViewportProjection.
        # _restore_window_size hit exactly this: restoring after the document had
        # already closed logged a camera-reference exception on every test.
        doc = self.doc
        self.doc = None

        def close_doc():
            if doc.Name in FreeCAD.listDocuments():
                FreeCAD.closeDocument(doc.Name)

        self.addCleanup(close_doc)
        self.addCleanup(lambda: (window.resize(original), self._process_events(300)))

        def viewport_shape():
            size = self.viewer.getSoRenderManager().getViewportRegion().getViewportSizePixels()
            return int(size[0]), int(size[1])

        window.resize(700, 1300)
        self._process_events(400)
        self.view.fitAll()
        self._process_events(300)
        width, height = viewport_shape()
        if height <= width:
            # A skip proves nothing here - this test exists to prove the grips are
            # found through a tall viewport. Try the MDI sub-window directly, the
            # way TestViewportProjection._shape_view does, before giving up.
            mdi_area = window.findChild(QtWidgets.QMdiArea)
            sub_window = mdi_area.activeSubWindow() if mdi_area is not None else None
            if sub_window is not None:
                sub_window.resize(700, 1300)
                self._process_events(400)
                self.view.fitAll()
                self._process_events(300)
                width, height = viewport_shape()
        self.assertGreater(
            height, width, "the window manager would not give a tall viewport"
        )

        self._arrow_grip()  # fails with "the arrow is not under any of the points tried"


class TestCountBoxes(PatternPanelCase):
    """The number of copies sits in a box just past each arrow."""

    BASE = TestLinearArrows.BASE
    _tip = TestLinearArrows._tip
    _distance_boxes = TestLinearArrows._distance_boxes
    _wait_for_focus = gizmo_labels.GizmoLabelCase._wait_for_focus
    _value_labels_off = gizmo_labels.GizmoLabelCase._value_labels_off
    _labels = gizmo_labels.GizmoLabelCase._labels

    def setUp(self):
        super().setUp()
        self._run("PartDesign_LinearPattern")
        self._refresh_view_widgets()
        self.view.viewIsometric()
        self.view.fitAll()
        self._process_events(300)

    def _count_boxes(self):
        main = FreeCADGui.getMainWindow()
        return [
            box
            for box in main.findChildren(QtWidgets.QAbstractSpinBox, COUNT_BOX_NAME)
            if box.isVisible()
        ]

    def _first_count_box(self):
        self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 1), "no count box")
        return self._count_boxes()[0]

    def test_the_arrow_has_a_box_with_the_number_of_copies(self):
        self.assertAlmostEqual(self._first_count_box().property("rawValue"), 3.0)

    def test_the_count_reads_as_a_whole_number(self):
        self.assertEqual(self._first_count_box().text().strip(), "3")

    def test_typing_in_the_count_box_sets_the_number_of_copies(self):
        box = self._first_count_box()
        box.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(box)
        self._select_all(box)
        self._type(box, "5")
        self._process_events(300)
        self.assertEqual(self.pattern.Occurrences, 5)

    def test_enter_in_the_count_box_finishes_the_pattern(self):
        box = self._first_count_box()
        box.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(box)
        self._select_all(box)
        self._type(box, "4")
        self._press(box, QtCore.Qt.Key_Return)
        self.assertTrue(self._wait(lambda: FreeCADGui.Control.activeTaskDialog() is None))
        self.assertEqual(self.pattern.Occurrences, 4)

    def test_the_count_box_leaves_the_arrow_free(self):
        self.assertFalse(self._dragger_under(self._first_count_box(), "SoLinearDraggerContainer"))

    def test_tab_runs_distance_then_count_for_each_direction(self):
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))
        self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 2))
        distances = self._distance_boxes()
        counts = self._count_boxes()
        by_value = lambda boxes, value: next(
            box for box in boxes if abs(box.property("rawValue") - value) < 1e-6
        )
        order = [
            by_value(distances, 15.0),  # Direction 1's spacing
            by_value(counts, 3.0),      # Direction 1's copies
            by_value(distances, 9.0),   # Direction 2's spacing
            by_value(counts, 2.0),      # Direction 2's copies
        ]
        order[0].setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(order[0])
        for current, following in zip(order, order[1:] + order[:1]):
            self._press(current, QtCore.Qt.Key_Tab)
            self._wait_for_focus(following)

    def test_no_count_boxes_when_values_in_the_view_are_off(self):
        self._value_labels_off()
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
        self._process_events(300)
        self.assertEqual(self._count_boxes(), [])

    def test_the_count_box_hides_for_an_expression(self):
        """The value box already hides when its own property carries a formula
        (Gizmo::isShownInView), and a value-box formula already hides the count box
        along with it (there is no arrow left to hang a count on). The count box must
        hide for its own formula too, independently of the value box's - this is the
        count-only case, with no formula on the value box at all. 2 + 1 keeps this a
        three-copy pattern, so nothing expensive is computed."""

        self.pattern.setExpression("Occurrences", "2 + 1")
        self.doc.recompute()
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
        self._process_events(300)
        self.assertEqual(self._count_boxes(), [])

    def test_the_times_mark_redraws_on_a_palette_change(self):
        """The "x" mark pixmap is drawn once, from the box's palette and device pixel
        ratio, at construction; QEvent::PaletteChange must redraw it, or a theme
        switch (or a move to a screen with a different scale, via the DPI/screen-
        change events the same handler covers) leaves a stale glyph in place."""

        box = self._first_count_box()
        edit = box.findChild(QtWidgets.QLineEdit)
        actions = edit.actions()
        self.assertEqual(len(actions), 1, "expected only the count box's own x mark action")
        before = actions[0].icon().cacheKey()

        QtWidgets.QApplication.sendEvent(box, QtCore.QEvent(QtCore.QEvent.PaletteChange))
        self._process_events(100)

        self.assertNotEqual(actions[0].icon().cacheKey(), before, "the x mark was not redrawn")

    def test_a_shown_labels_points_never_fall_short_for_its_type(self):
        """SoDatumLabel::GLRender warns "Too few points to render distance label" once
        a shown DISTANCE-type label has fewer than 2 points (SoDatumLabel.cpp). Coin's
        own default handler prints that straight past FreeCAD's Console (the bridge in
        Gui::Application.cpp's messageHandlerCoin is only installed when FC_DEBUG is
        set, i.e. never in a release build), so this checks the state that would cause
        it rather than the printed text. A count box sits at 0 mm of travel for as
        long as it is shown, so this state is permanent for it, not transient."""

        for label in self._labels():
            if label.datumtype.getValue() == gizmo_labels.DISTANCE:
                self.assertGreaterEqual(
                    label.pnts.getNum(),
                    2,
                    "a shown distance label with fewer than 2 points warns on every redraw",
                )

    def test_a_three_digit_count_fits_beside_the_times_mark(self):
        """QuantitySpinBox only widens for a leading action's icon when told to (see
        QuantitySpinBox::sizeHintForDigits's addIconSpace guard: it adds iconHeight,
        fontMetrics().height(), to the box only if addIconSpace was set) so a count
        box that skips that opt-in is sized for its digits alone, and the "x" mark
        (drawn in that same iconHeight square) crops them instead of sitting beside
        them. QLineEdit::textMargins() does not reflect the space Qt reserves for a
        leading action internally, so the box's own width is compared against the
        digits plus that reservation directly, the same way the C++ side does."""

        self.pattern.Occurrences = 100
        self.doc.recompute()
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
        self._process_events(300)
        box = self._first_count_box()
        self.assertEqual(box.text().strip(), "100")
        edit = box.findChild(QtWidgets.QLineEdit)
        fm = QtGui.QFontMetrics(edit.font())
        icon_reserved = fm.height()  # Gui::QuantitySpinBox's iconHeight
        needed = fm.horizontalAdvance(edit.text()) + icon_reserved
        self.assertGreaterEqual(box.width(), needed, "the x mark crops a 3-digit count")

    def test_the_count_boxes_stop_at_a_thousand_copies(self):
        """The panel caps each direction's copies, and the box in the view takes the same
        range; the property itself is left uncapped for old documents and scripts.
        Only the ranges are read here: a large count is never typed or set."""

        for number in (1, 2):
            count = self._direction_widget(number).findChild(QtWidgets.QSpinBox, "spinOccurrences")
            # A Gui::UIntSpinBox keeps its range shifted by INT_MIN inside QSpinBox (see
            # TestLinearArrows.test_the_preview_follows_a_change_within_a_quarter_second),
            # and has no unsigned "maximum" property of its own for Python to read
            self.assertEqual(count.maximum() + 2**31, 1000, f"Direction {number}'s count")
        self.assertAlmostEqual(self._first_count_box().property("maximum"), 1000.0)

    def test_an_old_documents_count_above_the_cap_still_shows(self):
        """A document saved before the panel capped copies at 1000 can carry a
        higher count. Set here the way a load from disk would leave it - the
        property holds 1200 but nothing is touched - rather than by simply
        assigning Occurrences and opening the panel: ViewProviderTransformed::
        setEdit calls recomputeFeature(false), which forces a real recompute
        whenever mustExecute() is true, no matter that RecomputesFrozen is set
        (Document::recomputeFeature's recursive path always passes force=true).
        A freshly touched Occurrences would make mustExecute() true and so
        recompute all 1200 copies; purgeTouched() after setting it keeps this
        test from ever doing that, matching a document that was already this
        way when it was last saved. RecomputesFrozen is set too, belt and
        braces, and restored after.

        Covers both directions, one at a time - not just Direction 1 (the gap the
        batch A review found was that Occurrences2 had no coverage of its own here
        at all). Direction 1 is dropped back down to 1, not just under the cap,
        before Direction 2 goes up: a LinearPattern's total copies is Occurrences x
        Occurrences2, so leaving Direction 1 at anything higher would still make the
        worst case (if the RecomputesFrozen/purgeTouched guard below were ever
        bypassed by a future change near this test) a multiple of the 1200 copies
        this test means to risk at most, not that figure itself.

        Also checks the in-view (gizmo) count box's own maximum widened, not just
        the panel box's: bindGizmoCount() (TaskPatternParameters.cpp) takes a
        one-time snapshot of the panel box's range at setupGizmos() time, when the
        panel first opens - a different path from the one
        test_the_in_view_count_range_follows_the_panel_box (above) exercises, which
        only reopens on an *already-open* panel's box widening further
        (refreshGizmoCountRanges()). An old document opened straight at 1200 goes
        through the one-time-snapshot path alone, so it needs its own check here.

        Extent mode (set on both directions below) is what let this drop from
        ~1.6s: in Spacing mode updateSpacingLabels() builds one on-view
        EditableDatumLabel per gap - 1199 of them at 1200 copies - which Extent mode
        does not, since there is no per-gap spacing to show. That label building is
        unrelated to what this test actually checks (the panel's and the in-view
        box's own count range), so switching mode first does not weaken it."""

        def unfreeze():
            # tearDown() (closeDocument) runs before an addCleanup callback, so by here
            # self.doc's wrapper may already be a dead reference - even reading .Name
            # off it raises, so the only safe check is to try the write and let a dead
            # document's ReferenceError pass.
            try:
                self.doc.RecomputesFrozen = False
            except ReferenceError:
                pass

        # Direction 2 needs a pick before it has an Occurrences2 box at all
        # (test_direction_2_starts_empty_and_says_how_to_add_one) - safe here, since
        # it starts at its own default 2 copies, well under the cap.
        self._click(self._direction_field(2))
        self._pick(self._edge_along(FreeCAD.Vector(0, 1, 0)))

        self.doc.RecomputesFrozen = True
        self.addCleanup(unfreeze)
        self._close_editing()
        self.pattern.Mode = "Extent"
        self.pattern.Mode2 = "Extent"

        def check_widened(number, prop_name):
            setattr(self.pattern, prop_name, 1200)
            self.pattern.purgeTouched()
            self.assertEqual(
                self.pattern.getStatusString(),
                "Valid",
                f"Direction {number} is touched: opening the panel would recompute 1200 copies",
            )

            FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
            self._process_events(300)

            box = self._direction_widget(number).findChild(QtWidgets.QSpinBox, "spinOccurrences")
            # Same INT_MIN shift as test_the_count_boxes_stop_at_a_thousand_copies above
            self.assertEqual(
                box.value() + 2**31, 1200, f"Direction {number}: the panel clamped an old document's count"
            )
            self.assertGreaterEqual(
                box.maximum() + 2**31, 1200, f"Direction {number}: the panel's maximum did not widen"
            )

            # The in-view count box's own range, bound once at setupGizmos() time
            # (bindGizmoCount()) - a document already above the cap when the panel
            # opens goes through that one-time snapshot, not the later-widening path
            # test_the_in_view_count_range_follows_the_panel_box (above) covers.
            # Both directions are in use here, so _first_count_box() (which waits
            # for exactly one) cannot be used; take whichever of the two boxes
            # widened furthest.
            self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 2), "no count boxes in the view")
            self.assertGreaterEqual(
                max(box.property("maximum") for box in self._count_boxes()),
                1200.0,
                f"Direction {number}: the in-view count box's range did not widen",
            )

            # Close with Cancel: resetEdit()/closeDialog() never call accept(), so
            # apply() never runs and nothing is written back or recomputed.
            self._close_editing()

        check_widened(1, "Occurrences")
        self.pattern.Occurrences = 1  # back down (to the true minimum, not just under
        # the cap) before Direction 2 goes up: a LinearPattern's total copies is
        # Occurrences x Occurrences2, so this keeps the worst case at 1200, not
        # some larger multiple of it, if the guard above were ever bypassed
        self.pattern.purgeTouched()
        check_widened(2, "Occurrences2")

    def test_the_in_view_count_range_follows_the_panel_box(self):
        """setupGizmos() bound the in-view count box's range from the panel box once, at
        panel-open time; the panel box can widen again later while the panel stays open
        (updateOccurrencesMaximum(), called from PatternParametersWidget::updateUI()),
        but nothing told the in-view box to widen with it. Re-ticking "Recompute on
        change" is the trigger used here because, unlike every other route to
        TaskPatternParameters::updateUI(), it writes no property of its own - Occurrences
        is set once, then purged, and never touched again, so the recompute the timer
        forces (TaskTransformedParameters::recomputeFeature() always passes force=true,
        see test_an_old_documents_count_above_the_cap_still_shows above) finds nothing to
        do. Document::recompute's force only bypasses the document-level SkipRecompute
        gate; whether an object's execute() runs is decided per object by
        mustRecompute() (Touch || mustExecute() > 0), which purgeTouched() clears."""

        def unfreeze():
            try:
                self.doc.RecomputesFrozen = False
            except ReferenceError:
                pass

        box = self._first_count_box()
        self.assertAlmostEqual(box.property("maximum"), 1000.0)

        self.doc.RecomputesFrozen = True
        self.addCleanup(unfreeze)
        self.pattern.Occurrences = 1200
        self.pattern.purgeTouched()
        self.assertEqual(
            self.pattern.getStatusString(),
            "Valid",
            "the pattern is touched: the update-view timer below would recompute 1200 copies",
        )

        check = self._find_widget("optionUpdateView")
        check.setChecked(False)
        check.setChecked(True)  # neither toggle writes a property; this just kicks the timer
        self._process_events(300)

        self.assertGreaterEqual(self._first_count_box().property("maximum"), 1200.0)

        # Close with Cancel: apply() never runs, so 1200 is never written back or recomputed.
        self._close_editing()


class TestPolarHandle(PatternPanelCase):
    """A polar pattern's angle is turned with a handle, and its copies counted beside it."""

    _count_boxes = TestCountBoxes._count_boxes
    _wait_for_focus = gizmo_labels.GizmoLabelCase._wait_for_focus

    # The handle turns about the point level with the Pad's bounding box centre
    # (TestLinearArrows.BASE) on the sketch's N_Axis (straight up through the origin);
    # RADIAL is the vector from there out to the start point, where the handle's arm
    # sits at 0 (and 360) degrees.
    PIVOT = FreeCAD.Vector(0.0, 0.0, 5.0)
    RADIAL = TestLinearArrows.BASE - PIVOT

    def setUp(self):
        super().setUp()
        self._run("PartDesign_PolarPattern")
        self._refresh_view_widgets()
        self.view.viewIsometric()
        # See TestLinearArrows.setUp: viewIsometric() sets orientation only, not
        # camera type; the drag math in _drag_handle_towards below needs an
        # orthographic one.
        self.view.setCameraType("Orthographic")
        self.view.fitAll()
        self._process_events(300)

    def _angle_boxes(self):
        return [box for box in self._boxes() if "°" in box.text()]

    def _handle_shown(self):
        paths = self._search_paths("SoRotationDraggerContainer").getPaths()
        return any(self._path_is_on(paths[index]) for index in range(paths.getLength()))

    def test_a_polar_pattern_has_a_rotation_handle(self):
        self.assertTrue(self._wait(self._handle_shown), "no rotation handle in the view")

    def test_the_handle_carries_the_total_angle_in_a_box(self):
        self.assertTrue(self._wait(lambda: len(self._angle_boxes()) == 1))
        self.assertAlmostEqual(self._angle_boxes()[0].property("rawValue"), 360.0)

    def test_the_handle_has_a_count_box(self):
        self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 1))
        self.assertAlmostEqual(self._count_boxes()[0].property("rawValue"), 4.0)

    def test_typing_an_angle_turns_the_pattern(self):
        self.assertTrue(self._wait(lambda: len(self._angle_boxes()) == 1))
        box = self._angle_boxes()[0]
        box.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(box)
        self._select_all(box)
        self._type(box, "90")
        self._process_events(300)
        self.assertAlmostEqual(self._value(self.pattern.Angle), 90.0)

    def test_tab_goes_from_the_angle_to_the_count(self):
        self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 1))
        angle, count = self._angle_boxes()[0], self._count_boxes()[0]
        angle.setFocus(QtCore.Qt.OtherFocusReason)
        self._wait_for_focus(angle)
        self._press(angle, QtCore.Qt.Key_Tab)
        self._wait_for_focus(count)

    def test_switching_to_angle_between_rebinds_the_handle(self):
        """The same rebind TestLinearArrows.
        test_with_recompute_off_a_mode_switch_still_rebinds_the_arrow covers for the
        arrows' own mode combo, but for the handle's (PatternParametersWidget::
        activeValueBox() switches from spinExtent to spinSpacing, and
        placePolarHandle's own handle->setProperty(...) follows), and with
        "Recompute on change" left on - the ordinary path, not the debounced-while-
        blocked one that test already covers."""

        self.assertTrue(self._wait(lambda: len(self._angle_boxes()) == 1))
        self.assertAlmostEqual(self._angle_boxes()[0].property("rawValue"), 360.0)

        combo = self._direction_widget(1).findChild(QtWidgets.QComboBox, "comboMode")
        combo.setCurrentIndex(1)
        combo.activated.emit(1)

        def rebound_to_spacing():
            boxes = self._angle_boxes()
            return len(boxes) == 1 and abs(
                boxes[0].property("rawValue") - self._value(self.pattern.Offset)
            ) < 1e-6

        self.assertTrue(self._wait(rebound_to_spacing), "the handle was not rebound to the spacing box")
        # Not a tautology: rawValue tracks whatever property is bound right now, and a
        # stale binding would just keep reading Angle's own 360 forever, which Offset
        # is not.
        self.assertNotAlmostEqual(self._value(self.pattern.Offset), 360.0)

    def test_the_handle_hides_while_the_axis_is_being_picked(self):
        self.assertTrue(self._wait(self._handle_shown))
        self._click(self._direction_field(1))
        self.assertFalse(self._handle_shown())

    def test_a_feature_centred_on_the_axis_hides_the_handle(self):
        """placePolarHandle hides the handle once the offset from the axis is
        (near) zero (radial.Length() < Precision::Confusion() in
        TaskPatternParameters.cpp) - there is no side left to put it on. A feature
        whose own AddSubShape sits centred right on the pattern's axis triggers
        exactly that; the default Pad every other test here copies is centred off
        to one side of it (RADIAL, above), which is why its handle shows at all.
        The default Axis for a feature with no sketch of its own to fall back to is
        the body's own Z origin axis (CmdPartDesignPolarPattern::activated) - the
        same line as the sketch's N_Axis this class's PIVOT sits on, for a fresh
        Pad-based body - so a cylinder left at the origin lands right on it.

        setUp's own pattern (copying the Pad) is undone first, and a fresh one made
        to copy the cylinder instead of adding the cylinder to the existing one's
        Originals: a feature added to the body after the pattern already exists
        sits downstream of it in the timeline, so it can never be one of that
        pattern's own Originals (adding it through the Features field is refused,
        as confirmed by running this the other way round first).

        setGizmoPositions()'s own top guard hides the handle for a pattern left in
        error too (see test_a_pattern_left_in_error_after_a_release_hides_the_container,
        below) - before placePolarHandle(), and its radial check, ever run. The
        getStatusString() assertion just before the real one rules that out: without
        it, a four-times-coincident on-axis pattern that happened to end up broken for
        an unrelated reason would still pass here with the radial branch never
        exercised at all."""

        self.doc.removeObject(self.pattern.Name)
        self.doc.recompute()

        cylinder = self.doc.addObject("PartDesign::AdditiveCylinder", "OnAxisCylinder")
        self.body.addObject(cylinder)
        cylinder.Radius = 1.0
        cylinder.Height = 4.0
        self.doc.recompute()

        self._run("PartDesign_PolarPattern", select_pad=False)
        self._pick("Face1", cylinder)
        self.assertTrue(self._wait(lambda: self.body.Tip is not self.pad), "no pattern was made")
        self.pattern = self.body.Tip
        self.assertEqual(self.pattern.TypeId, "PartDesign::PolarPattern")
        self.assertEqual(self.pattern.Originals, [cylinder])

        self.assertEqual(
            self.pattern.getStatusString(), "Valid", "the pattern broke for another reason"
        )
        self.assertFalse(self._handle_shown(), "the handle stayed shown for an on-axis feature")

    def test_a_pattern_left_in_error_after_a_release_hides_the_container(self):
        """setGizmoPositions()'s own top guard (feature->isError()) hides the whole
        container - not just the handle's own axis-radius check above, and not just
        the picking-mode guard test_the_handle_hides_while_the_axis_is_being_picked
        already covers - once a pattern is left broken. Checking the count box too
        is not a discriminator between this guard and a per-gizmo hide, for a polar
        pattern specifically: setupGizmos() binds the one count box to the same
        handle gizmo (bindGizmoCount(handle, ...)), so hiding the handle alone would
        already take the count box with it (Gizmo::isShownInView(), refreshValueLabels()).
        Its value here is narrower: a broken pattern leaves nothing at all in the
        view, not just an invisible handle with a stray count box left over."""

        self.assertTrue(self._wait(self._handle_shown), "no rotation handle in the view")
        self.assertTrue(self._wait(lambda: len(self._count_boxes()) == 1), "no count box")

        # PolarPatternExtension::calculateTransformations() throws "Pattern angle
        # can't be null" for Angle == 0 in Extent mode - see
        # test_dragging_the_handle_towards_zero_keeps_it_under_the_pointer, below.
        self.pattern.Angle = 0.0
        check = self._find_widget("optionUpdateView")
        check.setChecked(False)
        check.setChecked(True)  # neither toggle writes a property; this just kicks
        # the timer for a real recompute + gizmo refresh, the same cycle a drag's
        # own release already goes through (arrowDragFinished/handleDragFinished)
        self._process_events(300)

        self.assertFalse(self.pattern.isValid(), "the pattern did not end up broken")
        self.assertFalse(self._handle_shown(), "the handle stayed shown for a broken pattern")
        self.assertEqual(self._count_boxes(), [], "the count box stayed shown for a broken pattern")

    def test_nothing_runs_off_the_narrowest_tasks_panel(self):
        axis = self._direction_widget(1)
        self._narrow_the_tasks_panel(axis)
        self._save_grab(self._task_view(axis), "pattern-panel-narrow-polar.png")
        field = self._direction_field(1)
        self._assert_inside_the_panel(
            [
                ("the axis's quick picks", field.findChild(QtWidgets.QToolButton, "pickFieldMenu")),
                ("the axis's reverse button", field.findChild(QtWidgets.QToolButton, "pickFieldReverse")),
                ("the times mark", axis.findChild(QtWidgets.QLabel, "labelTimes")),
                ("the count", axis.findChild(QtWidgets.QSpinBox, "spinOccurrences")),
            ]
        )

    # -- dragging ----------------------------------------------------------

    def _rendered_arm_length(self):
        """The handle arm's actual on-screen length, in document units.

        The rotator arm sits at ``max(minRadius, radius / geometryScale)`` in its own
        pre-scale local frame (SoRotatorArrow::notify, Gizmo.cpp), so at typical view
        distances the ``minRadius`` floor (8 local units, RadialGizmo's default) wins
        over the pattern's own geometric radius (here, RADIAL's length, under 6 mm) -
        the rendered arm is longer than RADIAL, by the view's own auto-scale. Reading
        pivotPosition and geometryScale back from the scene, rather than assuming
        RADIAL's own length, keeps this independent of that (view-dependent) scale.
        """

        container = self._handle_container()
        dragger = container.getPart("dragger", False)
        rotator = dragger.getPart("rotator", False)
        pivot_y = rotator.getField("pivotPosition").getValue().getValue()[1]
        scale_y = rotator.getField("geometryScale").getValue().getValue()[1]
        return pivot_y * scale_y

    def _handle_container(self):
        from pivy import coin

        path = self._search_paths("SoRotationDraggerContainer", coin.SoSearchAction.FIRST).getPath()
        self.assertIsNotNone(path, "the handle is not in the scene")
        return path.getTail()

    def _handle_grip(self, value, arm_length):
        """A point on the handle's arm at the given angle, found by asking the scene
        what is under it, the way _arrow_grip does for the linear arrows (including
        using _pixels(), the product's own projection)."""

        from pivy import coin

        manager = self.viewer.getSoRenderManager()
        direction = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), value).multVec(self.RADIAL)
        direction.normalize()
        tip = self._pixels(self.PIVOT + direction * arm_length)
        base = self._pixels(self.PIVOT)
        for along in (0.0, 0.03, 0.06, 0.1, 0.15, 0.2):
            pixels = (tip[0] + (base[0] - tip[0]) * along, tip[1] + (base[1] - tip[1]) * along)
            pick = coin.SoRayPickAction(manager.getViewportRegion())
            pick.setPoint(coin.SbVec2s(int(pixels[0]), int(pixels[1])))
            pick.setRadius(6)
            pick.setPickAll(True)
            pick.apply(manager.getSceneGraph())
            picked = pick.getPickedPointList()
            for index in range(picked.getLength()):
                path = picked[index].getPath()
                for depth in range(path.getLength()):
                    name = path.getNode(depth).getTypeId().getName().getString()
                    if name == "SoRotationDraggerContainer":
                        return self._qt_pos(pixels)
        self.fail("the handle is not under any of the points tried")

    def _drag_handle_towards(self, start_value, target_value, steps=6, hold_ms=0):
        """Press on the handle at start_value and pull it, in small steps, to
        target_value. Returns whether the handle was hidden after each step (and
        after the hold), while the button was still down."""

        axis = FreeCAD.Vector(0, 0, 1)
        arm_length = self._rendered_arm_length()

        def screen_for(value):
            direction = FreeCAD.Rotation(axis, value).multVec(self.RADIAL)
            direction.normalize()
            return self._qt_pos(self._pixels(self.PIVOT + direction * arm_length))

        grip = self._handle_grip(start_value, arm_length)
        self._mouse(QtCore.QEvent.MouseMove, grip, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self._process_events()
        self._mouse(QtCore.QEvent.MouseButtonPress, grip, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._process_events(100)
        pos = grip
        hidden = []
        try:
            for step in range(1, steps + 1):
                value = start_value + (target_value - start_value) * step / steps
                pos = screen_for(value)
                self._mouse(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
                self._process_events(60)
                hidden.append(not self._handle_shown())
            if hold_ms:
                self._process_events(hold_ms)
                hidden.append(not self._handle_shown())
        finally:
            self._mouse(QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
            self._process_events(300)
        return hidden

    def test_dragging_the_handle_towards_zero_keeps_it_under_the_pointer(self):
        """Dragging the angle down to 0 makes the pattern throw ("Pattern angle can't
        be null"); the 100 ms recompute must not hide the handle out from under a drag
        still holding it, the same guard the linear arrows have (TestLinearArrows).
        Started from a smaller angle than the pattern's default 360 degrees, so the
        drag only has to cover a small, unambiguous arc: SoRotationDragger measures
        each move as the shortest arc from the press point, so a turn approaching a
        full 360 degrees (as dragging down from the default would need) cannot be
        driven reliably this way."""

        self.pattern.Angle = 20.0
        self.doc.recompute()
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
        self._process_events(300)
        self.assertTrue(self._wait(self._handle_shown))

        hidden = self._drag_handle_towards(20.0, -10.0, hold_ms=400)
        self.assertFalse(any(hidden), f"the handle was hidden while dragged: {hidden}")

    # -- reversed ------------------------------------------------------------

    def _handle_arc_normal(self):
        """The handle's current arc-normal direction, in world space (the direction
        SoRotationDraggerContainer.rotation carries local Z to)."""

        container = self._handle_container()
        quat = container.getField("rotation").getValue().getValue()
        return FreeCAD.Rotation(*quat).multVec(FreeCAD.Vector(0, 0, 1))

    def test_a_reversed_pattern_turns_its_handle_the_other_way(self):
        """PolarPatternExtension::getRotation() already reverses the axis when
        Reversed is set, the same direction updateSpacingLabels uses - the handle's
        arc normal should follow that, unreversed a second time."""

        self.pattern.Reversed = True
        self.doc.recompute()
        self._close_editing()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pattern.Name)
        self._process_events(300)
        self.assertTrue(self._wait(self._handle_shown))

        normal = self._handle_arc_normal()
        self.assertLess((normal - FreeCAD.Vector(0, 0, -1)).Length, 1e-4)

    def test_clicking_the_handle_turns_the_pattern_round(self):
        """As on the linear arrows (TestLinearArrows.
        test_clicking_the_arrow_turns_the_pattern_round), letting go without moving
        toggles Reversed rather than dragging - and the handle's own arc normal must
        follow suit in the same panel, not just after a reopen."""

        self.assertTrue(self._wait(self._handle_shown))
        arm_length = self._rendered_arm_length()
        grip = self._handle_grip(0.0, arm_length)
        self._mouse(QtCore.QEvent.MouseButtonPress, grip, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton)
        self._process_events(100)
        self._mouse(QtCore.QEvent.MouseButtonRelease, grip, QtCore.Qt.LeftButton, QtCore.Qt.NoButton)
        self._process_events(300)
        self.assertTrue(self.pattern.Reversed)

        normal = self._handle_arc_normal()
        self.assertLess((normal - FreeCAD.Vector(0, 0, -1)).Length, 1e-4)


class TestMultiTransformStep(PatternPanelCase):
    """A pattern step inside a MultiTransform gets the new panel, but no handles."""

    def setUp(self):
        super().setUp()
        self.multi = self.doc.addObject("PartDesign::MultiTransform", "MultiTransform")
        self.multi.Originals = [self.pad]
        self.step = self.doc.addObject("PartDesign::LinearPattern", "LinearPattern")
        self.step.Direction = (self.sketch, ["H_Axis"])
        self.step.Length = 30.0
        self.step.Occurrences = 2
        self.multi.Transformations = [self.step]
        self.body.addObject(self.multi)
        self.doc.recompute()
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.multi.Name)
        self._process_events(300)
        steps = self._find_widget("listTransformFeatures")
        self.assertIsNotNone(steps, "the MultiTransform panel did not open")
        steps.setCurrentRow(0)
        steps.activated.emit(steps.model().index(0, 0))
        self._process_events(300)
        self.assertIsNotNone(
            self._direction_widget(1), "the step's own pattern panel did not open"
        )

    def test_the_step_shows_the_direction_field(self):
        field = self._direction_field(1)
        self.assertIsNotNone(field, "the step's own pattern panel did not open")
        self.assertTrue(field.isVisible())

    def test_the_step_has_no_features_field_of_its_own(self):
        field = self._find_widget("pickFeatures")
        self.assertTrue(field is None or not field.isVisible())

    def test_the_step_has_no_handles(self):
        from pivy import coin

        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoLinearDraggerContainer"))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        self.assertEqual(search.getPaths().getLength(), 0)
