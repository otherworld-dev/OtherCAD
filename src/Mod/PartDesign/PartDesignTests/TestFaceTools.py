# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2026 OtherCAD contributors                               *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""Offset Face and Move Face on flat and curved faces.

Offset Face pushes a face along its own normal. A flat face sweeps along one direction,
but a curved one has a different normal everywhere, so Offset Face grows or shrinks it
by a constant distance instead (a cylinder changes radius). Move Face carries a face
along one direction, which only means something for a flat face, so it still refuses
curved ones and says why.
"""

import math
import unittest

import FreeCAD
import Part


def face_name(shape, surface_type):
    """The name of the first face of shape whose surface is surface_type."""
    for index, face in enumerate(shape.Faces):
        if isinstance(face.Surface, surface_type):
            return "Face%d" % (index + 1)
    raise AssertionError("no %s face" % surface_type.__name__)


def top_face_name(shape):
    """The name of the flat face highest up Z."""
    best = max(
        (face.CenterOfMass.z, index)
        for index, face in enumerate(shape.Faces)
        if isinstance(face.Surface, Part.Plane)
    )
    return "Face%d" % (best[1] + 1)


class TestFaceTools(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("PartDesignTestFaceTools")
        self.body = self.doc.addObject("PartDesign::Body", "Body")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _cylinder(self, radius=5.0, height=10.0):
        cylinder = self.doc.addObject("PartDesign::AdditiveCylinder", "Cylinder")
        cylinder.Radius = radius
        cylinder.Height = height
        self.body.addObject(cylinder)
        self.doc.recompute()
        return cylinder

    def _offset(self, base, face, distance):
        feature = self.doc.addObject("PartDesign::OffsetFace", "OffsetFace")
        feature.Base = (base, [face])
        feature.Offset = distance
        self.body.addObject(feature)
        self.doc.recompute()
        return feature

    def test_offsetting_a_flat_face_sweeps_it_along_its_normal(self):
        box = self.doc.addObject("PartDesign::AdditiveBox", "Box")
        self.body.addObject(box)
        self.doc.recompute()

        feature = self._offset(box, top_face_name(box.Shape), 2.0)

        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.Shape.Volume, 1200.0, places=3)

    def test_offsetting_a_cylinder_outwards_grows_its_radius(self):
        cylinder = self._cylinder()

        feature = self._offset(cylinder, face_name(cylinder.Shape, Part.Cylinder), 1.0)

        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.Shape.Volume, math.pi * 36.0 * 10.0, places=2)
        self.assertEqual(len(feature.Shape.Solids), 1)

    def test_offsetting_a_cylinder_inwards_shrinks_its_radius(self):
        cylinder = self._cylinder()

        feature = self._offset(cylinder, face_name(cylinder.Shape, Part.Cylinder), -1.0)

        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.Shape.Volume, math.pi * 16.0 * 10.0, places=2)

    def test_offsetting_a_hole_wall_outwards_closes_the_hole_up(self):
        box = self.doc.addObject("PartDesign::AdditiveBox", "Box")
        box.Length = 20.0
        box.Width = 20.0
        self.body.addObject(box)
        hole = self.doc.addObject("PartDesign::SubtractiveCylinder", "Hole")
        hole.Radius = 3.0
        hole.Height = 10.0
        hole.Placement.Base = FreeCAD.Vector(10.0, 10.0, 0.0)
        self.body.addObject(hole)
        self.doc.recompute()

        # The wall's outward normal points into the hole, so a positive offset
        # adds material there and the hole narrows from radius 3 to 2.
        feature = self._offset(hole, face_name(hole.Shape, Part.Cylinder), 1.0)

        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.Shape.Volume, 4000.0 - math.pi * 4.0 * 10.0, places=2)

    def test_moving_a_curved_face_is_refused_with_a_reason(self):
        cylinder = self._cylinder()

        feature = self.doc.addObject("PartDesign::MoveFace", "MoveFace")
        feature.Base = (cylinder, [face_name(cylinder.Shape, Part.Cylinder)])
        feature.Direction = FreeCAD.Vector(1.0, 0.0, 0.0)
        self.body.addObject(feature)
        self.doc.recompute()

        self.assertFalse(feature.isValid())
        self.assertIn("flat", feature.getStatusString())

    def test_a_face_with_no_edges_of_its_own_is_refused_with_a_reason(self):
        sphere = self.doc.addObject("PartDesign::AdditiveSphere", "Sphere")
        self.body.addObject(sphere)
        self.doc.recompute()

        feature = self._offset(sphere, "Face1", 1.0)

        self.assertFalse(feature.isValid())
        self.assertIn("cannot be offset", feature.getStatusString())
