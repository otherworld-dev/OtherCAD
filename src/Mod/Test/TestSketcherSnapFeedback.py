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

"""GUI regression tests for the Sketcher snap feedback and its way out of a sketch.

Three things are checked here:

* Snapping the pointer onto the grid draws a glyph, and the glyph goes away again
  once the pointer travels back between the grid lines. Point snaps (the origin, a
  vertex, a crossing) already drew one; the grid, the axes and a curve did not, so
  the pointer moved on its own with nothing on screen to explain it.
* Dragging existing geometry does not step from grid line to grid line. The grid
  pulls the pointer while a tool is drawing, but a drag is an adjustment of what is
  already there and has to follow the pointer.
* The way out of a sketch is reachable: Sketcher_LeaveSketch carries a shortcut of
  its own, its tooltip no longer promises that Escape leaves the sketch, and the
  Grid and Snap panels stay available while a tool is drawing.

To run tests:
    FreeCAD -t TestSketcherSnapFeedback
"""

import math
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui

SNAP_PARAMS = "User parameter:BaseApp/Preferences/Mod/Sketcher/Snap"

NO_BUTTON = QtCore.Qt.NoButton
LEFT_BUTTON = QtCore.Qt.LeftButton
NO_MODIFIER = QtCore.Qt.NoModifier
OTHER_FOCUS_REASON = QtCore.Qt.OtherFocusReason
MOUSE_MOVE = QtCore.QEvent.MouseMove
MOUSE_PRESS = QtCore.QEvent.MouseButtonPress
MOUSE_RELEASE = QtCore.QEvent.MouseButtonRelease

# Sketch units between grid lines, and the zoom the tests work at. The grid reaches for
# the pointer over min(GridSnapTolerance, pitch / 3) pixels, so a pitch of 60 puts the
# cap on the preference rather than on the pitch and gives every test the same 15-pixel
# band to work inside, whatever the display scaling is.
GRID_SIZE = 10.0
TARGET_PITCH_PX = 60.0
GRID_SNAP_TOLERANCE = 15.0
SNAP_RADIUS = 8.0

# Pointer travel of the drag test, in device pixels: inside the grid band above, so a
# drag that snapped would be pulled straight back onto the line it started on, and long
# enough that the sketcher takes it for a drag at all. Measured on this build, a press
# that travels 6 device pixels is swallowed and one that travels 9 is not, so the margin
# above the shorter of those matters.
DRAG_TRAVEL_PX = 12.0
MIN_DRAG_TRAVEL_WIDGET_PX = 5


