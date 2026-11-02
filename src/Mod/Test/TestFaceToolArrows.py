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

"""GUI tests for the arrows on the direct edit face tools.

Offset Face, Move Face and Press/Pull on a face put an arrow on the picked face, along
its outward normal, with its value in a box beside it, the way Fusion's Press Pull
does. Offset Face also takes curved faces, which grow or shrink by the distance.

To run tests:
    FreeCAD -t TestFaceToolArrows
"""

import math

import FreeCAD
import FreeCADGui
import Part
from PySide import QtCore

import TestGizmoValueLabels as labels
import TestPartDesignLetters as letters

# Borrowed through the module, so this suite does not run the letter tests again.
ModalCloser = letters.TestPartDesignLetters._ModalCloser


class FaceToolCase(labels.GizmoLabelCase):
    """The 10 x 6 x 10 Pad of the gizmo tests, with a face tool started on one of its faces."""

    # The Pad is a 10 x 6 rectangle on the XY plane, 10 mm high.
    TOP_CENTRE = FreeCAD.Vector(5.0, 3.0, 10.0)

    def setUp(self):
        super().setUp()
        self._close_editing()

    # -- helpers ---------------------------------------------------------

    def _face_where(self, shape, test):
        for index, face in enumerate(shape.Faces):
            if test(face):
                return "Face%d" % (index + 1)
        self.fail("no face matched")

    def _top_face(self):
        return self._face_where(
            self.pad.Shape,
            lambda face: isinstance(face.Surface, Part.Plane)
            and abs(face.CenterOfMass.z - 10.0) < 1e-6,
        )

    def _start(self, command, feature, face):
        """Run command on face of feature and return the new feature, now in edit."""

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, feature.Name, face)
        before = set(obj.Name for obj in self.doc.Objects)
        with ModalCloser() as closer:
            FreeCADGui.runCommand(command)
            self._process_events(200)
        self.assertEqual(closer.closed, [], "the tool refused the face")
        added = [obj for obj in self.doc.Objects if obj.Name not in before]
        self.assertEqual(len(added), 1, "expected the tool to add one feature")
        self._refresh_view_widgets()
        self._settle_view()
        return added[0]

    def _arrow(self):
        """The arrow's foot and its direction."""

        from pivy import coin

        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName("SoLinearDraggerContainer"))
        search.setInterest(coin.SoSearchAction.FIRST)
        search.setSearchingAll(True)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        path = search.getPath()
        self.assertIsNotNone(path, "no arrow in the scene")
        self.assertTrue(self._path_is_on(path), "the arrow is switched off")
        node = path.getTail()
        foot = coin.cast(node.getField("translation"), "SoSFVec3f").getValue()
        rotation = coin.cast(node.getField("rotation"), "SoSFRotation").getValue()
        direction = rotation.multVec(coin.SbVec3f(0.0, 1.0, 0.0))
        return (
            FreeCAD.Vector(*foot.getValue()),
            FreeCAD.Vector(*direction.getValue()).normalize(),
        )

    def _assert_vector(self, actual, expected, places=4):
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places, msg=f"{actual} != {expected}")

    def _grip(self, start, end):
        """Screen pixels on the arrow between points start and end, found by ray picks."""

        from pivy import coin

        manager = self.viewer.getSoRenderManager()
        first = self._pixels(start)
        last = self._pixels(end)
        for step in range(21):
            along = step / 20.0
            pixels = (
                first[0] + (last[0] - first[0]) * along,
                first[1] + (last[1] - first[1]) * along,
            )
            pick = coin.SoRayPickAction(manager.getViewportRegion())
            pick.setPoint(coin.SbVec2s(int(pixels[0]), int(pixels[1])))
            pick.setRadius(4)
            pick.setPickAll(True)
            pick.apply(manager.getSceneGraph())
            picked = pick.getPickedPointList()
            for index in range(picked.getLength()):
                path = picked[index].getPath()
                for depth in range(path.getLength()):
                    name = path.getNode(depth).getTypeId().getName().getString()
                    if name == "SoLinearDraggerContainer":
                        return pixels
        self.fail("the arrow is not under any of the points tried")

    def _drag_arrow_by(self, value, millimetres):
        """Drag the arrow, whose tip shows value, a distance along its own direction."""

        foot, direction = self._arrow()
        tip = foot + direction * value
        grip = self._qt_pos(self._grip(tip, tip + direction * 10.0))
        ahead = self._qt_pos(self._pixels(tip + direction * 10.0))
        here = self._qt_pos(self._pixels(tip))
        per_mm = QtCore.QPointF((ahead.x() - here.x()) / 10.0, (ahead.y() - here.y()) / 10.0)
        self._mouse(QtCore.QEvent.MouseMove, grip, QtCore.Qt.NoButton, QtCore.Qt.NoButton)
        self._process_events()
        self._mouse(
            QtCore.QEvent.MouseButtonPress, grip, QtCore.Qt.LeftButton, QtCore.Qt.LeftButton
        )
        self._process_events(100)
        pos = grip
        try:
            for step in range(1, 6):
                travel = millimetres * step / 5.0
                pos = QtCore.QPointF(grip.x() + per_mm.x() * travel, grip.y() + per_mm.y() * travel)
                self._mouse(QtCore.QEvent.MouseMove, pos, QtCore.Qt.NoButton, QtCore.Qt.LeftButton)
                self._process_events(100)
        finally:
            self._mouse(
                QtCore.QEvent.MouseButtonRelease, pos, QtCore.Qt.LeftButton, QtCore.Qt.NoButton
            )
            self._process_events(100)


