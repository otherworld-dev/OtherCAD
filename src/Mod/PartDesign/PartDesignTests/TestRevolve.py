# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
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

import math
import unittest

import FreeCAD
import Part
import Sketcher


class TestRevolve(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestRevolve")

    def testRevolveFace(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.Revolution = self.Doc.addObject("PartDesign::Revolution", "Revolution")
        self.Revolution.Profile = (self.Box, ["Face6"])
        self.Revolution.ReferenceAxis = (self.Doc.Y_Axis, [""])
        self.Revolution.Angle = 180.0
        self.Revolution.Reversed = 1
        self.Body.addObject(self.Revolution)
        self.Doc.recompute()
        # depending on if refinement is done we expect 8 or 10 faces
        self.assertIn(len(self.Revolution.Shape.Faces), (8, 10))

    def testGrooveFace(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Box = self.Doc.addObject("PartDesign::AdditiveBox", "Box")
        self.Body.addObject(self.Box)
        self.Box.Length = 10.00
        self.Box.Width = 10.00
        self.Box.Height = 10.00
        self.Doc.recompute()
        self.Groove = self.Doc.addObject("PartDesign::Groove", "Groove")
        self.Groove.Profile = (self.Box, ["Face6"])
        self.Groove.ReferenceAxis = (self.Doc.X_Axis, [""])
        self.Groove.Angle = 180.0
        self.Groove.Reversed = 1
        self.Body.addObject(self.Groove)
        self.Doc.recompute()
        self.assertEqual(len(self.Groove.Shape.Faces), 5)

    def testRevolutionStartOffsetAndReference(self):
        profile = self.Doc.addObject("Sketcher::SketchObject", "Profile")
        points = [
            FreeCAD.Vector(2, 0),
            FreeCAD.Vector(3, 0),
            FreeCAD.Vector(3, 1),
            FreeCAD.Vector(2, 1),
        ]
        for start, end in zip(points, points[1:] + points[:1]):
            profile.addGeometry(Part.LineSegment(start, end), False)

        axis = self.Doc.addObject("Part::Feature", "Axis")
        axis.Shape = Part.makeLine(FreeCAD.Vector(0, -1, 0), FreeCAD.Vector(0, 2, 0))

        revolution = self.Doc.addObject("PartDesign::Revolution", "OffsetRevolution")
        revolution.Profile = profile
        revolution.ReferenceAxis = (axis, ["Edge1"])
        revolution.Angle = 30
        revolution.StartType = "Offset"
        revolution.StartOffset = 105
        self.Doc.recompute()

        direct_bounds = revolution.AddSubShape.BoundBox
        direct_values = (
            direct_bounds.XMin,
            direct_bounds.XMax,
            direct_bounds.YMin,
            direct_bounds.YMax,
            direct_bounds.ZMin,
            direct_bounds.ZMax,
        )
        self.assertLess(direct_bounds.XMax, -0.5)
        self.assertLess(direct_bounds.ZMax, -1.4)

        reference = self.Doc.addObject("Part::Feature", "StartReference")
        reference.Shape = Part.Face(
            Part.makePolygon(
                [
                    FreeCAD.Vector(0, -1, -1),
                    FreeCAD.Vector(0, 2, -1),
                    FreeCAD.Vector(0, 2, -4),
                    FreeCAD.Vector(0, -1, -4),
                    FreeCAD.Vector(0, -1, -1),
                ]
            )
        )
        revolution.StartReference = (reference, ["Face1"])
        revolution.StartType = "Reference"
        revolution.StartOffset = 15
        self.Doc.recompute()

        reference_bounds = revolution.AddSubShape.BoundBox
        reference_values = (
            reference_bounds.XMin,
            reference_bounds.XMax,
            reference_bounds.YMin,
            reference_bounds.YMax,
            reference_bounds.ZMin,
            reference_bounds.ZMax,
        )
        for actual, expected in zip(reference_values, direct_values):
            self.assertAlmostEqual(actual, expected)

    # -- several profiles in one feature (#752) ---------------------------

    def _squareSketch(self, body, name, plane, x, y, size):
        support = [f for f in body.Origin.OriginFeatures if f.Role == plane][0]
        sketch = body.newObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (support, [""])
        sketch.MapMode = "FlatFace"
        corners = [
            FreeCAD.Vector(x, y, 0),
            FreeCAD.Vector(x + size, y, 0),
            FreeCAD.Vector(x + size, y + size, 0),
            FreeCAD.Vector(x, y + size, 0),
        ]
        for start, end in zip(corners, corners[1:] + corners[:1]):
            sketch.addGeometry(Part.LineSegment(start, end), False)
        return sketch

    def _zAxis(self, body):
        return [f for f in body.Origin.OriginFeatures if f.Role == "Z_Axis"][0]

    def testRevolutionWithExtraProfiles(self):
        """Profiles on two planes through the axis are revolved about it together."""
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squareSketch(body, "First", "XZ_Plane", 10, 0, 10)
        second = self._squareSketch(body, "Second", "YZ_Plane", 30, 0, 10)
        self.Doc.recompute()
        revolution = body.newObject("PartDesign::Revolution", "Revolution")
        revolution.Profile = first
        revolution.ExtraProfiles = [(second, "")]
        revolution.ReferenceAxis = (self._zAxis(body), [""])
        revolution.Angle = 360
        self.Doc.recompute()

        self.assertTrue(revolution.isValid(), revolution.getStatusString())
        expected = math.pi * ((20**2 - 10**2) + (40**2 - 30**2)) * 10
        self.assertAlmostEqual(revolution.Shape.Volume, expected, places=4)

    def testGrooveWithExtraProfiles(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        cylinder = body.newObject("PartDesign::AdditiveCylinder", "Cylinder")
        cylinder.Radius = 50
        cylinder.Height = 20
        first = self._squareSketch(body, "First", "XZ_Plane", 40, 5, 5)
        second = self._squareSketch(body, "Second", "YZ_Plane", 20, 5, 5)
        self.Doc.recompute()
        groove = body.newObject("PartDesign::Groove", "Groove")
        groove.Profile = first
        groove.ExtraProfiles = [(second, "")]
        groove.ReferenceAxis = (self._zAxis(body), [""])
        groove.Angle = 360
        self.Doc.recompute()

        self.assertTrue(groove.isValid(), groove.getStatusString())
        removed = math.pi * ((45**2 - 40**2) + (25**2 - 20**2)) * 5
        self.assertAlmostEqual(groove.Shape.Volume, math.pi * 50**2 * 20 - removed, places=4)

    def testRevolveRefusesAnExtraProfileFacingAlongTheAxis(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squareSketch(body, "First", "XZ_Plane", 10, 0, 10)
        second = self._squareSketch(body, "Second", "XY_Plane", 30, 0, 10)
        self.Doc.recompute()
        revolution = body.newObject("PartDesign::Revolution", "Revolution")
        revolution.Profile = first
        revolution.ExtraProfiles = [(second, "")]
        revolution.ReferenceAxis = (self._zAxis(body), [""])
        revolution.Angle = 360
        self.Doc.recompute()

        self.assertFalse(revolution.isValid())
        self.assertIn("revolve axis", revolution.getStatusString())

    # -- every operation in the up-to types (#750) ------------------------
    #
    # A square at x 10..20, z 0..10 on the XZ plane revolves about Z towards +Y. Up to x = -5
    # it fills the quarter annulus with y >= 0 and x >= -5.

    WALL = 10 * 25 * 20  # x -5..5: the revolution runs through it
    BLOCK = 30 * 30 * 20  # x -5..25, y -5..25: the profile starts inside it

    def _upTo(self, kind, method, operation, solid="Wall"):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", solid)
        box.Height = 20
        if solid == "Wall":
            box.Length = 10
            box.Width = 25
            box.Placement.Base = FreeCAD.Vector(-5, 0, -5)
        else:
            box.Length = 30
            box.Width = 30
            box.Placement.Base = FreeCAD.Vector(-5, -5, -5)
        profile = self._squareSketch(body, "Profile", "XZ_Plane", 10, 0, 10)
        self.Doc.recompute()

        feature = body.newObject("PartDesign::" + kind, kind)
        feature.Profile = profile
        feature.ReferenceAxis = (self._zAxis(body), [""])
        feature.Type = method
        if method == "UpToFace":
            feature.UpToFace = (box, [self._faceAtXMinus5(box)])
        feature.Operation = operation
        self.Doc.recompute()
        return feature

    def _faceAtXMinus5(self, obj):
        for i, face in enumerate(obj.Shape.Faces, 1):
            if abs(face.CenterOfMass.x + 5) < 1e-6:
                return f"Face{i}"
        self.fail("no face at x = -5")

    def _volumes(self):
        """The revolution up to x = -5, and the part of it inside the wall."""
        annulus = Part.makeCylinder(20, 10).cut(Part.makeCylinder(10, 10))
        whole = annulus.common(Part.makeBox(30, 25, 10, FreeCAD.Vector(-5, 0, 0))).Volume
        inWall = annulus.common(Part.makeBox(10, 25, 10, FreeCAD.Vector(-5, 0, 0))).Volume
        return whole, inWall

    def _assertSolid(self, feature, volume):
        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertTrue(feature.Shape.isValid())
        self.assertEqual(len(feature.Shape.Solids), 1)
        self.assertAlmostEqual(feature.Shape.Volume, volume, places=3)

    def testRevolveUpToFaceJoinsTheWall(self):
        whole, inWall = self._volumes()
        feature = self._upTo("Revolution", "UpToFace", "Join")
        self._assertSolid(feature, self.WALL + whole - inWall)

    def testRevolveUpToFaceCutsTheWall(self):
        _, inWall = self._volumes()
        for kind in ("Revolution", "Groove"):
            with self.subTest(kind=kind):
                feature = self._upTo(kind, "UpToFace", "Cut")
                self._assertSolid(feature, self.WALL - inWall)

    def testRevolveUpToFaceIntersectsTheWall(self):
        _, inWall = self._volumes()
        for kind in ("Revolution", "Groove"):
            with self.subTest(kind=kind):
                feature = self._upTo(kind, "UpToFace", "Intersect")
                self._assertSolid(feature, inWall)

    def testRevolveUpToFaceNewBodyIsTheWholeRevolution(self):
        whole, _ = self._volumes()
        feature = self._upTo("Revolution", "UpToFace", "NewBody")
        # The body keeps its wall until the feature moves into a body of its own
        self._assertSolid(feature, self.WALL)
        self.assertAlmostEqual(feature.AddSubShape.Volume, whole, places=3)

    def testRevolveUpToFaceNewBodyInABodyOfItsOwn(self):
        import PartDesignNewBody

        whole, _ = self._volumes()
        feature = self._upTo("Revolution", "UpToFace", "NewBody")
        newBody = PartDesignNewBody.moveToNewBody(feature)

        self.assertIsNotNone(newBody)
        self.assertIsNone(feature.BaseFeature)
        self._assertSolid(feature, whole)
        self.assertAlmostEqual(newBody.Shape.Volume, whole, places=3)

    def testRevolveUpToFaceWithoutABase(self):
        whole, _ = self._volumes()
        wall = self.Doc.addObject("Part::Box", "Wall")
        wall.Length = 10
        wall.Width = 25
        wall.Height = 20
        wall.Placement.Base = FreeCAD.Vector(-5, 0, -5)
        self.Doc.recompute()
        body = self.Doc.addObject("PartDesign::Body", "Body")
        binder = body.newObject("PartDesign::SubShapeBinder", "WallFace")
        binder.Support = [(wall, [self._faceAtXMinus5(wall)])]
        profile = self._squareSketch(body, "Profile", "XZ_Plane", 10, 0, 10)
        self.Doc.recompute()

        feature = body.newObject("PartDesign::Revolution", "Revolution")
        feature.Profile = profile
        feature.ReferenceAxis = (self._zAxis(body), [""])
        feature.Type = "UpToFace"
        feature.UpToFace = (binder, ["Face1"])
        self.Doc.recompute()

        self._assertSolid(feature, whole)

    def testRevolveUpToFirstStopsAtTheNearSideOfTheWall(self):
        whole, inWall = self._volumes()
        feature = self._upTo("Revolution", "UpToFirst", "NewBody")
        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertAlmostEqual(feature.AddSubShape.Volume, whole - inWall, places=3)

    def testRevolveUpToFirstCutsTheBlock(self):
        whole, _ = self._volumes()
        feature = self._upTo("Revolution", "UpToFirst", "Cut", solid="Block")
        self._assertSolid(feature, self.BLOCK - whole)

    def testRevolveUpToFirstIntersectsTheBlock(self):
        whole, _ = self._volumes()
        feature = self._upTo("Revolution", "UpToFirst", "Intersect", solid="Block")
        self._assertSolid(feature, whole)

    def testRevolveUpToFirstNewBodyIsTheWholeRevolution(self):
        whole, _ = self._volumes()
        feature = self._upTo("Revolution", "UpToFirst", "NewBody", solid="Block")
        self._assertSolid(feature, self.BLOCK)
        self.assertAlmostEqual(feature.AddSubShape.Volume, whole, places=3)

    def testRevolveUpToFaceIntersectsWithExtraProfiles(self):
        feature = self._upTo("Revolution", "UpToFace", "Intersect")
        body = feature.getParentGeoFeatureGroup()
        extra = self._squareSketch(body, "Extra", "XZ_Plane", 10, 11, 3)
        feature.ExtraProfiles = [(extra, "")]
        self.Doc.recompute()

        _, inWall = self._volumes()
        annulus = Part.makeCylinder(13, 3, FreeCAD.Vector(0, 0, 11)).cut(
            Part.makeCylinder(10, 3, FreeCAD.Vector(0, 0, 11))
        )
        extraInWall = annulus.common(Part.makeBox(10, 25, 20, FreeCAD.Vector(-5, 0, -5))).Volume
        self.assertTrue(feature.isValid(), feature.getStatusString())
        self.assertTrue(feature.Shape.isValid())
        self.assertAlmostEqual(feature.Shape.Volume, inWall + extraInWall, places=3)

    def tearDown(self):
        # closing doc
        FreeCAD.closeDocument("PartDesignTestRevolve")
        # print ("omit closing document for debugging")