class SketchSnapCase(unittest.TestCase):
    """A sketch in edit mode on the XY plane, seen square-on at a known zoom."""

    def setUp(self):
        self._override_snap_parameters()

        self.doc = FreeCAD.newDocument("TestSketcherSnapFeedback")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.doc.recompute()

        self._process_events(50)
        try:
            self._refresh_view_widgets(timeout_ms=3000)
        except RuntimeError as exc:
            self._abandon_set_up()
            raise unittest.SkipTest(
                "3D view widget wrapping is unavailable in this test environment: " + str(exc)
            )

        # tearDown does not run for a set-up that raises, so from here on a skip - or a
        # failure out of one of the waits - has to hand back the document and the
        # preferences itself.
        try:
            self._prepare_the_sketch_view()
        except Exception:
            self._abandon_set_up()
            raise

    def _prepare_the_sketch_view(self):
        self.viewer.setEnabledNaviCube(False)
        self.view.setAxisCross(False)
        self.view.setCameraType("Orthographic")

        view_object = self.sketch.ViewObject
        view_object.GridAuto = False
        view_object.GridSize = GRID_SIZE
        view_object.ShowGrid = True
        # A constraint born mid-drag would move the point for reasons of its own.
        view_object.Autoconstraints = False

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        FreeCADGui.ActiveDocument.setEdit(self.sketch.Name, 0)
        self._process_events(100)
        self._wait_for_camera_to_settle()
        self._refresh_view_widgets()
        self.viewport.setFocus(OTHER_FOCUS_REASON)
        self._zoom_until_the_grid_is_readable()
        self._wait_for_view_to_settle()
        self._require_a_square_on_view()

    def tearDown(self):
        self._leave_edit_mode()
        self._restore_snap_parameters()
        self._discard_document()

    # -- set-up helpers --------------------------------------------------

    def _leave_edit_mode(self):
        try:
            FreeCADGui.ActiveDocument.resetEdit()
        except Exception:  # noqa: BLE001 - the document may already be gone
            pass
        self._process_events(50)

    def _abandon_set_up(self):
        """Undo a half-finished set-up, which tearDown will never be called to do."""

        self._leave_edit_mode()
        self._restore_snap_parameters()
        self._discard_document()

    def _override_snap_parameters(self):
        self.params = FreeCAD.ParamGet(SNAP_PARAMS)
        self.saved_bools = {
            name: self.params.GetBool(name, True)
            for name in ("Snap", "SnapToObjects", "SnapToGrid")
        }
        # A preference the profile never had is removed again afterwards, not written
        # back with the test's value, which would pin the user to it from then on.
        stored = set(self.params.GetFloats())
        self.saved_floats = {
            name: self.params.GetFloat(name) if name in stored else None
            for name in ("GridSnapTolerance", "SnapRadius")
        }
        for name in self.saved_bools:
            self.params.SetBool(name, True)
        self.params.SetFloat("GridSnapTolerance", GRID_SNAP_TOLERANCE)
        self.params.SetFloat("SnapRadius", SNAP_RADIUS)

    def _restore_snap_parameters(self):
        for name, value in self.saved_bools.items():
            self.params.SetBool(name, value)
        for name, value in self.saved_floats.items():
            if value is None:
                self.params.RemFloat(name)
            else:
                self.params.SetFloat(name, value)

    def _discard_document(self):
        if getattr(self, "doc", None) is not None:
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = None

    def _process_events(self, wait_ms=50):
        FreeCADGui.updateGui()
        app = QtGui.QApplication.instance()
        app.processEvents()
        time.sleep(wait_ms / 1000.0)
        app.processEvents()

    def _refresh_view_widgets(self, timeout_ms=1000):
        """Grab the live 3D view of the test document and its viewport widget.

        Right after a document switch the active view can still be the previous document
        window on its way out - its C++ side already deleted, or laid out to nothing - so
        the view is re-fetched on each try and only a window with a real size is accepted.
        """

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            try:
                self.view = FreeCADGui.getDocument(self.doc.Name).ActiveView
                self.viewer = self.view.getViewer()
                graphics_view = self.view.graphicsView()
                viewport = graphics_view.viewport()
                if viewport.width() > 0 and viewport.height() > 0:
                    self.graphics_view = graphics_view
                    self.viewport = viewport
                    return
                if time.monotonic() >= deadline:
                    raise RuntimeError("the 3D view of the test document never got a size")
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
            self._process_events(20)

    def _camera_state(self):
        camera = self.view.getCameraNode()
        position = FreeCAD.Vector(*camera.position.getValue().getValue())
        orientation = self.view.getCameraOrientation()
        height = camera.height.getValue()
        return position, orientation, height

    def _wait_for_camera_to_settle(self, timeout_ms=3000):
        """Let the animated swing onto the sketch plane finish before reading the camera."""

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        previous = self._camera_state()
        while True:
            self._process_events(100)
            current = self._camera_state()
            if (
                (previous[0] - current[0]).Length <= 1e-3
                and previous[1].isSame(current[1], 1e-4)
                and abs(previous[2] - current[2]) <= 1e-3
            ):
                return
            if time.monotonic() >= deadline:
                self.fail("The camera kept moving after the sketch was opened")
            previous = current

    def _wait_for_view_to_settle(self, timeout_ms=3000):
        """Wait until the viewport size and the projected origin stop changing."""

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        previous = (self.viewport.size(), self._project(0.0, 0.0))
        while True:
            self._process_events(100)
            self._refresh_view_widgets()
            current = (self.viewport.size(), self._project(0.0, 0.0))
            if current == previous:
                return
            if time.monotonic() >= deadline:
                self.fail("The 3D view kept changing size after the sketch was opened")
            previous = current

    def _zoom_until_the_grid_is_readable(self):
        """Put the sketch origin in the middle of the view at a known grid pitch."""

        from pivy import coin

        camera = self.view.getCameraNode()
        pitch = GRID_SIZE / self._units_per_pixel()
        camera.height.setValue(max(1e-6, camera.height.getValue() * pitch / TARGET_PITCH_PX))
        position = camera.position.getValue().getValue()
        camera.position.setValue(coin.SbVec3f(0.0, 0.0, position[2]))
        self._process_events(100)

    def _require_a_square_on_view(self):
        """The tests read pixels along the sketch axes, so the view must be square-on."""

        ox, oy = self._project(0.0, 0.0)
        x_axis = self._project(GRID_SIZE, 0.0)
        y_axis = self._project(0.0, GRID_SIZE)
        if (
            abs(x_axis[1] - oy) > 1.0
            or abs(y_axis[0] - ox) > 1.0
            or x_axis[0] <= ox
            or y_axis[1] <= oy
        ):
            raise unittest.SkipTest("The sketch plane is not seen square-on in this environment")

        pitch = GRID_SIZE / self._units_per_pixel()
        if pitch < 24.0:
            raise unittest.SkipTest("The 3D view is too small to draw a readable grid")

    # -- geometry of the view --------------------------------------------

    def _device_pixel_ratio(self):
        if hasattr(self.viewport, "devicePixelRatioF"):
            return self.viewport.devicePixelRatioF()
        return float(self.viewport.devicePixelRatio())

    def _project(self, u, v):
        """Device pixels, measured from the bottom-left corner, of a sketch point."""

        px, py = self.view.getPointOnScreen(FreeCAD.Vector(u, v, 0.0))
        return float(px), float(py)

    def _units_per_pixel(self):
        origin = self._project(0.0, 0.0)
        along_x = self._project(GRID_SIZE, 0.0)
        distance = math.hypot(along_x[0] - origin[0], along_x[1] - origin[1])
        if distance <= 0.0:
            raise unittest.SkipTest("The 3D view does not project the sketch plane")
        return GRID_SIZE / distance

    def _widget_point(self, u, v):
        px, py = self._project(u, v)
        dpr = self._device_pixel_ratio()
        # The exact inverse of Quarter's mapping, which counts a Qt row y as Coin row
        # height - 1 - y (see TestExtrudeFlip._qt_pos).
        return QtCore.QPoint(
            int(round(px / dpr)), int(round(self.viewport.height() - 1 - py / dpr))
        )

    def _grid_tolerance(self):
        """How far, in sketch units, the grid reaches for the pointer."""

        units_per_pixel = self._units_per_pixel()
        pitch_px = GRID_SIZE / units_per_pixel
        return min(GRID_SNAP_TOLERANCE, pitch_px / 3.0) * units_per_pixel

    def _grid_point(self):
        """A grid intersection well clear of the origin and of both axes."""

        return 2.0 * GRID_SIZE, 2.0 * GRID_SIZE

    def _require_on_screen(self, points):
        rect = self.viewport.rect().adjusted(20, 20, -20, -20)
        for u, v in points:
            if not rect.contains(self._widget_point(u, v)):
                raise unittest.SkipTest("The 3D view is too small to hold the test sketch")

    # -- driving the pointer ---------------------------------------------

    def _send_mouse_event(self, event_type, pos, button, buttons):
        self._refresh_view_widgets()
        app = QtGui.QApplication.instance()
        global_pos = self.viewport.mapToGlobal(pos)
        event = QtGui.QMouseEvent(event_type, pos, global_pos, button, buttons, NO_MODIFIER)
        app.sendEvent(self.viewport, event)

    def _move_pointer(self, u, v, wait_ms=50):
        self._send_mouse_event(MOUSE_MOVE, self._widget_point(u, v), NO_BUTTON, NO_BUTTON)
        self._process_events(wait_ms)

    def _hover_until_preselected(self, pos, message):
        """Park the pointer on a widget position until the sketch preselects a vertex there."""

        for _ in range(5):
            self._send_mouse_event(MOUSE_MOVE, pos, NO_BUTTON, NO_BUTTON)
            self._process_events(80)
            preselection = FreeCADGui.Selection.getPreselection()
            names = getattr(preselection, "SubElementNames", ())
            if preselection.ObjectName and names and names[0].startswith("Vertex"):
                return names[0]
        self.fail(message)
        return None

    def _start_line_tool(self):
        FreeCADGui.runCommand("Sketcher_CreateLine", 0)
        self._process_events(100)

    # -- reading the snap glyph ------------------------------------------

    def _find_edit_node(self, name):
        """A node of the sketch's edit-mode scene graph, by name.

        Searched from the view, not from ``ViewObject.RootNode``: the edit-mode nodes are
        hung off the viewer's scene graph while the sketch is open, and the view provider's
        own root comes back empty.
        """

        from pivy import coin

        self._refresh_view_widgets()
        search = coin.SoSearchAction()
        search.setName(coin.SbName(name))
        search.setInterest(coin.SoSearchAction.FIRST)
        search.setSearchingAll(True)
        search.apply(self.view.getSceneGraph())
        path = search.getPath()
        return path.getTail() if path else None

    def _snap_marker(self):
        """Where the snap glyph is drawn, or None while no glyph is on screen."""

        marker = self._find_edit_node("SnapMarkerSet")
        if marker is None:
            self.fail("The sketch edit scene graph has no SnapMarkerSet node")
        if marker.numPoints.getValue() < 1:
            return None
        coordinate = self._find_edit_node("SnapMarkerCoordinate")
        self.assertIsNotNone(coordinate, "A snap glyph must come with its coordinate")
        point = coordinate.point.getValues()[0].getValue()
        return point[0], point[1]

    def _snap_marker_index(self):
        """Which bitmap the snap glyph is currently drawn with."""

        marker = self._find_edit_node("SnapMarkerSet")
        self.assertIsNotNone(marker, "The sketch edit scene graph has no SnapMarkerSet node")
        field = marker.markerIndex
        values = field.getValues() if hasattr(field, "getValues") else [field.getValue()]
        self.assertTrue(len(values), "A snap glyph has to name the bitmap it uses")
        return int(values[0])

    def _built_in_marker_indices(self, family):
        """The indices Coin names itself, for the handful of sizes it ships bitmaps for.

        FreeCAD registers the larger bitmaps at run time and their indices have no name, so
        this comes back empty whenever the glyph landed on one of those.
        """

        from pivy import coin

        indices = set()
        for size in (5, 7, 9):
            name = "{}_{}_{}".format(family, size, size)
            if hasattr(coin.SoMarkerSet, name):
                indices.add(int(getattr(coin.SoMarkerSet, name)))
        return indices

    def _snapped_marker_at(self, u, v, message):
        """Move the pointer to (u, v) and return the glyph, retrying the first frame."""

        for _ in range(3):
            self._move_pointer(u, v)
            marker = self._snap_marker()
            if marker is not None:
                return marker
            self._process_events(100)
        self.fail(message)
        return None

    # -- dragging --------------------------------------------------------

    def _reset_line(self, start, end):
        import Part

        if self.sketch.GeometryCount:
            self.sketch.delGeometry(0)
        self.sketch.addGeometry(
            Part.LineSegment(
                FreeCAD.Vector(start[0], start[1], 0.0),
                FreeCAD.Vector(end[0], end[1], 0.0),
            ),
            False,
        )
        self.doc.recompute()
        self._process_events(50)

    def _drag_end_point(self, grab, travel_px):
        """Press on the sketch point at grab, pull it travel_px along +X, release."""

        press = self._widget_point(*grab)
        widget_travel = int(round(travel_px / self._device_pixel_ratio()))
        if widget_travel < MIN_DRAG_TRAVEL_WIDGET_PX:
            raise unittest.SkipTest(
                "the display scaling leaves no travel that is both a drag and inside the grid"
            )
        target = QtCore.QPoint(press.x() + widget_travel, press.y())

        # A press only starts a drag on what is preselected under it, and the first move
        # after a view is built can land before its first frame, so wait for the vertex.
        self._hover_until_preselected(press, "The pointer never picked up the point to drag")

        self._send_mouse_event(MOUSE_PRESS, press, LEFT_BUTTON, LEFT_BUTTON)
        self._process_events(50)
        # The first move past the ignored distance only starts the drag; the second
        # one is the first that moves anything.
        self._send_mouse_event(MOUSE_MOVE, target, NO_BUTTON, LEFT_BUTTON)
        self._process_events(50)
        self._send_mouse_event(MOUSE_MOVE, target, NO_BUTTON, LEFT_BUTTON)
        self._process_events(50)
        self._send_mouse_event(MOUSE_RELEASE, target, LEFT_BUTTON, NO_BUTTON)
        self._process_events(150)

        return self.sketch.Geometry[0].EndPoint