class TestOffsetFaceArrow(FaceToolCase):
    def test_the_panel_has_its_offset_field(self):
        self._start("PartDesign_OffsetFace", self.pad, self._top_face())
        self.assertIsNotNone(self._find_widget("offsetFaceDistance"), "no Offset field")

    def test_the_arrow_stands_on_the_face_along_its_normal(self):
        self._start("PartDesign_OffsetFace", self.pad, self._top_face())
        foot, direction = self._arrow()
        self._assert_vector(foot, self.TOP_CENTRE)
        self._assert_vector(direction, FreeCAD.Vector(0.0, 0.0, 1.0))

    def test_the_offset_shows_in_a_box_in_the_view(self):
        feature = self._start("PartDesign_OffsetFace", self.pad, self._top_face())
        box = self._wait_for_distance_boxes(1)[0]
        self.assertAlmostEqual(box.property("rawValue"), feature.Offset.Value)

    def test_dragging_the_arrow_out_pulls_the_face_out(self):
        feature = self._start("PartDesign_OffsetFace", self.pad, self._top_face())
        before = feature.Offset.Value
        self._drag_arrow_by(before, 4.0)
        self.assertGreater(feature.Offset.Value, before + 2.0)
        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.Shape.Volume, 60.0 * (10.0 + feature.Offset.Value), places=3)


class TestCurvedFaceArrow(FaceToolCase):
    """A hole of radius 2 through the Pad, whose wall is a curved face."""

    AXIS = FreeCAD.Vector(5.0, 3.0, 0.0)

    def setUp(self):
        super().setUp()
        self.hole = self.doc.addObject("PartDesign::SubtractiveCylinder", "Hole")
        self.hole.Radius = 2.0
        self.hole.Height = 10.0
        self.hole.Placement.Base = self.AXIS
        self.body.addObject(self.hole)
        self.doc.recompute()
        self.wall = self._face_where(
            self.hole.Shape, lambda face: isinstance(face.Surface, Part.Cylinder)
        )

    def test_press_pull_offsets_a_curved_face_instead_of_refusing_it(self):
        feature = self._start("PartDesign_PressPull", self.hole, self.wall)
        self.assertEqual(feature.TypeId, "PartDesign::OffsetFace")

    def test_the_arrow_points_out_of_the_material_into_the_hole(self):
        self._start("PartDesign_OffsetFace", self.hole, self.wall)
        foot, direction = self._arrow()
        towards_axis = FreeCAD.Vector(self.AXIS.x - foot.x, self.AXIS.y - foot.y, 0.0)
        self.assertAlmostEqual(towards_axis.Length, 2.0, places=4)
        self._assert_vector(direction, towards_axis.normalize())

    def test_a_positive_offset_narrows_the_hole(self):
        feature = self._start("PartDesign_OffsetFace", self.hole, self.wall)
        self._find_widget("offsetFaceDistance").setProperty("rawValue", 0.5)
        self._process_events(100)
        self.assertTrue(feature.isValid(), feature.getStatusString())
        expected = 600.0 - math.pi * 1.5 * 1.5 * 10.0
        self.assertAlmostEqual(feature.Shape.Volume, expected, places=2)


