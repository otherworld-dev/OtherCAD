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

"""GUI tests for Move (M), Fusion's in-view Move gizmo.

Move puts three arrows and three rotation handles on the selected body, with their
values in boxes in the view and in the panel. The body follows as they change, OK
keeps the move as one undo step and Cancel puts the body back. With a face picked,
Move moves that face instead, through Move Face.

To run tests:
    FreeCAD -t TestMoveGizmo
"""

import FreeCAD
import FreeCADGui
from PySide import QtCore

import TestFaceToolArrows as faces
import TestPartDesignLetters as letters

ModalCloser = letters.TestPartDesignLetters._ModalCloser

DISTANCES = ("moveDistanceX", "moveDistanceY", "moveDistanceZ")
ANGLES = ("moveAngleX", "moveAngleY", "moveAngleZ")
AXES = (FreeCAD.Vector(1, 0, 0), FreeCAD.Vector(0, 1, 0), FreeCAD.Vector(0, 0, 1))


class TestMoveGizmo(faces.FaceToolCase):
    """The 10 x 6 x 10 Pad of the gizmo tests, in its body, moved with M."""

    # The middle of the Pad's bounding box, where the gizmo stands.
    CENTRE = FreeCAD.Vector(5.0, 3.0, 5.0)

    def setUp(self):
        super().setUp()
        self.undo_before = self.doc.UndoCount

    # -- helpers ---------------------------------------------------------

    def _open_move(self, *selection):
        FreeCADGui.Selection.clearSelection()
        for args in selection or ((self.doc.Name, self.body.Name),):
            FreeCADGui.Selection.addSelection(*args)
        self.assertTrue(FreeCADGui.Command.get("Std_Move").isActive(), "Move is greyed out")
        with ModalCloser() as closer:
            FreeCADGui.runCommand("Std_Move")
            self._process_events(200)
        self.assertEqual(closer.closed, [])
        self._refresh_view_widgets()
        self._settle_view()

    def _field(self, name):
        field = self._find_widget(name)
        self.assertIsNotNone(field, f"no {name} field in the Move panel")
        return field

    def _set(self, name, value):
        self._field(name).setProperty("rawValue", float(value))
        self._process_events(100)

    def _containers(self, type_name):
        from pivy import coin

        search = coin.SoSearchAction()
        search.setType(coin.SoType.fromName(type_name))
        search.setInterest(coin.SoSearchAction.ALL)
        search.setSearchingAll(True)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        paths = search.getPaths()
        # The nodes, not the paths: the paths go with the search when it is collected.
        return [
            paths[index].getTail()
            for index in range(paths.getLength())
            if self._path_is_on(paths[index])
        ]

    def _arrow(self):
        """The X arrow, the one FaceToolCase._drag_arrow_by drags."""

        from pivy import coin

        for node in self._containers("SoLinearDraggerContainer"):
            foot = coin.cast(node.getField("translation"), "SoSFVec3f").getValue()
            direction = self._direction_of(node)
            if direction.isEqual(AXES[0], 1e-4):
                return FreeCAD.Vector(*foot.getValue()), direction
        self.fail("no arrow along X")

    @staticmethod
    def _direction_of(node):
        from pivy import coin

        rotation = coin.cast(node.getField("rotation"), "SoSFRotation").getValue()
        direction = rotation.multVec(coin.SbVec3f(0.0, 1.0, 0.0))
        return FreeCAD.Vector(*direction.getValue()).normalize()

    def _grip(self, start, end):
        """Pixels between start and end where the X arrow, and no other handle, is hit.

        All three arrows start at the middle of the body, so a press near there could
        take any of them.
        """

        from pivy import coin

        manager = self.viewer.getSoRenderManager()
        first = self._pixels(start)
        last = self._pixels(end)
        for step in range(41):
            along = step / 40.0
            pixels = (
                first[0] + (last[0] - first[0]) * along,
                first[1] + (last[1] - first[1]) * along,
            )
            pick = coin.SoRayPickAction(manager.getViewportRegion())
            pick.setPoint(coin.SbVec2s(int(pixels[0]), int(pixels[1])))
            pick.setRadius(3)
            pick.setPickAll(True)
            pick.apply(manager.getSceneGraph())
            picked = pick.getPickedPointList()
            handles = set()
            for index in range(picked.getLength()):
                path = picked[index].getPath()
                for depth in range(path.getLength()):
                    node = path.getNode(depth)
                    name = node.getTypeId().getName().getString()
                    if name == "SoLinearDraggerContainer":
                        handles.add(tuple(round(c, 3) for c in self._direction_of(node)))
                    elif name == "SoRotationDraggerContainer":
                        handles.add("rotation")
            if handles == {(1.0, 0.0, 0.0)}:
                return pixels
        self.fail("the X arrow is not on its own under any of the points tried")

    # -- tests -----------------------------------------------------------

    def test_m_is_the_move_command(self):
        self.assertEqual(FreeCADGui.Command.get("Std_Move").getShortcut(), "M")

    def test_move_shows_three_arrows_and_three_rotation_handles(self):
        self._open_move()
        self.assertEqual(len(self._containers("SoLinearDraggerContainer")), 3)
        self.assertEqual(len(self._containers("SoRotationDraggerContainer")), 3)
        for name in DISTANCES + ANGLES:
            self._field(name)

    def test_the_arrows_stand_at_the_middle_of_the_body(self):
        self._open_move()
        foot, _ = self._arrow()
        self._assert_vector(foot, self.CENTRE)

    def test_the_values_show_in_boxes_in_the_view(self):
        self._open_move()
        self._wait_for_distance_boxes(3)

    def test_a_distance_moves_the_body_as_it_is_typed(self):
        self._open_move()
        self._set("moveDistanceX", 5.0)
        self._set("moveDistanceZ", -2.0)
        self._assert_vector(self.body.Placement.Base, FreeCAD.Vector(5.0, 0.0, -2.0))
        # The other arrows follow the body; the X arrow's own value is its tip.
        foot, _ = self._arrow()
        self._assert_vector(foot, self.CENTRE + FreeCAD.Vector(0.0, 0.0, -2.0))

    def test_an_angle_turns_the_body_about_its_middle(self):
        self._open_move()
        self._set("moveAngleZ", 90.0)
        moved = self.body.Placement.multVec(self.CENTRE)
        self._assert_vector(moved, self.CENTRE)
        self.assertAlmostEqual(self.body.Placement.Rotation.Angle, 1.5707963, places=5)

    def test_ok_keeps_the_move_as_one_undo_step(self):
        self._open_move()
        self._set("moveDistanceX", 5.0)
        self._set("moveDistanceY", 1.0)
        self._set("moveAngleX", 30.0)
        FreeCADGui.Control.activeTaskDialog().accept()
        self._process_events(200)
        self.assertFalse(FreeCADGui.Control.activeDialog())
        self.assertAlmostEqual(self.body.Placement.Base.x, 5.0)
        self.assertEqual(self.doc.UndoCount, self.undo_before + 1)
        self.doc.undo()
        self._process_events()
        self.assertTrue(self.body.Placement.isSame(FreeCAD.Placement(), 1e-9))

    def test_enter_in_a_value_box_finishes_the_move(self):
        self._open_move()
        boxes = self._wait_for_distance_boxes(3)
        # The X distance's box opens with the keyboard, as the first box of a feature does.
        self.assertTrue(
            self._wait(lambda: any(b.hasFocus() for b in boxes)), "no box has the keyboard"
        )
        box = next(b for b in boxes if b.hasFocus())
        self._select_all(box)
        self._type(box, "4")
        self._press(box, QtCore.Qt.Key_Return)
        self._process_events(200)
        self.assertFalse(FreeCADGui.Control.activeDialog())
        self.assertAlmostEqual(self.body.Placement.Base.x, 4.0)
        self.assertEqual(self.doc.UndoCount, self.undo_before + 1)

    def test_cancel_puts_the_body_back(self):
        self._open_move()
        self._set("moveDistanceX", 5.0)
        self._set("moveAngleY", 45.0)
        FreeCADGui.Control.activeTaskDialog().reject()
        self._process_events(200)
        self.assertFalse(FreeCADGui.Control.activeDialog())
        self.assertTrue(self.body.Placement.isSame(FreeCAD.Placement(), 1e-9))
        self.assertEqual(self.doc.UndoCount, self.undo_before)

    def test_dragging_the_x_arrow_moves_the_body_along_x(self):
        self._open_move()
        self._drag_arrow_by(0.0, 4.0)
        moved = self.body.Placement.Base
        self.assertGreater(moved.x, 2.0)
        self.assertAlmostEqual(moved.y, 0.0)
        self.assertAlmostEqual(moved.z, 0.0)
        self.assertAlmostEqual(self._field("moveDistanceX").property("rawValue"), moved.x)

    def test_a_feature_of_a_body_moves_the_whole_body(self):
        self._open_move((self.doc.Name, self.pad.Name))
        self._set("moveDistanceY", 3.0)
        self._assert_vector(self.body.Placement.Base, FreeCAD.Vector(0.0, 3.0, 0.0))

    def test_with_a_face_picked_move_moves_the_face(self):
        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(self.doc.Name, self.pad.Name, self._top_face())
        self.assertTrue(FreeCADGui.Command.get("Std_Move").isActive(), "Move is greyed out")
        before = set(obj.Name for obj in self.doc.Objects)
        with ModalCloser() as closer:
            FreeCADGui.runCommand("Std_Move")
            self._process_events(200)
        self.assertEqual(closer.closed, [])
        added = [obj for obj in self.doc.Objects if obj.Name not in before]
        self.assertEqual([obj.TypeId for obj in added], ["PartDesign::MoveFace"])
        self.assertIsNotNone(self._find_widget("moveFaceAlongNormal"))