class TestSketcherSnapFeedback(SketchSnapCase):
    """The snap glyphs, and a drag that stays off the grid."""

    def test_snapping_to_the_grid_draws_a_marker_of_its_own(self):
        grid_x, grid_y = self._grid_point()
        half = GRID_SIZE / 2.0
        # Half a cell out on both axes, so the grid cannot reach it and only the vertex can.
        vertex = (grid_x + half, grid_y + half)
        far_end = (vertex[0] + GRID_SIZE, vertex[1])
        self._require_on_screen([(grid_x, grid_y), vertex, far_end])
        offset = 0.35 * self._grid_tolerance()

        self._reset_line(vertex, far_end)
        self._start_line_tool()

        marker = self._snapped_marker_at(
            grid_x + offset,
            grid_y + offset,
            "Snapping the pointer onto a grid intersection must draw a marker",
        )
        grid_index = self._snap_marker_index()
        self.assertAlmostEqual(marker[0], grid_x, delta=0.01)
        self.assertAlmostEqual(marker[1], grid_y, delta=0.01)

        # One glyph for every kind of snap would say no more than none at all: catching a
        # vertex has to look different from settling onto a grid line.
        caught = self._snapped_marker_at(
            vertex[0], vertex[1], "Snapping the pointer onto a vertex must draw a marker"
        )
        vertex_index = self._snap_marker_index()
        self.assertAlmostEqual(caught[0], vertex[0], delta=0.01)
        self.assertAlmostEqual(caught[1], vertex[1], delta=0.01)

        self.assertNotEqual(
            grid_index,
            vertex_index,
            "the grid and a vertex must not be marked with the same glyph",
        )

        # Both glyphs pick their size by the same rule out of the same table, so when the
        # vertex landed on a size Coin names, the grid glyph can be named exactly too.
        if vertex_index in self._built_in_marker_indices("SQUARE_FILLED"):
            self.assertIn(
                grid_index,
                self._built_in_marker_indices("SQUARE_LINE"),
                "the grid snap must be marked with an outlined square",
            )

    def test_the_marker_goes_away_between_the_grid_lines(self):
        grid_x, grid_y = self._grid_point()
        half = GRID_SIZE / 2.0
        self._require_on_screen([(grid_x, grid_y), (grid_x + half, grid_y + half)])
        offset = 0.35 * self._grid_tolerance()

        self._start_line_tool()
        self._snapped_marker_at(
            grid_x + offset, grid_y + offset, "The grid snap must draw a marker to begin with"
        )

        self._move_pointer(grid_x + half, grid_y + half)
        self.assertIsNone(
            self._snap_marker(),
            "The marker must go away once the pointer travels between the grid lines",
        )

    def test_dragging_a_point_does_not_step_along_the_grid(self):
        grid_x, grid_y = self._grid_point()
        start = (grid_x, grid_y)
        other = (grid_x - GRID_SIZE, grid_y)
        self._require_on_screen([start, other])

        travel = DRAG_TRAVEL_PX * self._units_per_pixel()
        self.assertLess(
            travel,
            self._grid_tolerance(),
            "the drag has to stay inside the pull of the grid line it starts on",
        )

        # A drag with the grid snap switched off is what every drag should do.
        self.params.SetBool("SnapToGrid", False)
        self._reset_line(other, start)
        free = self._drag_end_point(start, DRAG_TRAVEL_PX)
        self.assertGreater(
            abs(free.x - grid_x),
            0.5 * travel,
            "the point was never dragged, so the test would prove nothing",
        )

        # Park the pointer well away so the next press is not read as a double click.
        self._move_pointer(grid_x, grid_y - GRID_SIZE, wait_ms=400)

        self.params.SetBool("SnapToGrid", True)
        self._reset_line(other, start)
        snapped = self._drag_end_point(start, DRAG_TRAVEL_PX)

        self.assertAlmostEqual(
            snapped.x,
            free.x,
            delta=0.01,
            msg="dragging a point must not step from grid line to grid line",
        )
        self.assertAlmostEqual(snapped.y, free.y, delta=0.01)

    def test_grid_and_snap_stay_available_while_a_tool_draws(self):
        """A lock, not a verification.

        Both toggles already answered yes mid-tool before this change - the helper they used
        never looked at the running handler, whatever its name says. The test is here so that
        a future tightening of either isActive() cannot quietly take the Grid and Snap panels
        away from someone halfway through drawing.
        """

        grid_x, grid_y = self._grid_point()
        self._require_on_screen([(grid_x, grid_y)])
        offset = 0.35 * self._grid_tolerance()

        self._start_line_tool()
        # A snap marker is only ever drawn by a running tool, so this both proves the
        # tool is drawing and sets up the state the toggles used to be refused in.
        self._snapped_marker_at(
            grid_x + offset, grid_y + offset, "The line tool must be drawing for this test"
        )

        self.assertTrue(
            FreeCADGui.Command.get("Sketcher_Snap").isActive(),
            "The Snap panel must stay available while a tool is drawing",
        )
        self.assertTrue(
            FreeCADGui.Command.get("Sketcher_Grid").isActive(),
            "The Grid panel must stay available while a tool is drawing",
        )