class TestMoveFaceArrow(FaceToolCase):
    FIELDS = ("moveFaceAlongX", "moveFaceAlongY", "moveFaceAlongZ", "moveFaceAlongNormal")

    def _fields(self):
        return [self._find_widget(name) for name in self.FIELDS]

    def test_the_panel_keeps_its_xyz_fields_and_gains_one_along_the_normal(self):
        self._start("PartDesign_MoveFace", self.pad, self._top_face())
        for name, field in zip(self.FIELDS, self._fields()):
            self.assertIsNotNone(field, f"no {name} field")

    def test_the_arrow_stands_on_the_face_along_its_normal(self):
        feature = self._start("PartDesign_MoveFace", self.pad, self._top_face())
        foot, direction = self._arrow()
        self._assert_vector(foot, self.TOP_CENTRE)
        self._assert_vector(direction, FreeCAD.Vector(0.0, 0.0, 1.0))
        self.assertAlmostEqual(self._fields()[3].property("rawValue"), feature.Direction.z)

    def test_the_normal_field_moves_the_face_along_its_normal(self):
        feature = self._start("PartDesign_MoveFace", self.pad, self._top_face())
        along_x, along_y, along_z, normal = self._fields()
        along_x.setProperty("rawValue", 2.0)
        self._process_events(100)
        normal.setProperty("rawValue", 3.0)
        self._process_events(100)
        self._assert_vector(feature.Direction, FreeCAD.Vector(2.0, 0.0, 3.0))
        self.assertAlmostEqual(along_z.property("rawValue"), 3.0)
        # The sideways travel carries the arrow's foot with it.
        foot, _ = self._arrow()
        self._assert_vector(foot, self.TOP_CENTRE + FreeCAD.Vector(2.0, 0.0, 0.0))

    def test_dragging_the_arrow_moves_the_face_along_its_normal(self):
        feature = self._start("PartDesign_MoveFace", self.pad, self._top_face())
        before = feature.Direction.z
        self._drag_arrow_by(before, 4.0)
        self.assertGreater(feature.Direction.z, before + 2.0)
        self.assertAlmostEqual(feature.Direction.x, 0.0)
        self.assertAlmostEqual(feature.Direction.y, 0.0)
        self.assertAlmostEqual(self._fields()[2].property("rawValue"), feature.Direction.z)

    def test_a_curved_face_is_still_refused(self):
        hole = self.doc.addObject("PartDesign::SubtractiveCylinder", "Hole")
        hole.Radius = 2.0
        hole.Placement.Base = FreeCAD.Vector(5.0, 3.0, 0.0)
        self.body.addObject(hole)
        self.doc.recompute()
        wall = self._face_where(hole.Shape, lambda face: isinstance(face.Surface, Part.Cylinder))
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, hole.Name, wall)
        before = len(self.doc.Objects)
        with ModalCloser() as closer:
            FreeCADGui.runCommand("PartDesign_MoveFace")
            self._process_events(200)
        self.assertEqual(closer.closed, ["QMessageBox"])
        self.assertEqual(len(self.doc.Objects), before)