class TestSnapAutoConstraints(SketchSnapCase):
    """A point a snap puts on a special point of a curve is constrained to stay there.

    The snap recorded what it caught, but the autoconstraints came from preselection, which
    only knows the curve: a point snapped to an arc's midpoint, a quadrant or a crossing got
    point-on-object and slid along the curve as soon as anything moved. Each test blocks the
    curves it snapped to and counts what is left free.
    """

    def _prepare_the_sketch_view(self):
        super()._prepare_the_sketch_view()
        self.sketch.ViewObject.Autoconstraints = True

    # -- building and reading the sketch ---------------------------------

    def _add(self, geometry):
        index = self.sketch.addGeometry(geometry, False)
        self.doc.recompute()
        self._process_events(50)
        return index

    def _add_arc(self, centre, radius, start_deg, end_deg):
        import Part

        circle = Part.Circle(
            FreeCAD.Vector(centre[0], centre[1], 0.0), FreeCAD.Vector(0, 0, 1), radius
        )
        return self._add(Part.ArcOfCircle(circle, math.radians(start_deg), math.radians(end_deg)))

    def _add_circle(self, centre, radius):
        import Part

        return self._add(
            Part.Circle(FreeCAD.Vector(centre[0], centre[1], 0.0), FreeCAD.Vector(0, 0, 1), radius)
        )

    def _add_line(self, start, end):
        import Part

        return self._add(
            Part.LineSegment(
                FreeCAD.Vector(start[0], start[1], 0.0), FreeCAD.Vector(end[0], end[1], 0.0)
            )
        )

    @staticmethod
    def _arc_midpoint(arc):
        middle = 0.5 * (arc.FirstParameter + arc.LastParameter)
        return (
            arc.Location.x + arc.Radius * math.cos(middle),
            arc.Location.y + arc.Radius * math.sin(middle),
        )

    def _new_point_index(self):
        import Part

        indices = [
            i for i, geometry in enumerate(self.sketch.Geometry) if isinstance(geometry, Part.Point)
        ]
        self.assertEqual(len(indices), 1, "the point tool must have placed exactly one point")
        return indices[0]

    def _block(self, *geo_ids):
        import Sketcher

        for geo_id in geo_ids:
            self.sketch.addConstraint(Sketcher.Constraint("Block", geo_id))
        self.sketch.solve()

    def _assert_free_and_clean(self, dof, message):
        self.assertEqual(self.sketch.ConflictingConstraints, [], "no conflicts")
        self.assertEqual(self.sketch.RedundantConstraints, [], "no redundant constraints")
        self.assertEqual(self.sketch.PartiallyRedundantConstraints, [], "no partial redundancy")
        self.assertEqual(self.sketch.DoF, dof, message)

    def _constraints_on(self, geo_id, pos):
        return [
            c
            for c in self.sketch.Constraints
            if (c.First == geo_id and c.FirstPos == pos)
            or (c.Second == geo_id and c.SecondPos == pos)
        ]

    # -- driving the tools -----------------------------------------------

    def _click_on_snap(self, u, v, message):
        """Hover until the snap glyph sits on (u, v), then click there."""

        marker = self._snapped_marker_at(u, v, message)
        self.assertAlmostEqual(marker[0], u, delta=1e-3, msg=message)
        self.assertAlmostEqual(marker[1], v, delta=1e-3, msg=message)
        pos = self._widget_point(u, v)
        self._send_mouse_event(MOUSE_PRESS, pos, LEFT_BUTTON, LEFT_BUTTON)
        self._process_events(50)
        self._send_mouse_event(MOUSE_RELEASE, pos, LEFT_BUTTON, NO_BUTTON)
        self._process_events(150)

    def _place_point(self, u, v, message):
        FreeCADGui.runCommand("Sketcher_CreatePoint", 0)
        self._process_events(100)
        self._click_on_snap(u, v, message)

    def _draw_line(self, start, end, start_message, end_message):
        self._start_line_tool()
        self._click_on_snap(start[0], start[1], start_message)
        # Far enough apart that the second press is not read as a double click.
        self._process_events(400)
        self._click_on_snap(end[0], end[1], end_message)

    # -- the tests -------------------------------------------------------

    def test_a_point_snapped_to_an_arc_midpoint_stays_at_the_middle(self):
        arc_id = self._add_arc((5.0, 3.0), 15.0, 20.0, 110.0)
        middle = self._arc_midpoint(self.sketch.Geometry[arc_id])
        self._require_on_screen([middle])

        self._place_point(*middle, "the pointer must snap to the arc's midpoint")
        point_id = self._new_point_index()

        self._block(arc_id)
        self._assert_free_and_clean(
            0, "a point snapped to an arc's midpoint must not be free to slide along the arc"
        )

        # Swing the arc's end round: the point has to follow the middle, not stay put.
        self.sketch.delConstraint(self.sketch.ConstraintCount - 1)
        self.sketch.solve()
        swung = math.radians(160.0)
        arc = self.sketch.Geometry[arc_id]
        self.sketch.moveGeometry(
            arc_id,
            2,
            FreeCAD.Vector(
                arc.Location.x + arc.Radius * math.cos(swung),
                arc.Location.y + arc.Radius * math.sin(swung),
                0.0,
            ),
        )
        self.sketch.solve()
        arc = self.sketch.Geometry[arc_id]
        self.assertGreater(
            math.degrees(arc.LastParameter),
            130.0,
            "the arc's end never moved, so this proves nothing",
        )
        expected = self._arc_midpoint(arc)
        point = self.sketch.getPoint(point_id, 1)
        self.assertAlmostEqual(point.x, expected[0], delta=1e-6)
        self.assertAlmostEqual(point.y, expected[1], delta=1e-6)

    def test_a_line_drawn_from_an_arc_midpoint_keeps_its_start_there(self):
        arc_id = self._add_arc((5.0, 3.0), 15.0, 20.0, 110.0)
        middle = self._arc_midpoint(self.sketch.Geometry[arc_id])
        # Half a cell clear of the grid lines and well off any horizontal or vertical.
        free_end = (25.0, 35.0)
        self._require_on_screen([middle, free_end])

        self._start_line_tool()
        self._click_on_snap(*middle, "the line must start on the arc's midpoint snap")
        # Far enough apart in time that the second press is not read as a double click.
        self._process_events(400)
        self._move_pointer(*free_end)
        pos = self._widget_point(*free_end)
        self._send_mouse_event(MOUSE_PRESS, pos, LEFT_BUTTON, LEFT_BUTTON)
        self._process_events(50)
        self._send_mouse_event(MOUSE_RELEASE, pos, LEFT_BUTTON, NO_BUTTON)
        self._process_events(150)

        self._block(arc_id)
        # The free end keeps its two degrees of freedom; the start has none.
        self._assert_free_and_clean(
            2, "a line end snapped to an arc's midpoint must not be free to slide along the arc"
        )

    def test_a_polyline_from_an_arc_midpoint_stays_joined_up(self):
        """The construction radius is added between segments; the polyline must not mind."""

        import Part

        arc_id = self._add_arc((5.0, 3.0), 15.0, 20.0, 110.0)
        middle = self._arc_midpoint(self.sketch.Geometry[arc_id])
        # Off the grid lines and not horizontal or vertical from each other.
        corner = (25.0, 35.0)
        far_end = (35.0, 45.0)
        self._require_on_screen([middle, corner, far_end])

        FreeCADGui.runCommand("Sketcher_CreatePolyline", 0)
        self._process_events(100)
        self._click_on_snap(*middle, "the polyline must start on the arc's midpoint snap")
        for point in (corner, far_end):
            self._process_events(400)
            self._move_pointer(*point)
            pos = self._widget_point(*point)
            self._send_mouse_event(MOUSE_PRESS, pos, LEFT_BUTTON, LEFT_BUTTON)
            self._process_events(50)
            self._send_mouse_event(MOUSE_RELEASE, pos, LEFT_BUTTON, NO_BUTTON)
            self._process_events(150)

        segments = [
            i
            for i, g in enumerate(self.sketch.Geometry)
            if isinstance(g, Part.LineSegment) and not self.sketch.getConstruction(i)
        ]
        self.assertEqual(len(segments), 2, "the polyline must have drawn two segments")
        first, second = segments
        joined = self.sketch.getPoint(first, 2) - self.sketch.getPoint(second, 1)
        self.assertLess(joined.Length, 1e-6, "the second segment must start where the first ends")

        self._block(arc_id)
        # The corner and the far end are free; the start on the arc is not.
        self._assert_free_and_clean(
            4, "a polyline started on an arc's midpoint must not be free to slide along the arc"
        )

    def test_a_line_between_two_quadrants_is_held_level_and_plumb_with_the_centre(self):
        centre = (25.0, 15.0)
        radius = 8.0
        circle_id = self._add_circle(centre, radius)
        right = (centre[0] + radius, centre[1])
        top = (centre[0], centre[1] + radius)
        self._require_on_screen([right, top])

        self._draw_line(
            right,
            top,
            "the line must start on the circle's right-hand quadrant",
            "the line must end on the circle's top quadrant",
        )
        line_id = self.sketch.GeometryCount - 1
        self.assertNotEqual(line_id, circle_id, "the line tool must have drawn a line")

        alignments = {
            c.Type
            for pos in (1, 2)
            for c in self._constraints_on(line_id, pos)
            if c.Type in ("Horizontal", "Vertical") and c.Second == circle_id and c.SecondPos == 3
        }
        self.assertEqual(
            alignments,
            {"Horizontal", "Vertical"},
            "the side quadrant must be level with the centre and the top one plumb over it",
        )

        self._block(circle_id)
        self._assert_free_and_clean(
            0, "line ends snapped to quadrants must not be free to slide round the circle"
        )

    def test_a_point_snapped_to_a_crossing_stays_on_both_curves(self):
        centre = (25.0, 15.0)
        radius = 8.0
        circle_id = self._add_circle(centre, radius)
        line_id = self._add_line((12.0, 19.0), (38.0, 19.0))
        crossing = (centre[0] + math.sqrt(radius**2 - 4.0**2), 19.0)
        self._require_on_screen([crossing])

        self._place_point(*crossing, "the pointer must snap to where the line crosses the circle")
        point_id = self._new_point_index()

        on_object = {
            c.Second for c in self._constraints_on(point_id, 1) if c.Type == "PointOnObject"
        }
        self.assertEqual(
            on_object, {circle_id, line_id}, "a crossing must put the point on both curves"
        )

        # Both constraints belong to one undo step.
        constraint_count = self.sketch.ConstraintCount
        self.doc.undo()
        self._process_events(50)
        self.assertEqual(self.sketch.ConstraintCount, 0, "one undo must take both constraints off")
        self.assertEqual(self.sketch.GeometryCount, 3, "and leave the point where it was put")
        self.doc.redo()
        self._process_events(50)
        self.assertEqual(self.sketch.ConstraintCount, constraint_count)

        self._block(circle_id, line_id)
        self._assert_free_and_clean(
            0, "a point snapped to a crossing must not be free to slide along either curve"
        )


class TestSketcherLeaveSketch(unittest.TestCase):
    """Leaving a sketch has to be reachable, and has to say so honestly."""

    def setUp(self):
        FreeCADGui.activateWorkbench("SketcherWorkbench")
        self.command = FreeCADGui.Command.get("Sketcher_LeaveSketch")
        if self.command is None:
            raise unittest.SkipTest("The Sketcher commands are not registered")

    def test_leave_sketch_has_a_shortcut_of_its_own(self):
        shortcut = self.command.getShortcut()
        self.assertNotEqual(shortcut, "", "Leaving a sketch needs a keyboard shortcut")
        self.assertEqual(
            FreeCADGui.Command.listByShortcut(shortcut),
            ["Sketcher_LeaveSketch"],
            "The shortcut for leaving a sketch must not be shared with another command",
        )

    def test_leave_sketch_does_not_promise_that_escape_leaves(self):
        tooltip = self.command.getInfo()["toolTip"]
        self.assertNotIn(
            "Escape",
            tooltip,
            "Escape stops the running tool, so the tooltip must not offer it as the way out",
        )


if __name__ == "__main__":
    unittest.main()


class _SnapBandInScreenPixels:
    """The grid snap band is GridSnapTolerance pixels on screen, whatever the view's shape.

    The sketcher converted its pixel settings to sketch units through the camera's view
    volume before viewport mapping, which for a view wider than tall is narrower than what
    is drawn by the view's aspect ratio. A 15 px band was 8 px in a 16:9 view, and less
    still in a wider one, while a tall view was right. Mixed into a SketchSnapCase with
    VIEW_SIZE set to the shape to check.
    """

    VIEW_SIZE = (0, 0)

    def _prepare_the_sketch_view(self):
        self._original_window_size = FreeCADGui.getMainWindow().size()
        self._shape_view(*self.VIEW_SIZE)
        super()._prepare_the_sketch_view()

    def tearDown(self):
        super().tearDown()
        self._restore_window_size()

    def _abandon_set_up(self):
        super()._abandon_set_up()
        self._restore_window_size()

    def _restore_window_size(self):
        size = getattr(self, "_original_window_size", None)
        if size is not None:
            FreeCADGui.getMainWindow().resize(size)
            self._process_events(300)

    def _shape_view(self, width, height):
        """Reshape the 3D view towards width x height, as TestViewportProjection does.

        A maximised main window may refuse the resize, so the MDI sub-window is tried
        next. The test fails rather than skips if neither gives the wanted shape, since a
        skipped wide case would say nothing about the defect it is here for.
        """

        from PySide import QtWidgets

        wanted_wide = width > height
        window = FreeCADGui.getMainWindow()
        window.resize(width, height)
        self._process_events(400)
        self._refresh_view_widgets()
        if (self.viewport.width() > self.viewport.height()) != wanted_wide:
            mdi_area = window.findChild(QtWidgets.QMdiArea)
            sub_window = mdi_area.activeSubWindow() if mdi_area is not None else None
            if sub_window is not None:
                sub_window.resize(width, height)
                self._process_events(400)
                self._refresh_view_widgets()

        size = self.viewport.size()
        self.assertEqual(
            size.width() > size.height(),
            wanted_wide,
            "the window manager gave a {}x{} view, not the {} shape this test needs".format(
                size.width(), size.height(), "wide" if wanted_wide else "tall"
            ),
        )

    def _line_marker_at(self, u, v):
        """The glyph after moving the pointer to (u, v), or None, giving the frame a retry."""

        for _ in range(3):
            self._move_pointer(u, v)
            marker = self._snap_marker()
            if marker is not None:
                return marker
        return None

    def test_the_grid_reaches_as_many_screen_pixels_as_the_preference_says(self):
        grid_x, grid_y = self._grid_point()
        half = GRID_SIZE / 2.0
        # Half a cell up, so only the vertical line through grid_x is within reach.
        v = grid_y + half
        self._require_on_screen([(grid_x, v), (grid_x + half, v)])

        units_per_pixel = self._units_per_pixel()
        pitch_px = GRID_SIZE / units_per_pixel
        band_px = min(GRID_SNAP_TOLERANCE, pitch_px / 3.0)
        # Well inside and well outside the band; both stay short of the half pitch, so
        # the line they are measured from is the nearest one either way.
        inside = 0.75 * band_px * units_per_pixel
        outside = 1.25 * band_px * units_per_pixel
        self.assertLess(outside, half)

        self._start_line_tool()

        marker = self._line_marker_at(grid_x + inside, v)
        self.assertIsNotNone(
            marker,
            "{:.1f} screen pixels from a grid line is inside a {:.0f} px band, so the "
            "pointer must snap ({}x{} view)".format(
                0.75 * band_px, band_px, self.viewport.width(), self.viewport.height()
            ),
        )
        self.assertAlmostEqual(marker[0], grid_x, delta=0.01)

        self.assertIsNone(
            self._line_marker_at(grid_x + outside, v),
            "{:.1f} screen pixels from a grid line is outside a {:.0f} px band, so the "
            "pointer must move freely ({}x{} view)".format(
                1.25 * band_px, band_px, self.viewport.width(), self.viewport.height()
            ),
        )


class TestSnapBandInAWideView(_SnapBandInScreenPixels, SketchSnapCase):
    VIEW_SIZE = (1800, 700)


class TestSnapBandInATallView(_SnapBandInScreenPixels, SketchSnapCase):
    VIEW_SIZE = (800, 1300)
