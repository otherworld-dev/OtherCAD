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

import unittest

import FreeCAD
import Part
from FreeCAD import Base
import TestSketcherApp


class TestPad(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestPad")

    def testBoxCase(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchOnBasePlane(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.PadSketch.AttachmentSupport = (self.Doc.XY_Plane, [""])
        self.PadSketch.MapMode = "FlatFace"
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Body.addObject(self.Pad)
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchOnDatumPlane(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.DatumPlane = self.Doc.addObject("PartDesign::Plane", "DatumPlane")
        self.DatumPlane.AttachmentSupport = (self.Doc.XY_Plane, [""])
        self.DatumPlane.MapMode = "FlatFace"
        self.Body.addObject(self.DatumPlane)
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.PadSketch.AttachmentSupport = (self.DatumPlane, [""])
        self.PadSketch.MapMode = "FlatFace"
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateSlotPlateSet(self.PadSketch)
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Body.addObject(self.Pad)
        self.Doc.recompute()
        self.assertEqual(len(self.Pad.Shape.Faces), 6)

    def testSketchAttachmentDoesNotImportExternalBody(self):
        source_body = self.Doc.addObject("PartDesign::Body", "SourceBody")
        source_box = source_body.newObject("PartDesign::AdditiveBox", "SourceBox")
        source_box.Length = 1
        source_box.Width = 1
        source_box.Height = 1

        target_body = self.Doc.addObject("PartDesign::Body", "TargetBody")
        sketch = target_body.newObject("Sketcher::SketchObject", "SketchPad")
        sketch.AttachmentSupport = (source_body, [""])
        sketch.MapMode = "ObjectXY"
        TestSketcherApp.CreateRectangleSketch(sketch, (2, 0), (1, 1))

        pad = target_body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 1
        self.Doc.recompute()

        self.assertIsNone(pad.BaseFeature)
        self.assertEqual(len(pad.Shape.Solids), 1)
        self.assertAlmostEqual(pad.Shape.Volume, 1)

    def testStartOffsetAndReference(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.StartType = "Offset"
        self.Pad.StartOffset = 2
        self.Pad.Length = 3
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 2.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 5.0)

        reference = self.Doc.addObject("Part::Feature", "Reference")
        outer = Part.makeCylinder(2, 1, Base.Vector(0, 0, 10))
        inner = Part.makeCylinder(1, 1, Base.Vector(0, 0, 10))
        reference.Shape = outer.cut(inner)
        top_face = max(
            range(1, len(reference.Shape.Faces) + 1),
            key=lambda index: reference.Shape.Faces[index - 1].CenterOfMass.z,
        )
        self.Pad.StartReference = (reference, [f"Face{top_face}"])
        self.Pad.StartType = "Reference"
        self.Pad.StartOffset = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 13.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 16.0)

    def testStartReferenceInternalSketchFace(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        reference = self.Doc.addObject("Sketcher::SketchObject", "Reference")
        reference.MakeInternals = True
        reference.Placement.Base = Base.Vector(0, 0, 10)
        TestSketcherApp.CreateRectangleSketch(reference, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 3
        self.Pad.StartReference = (reference, ["InternalFace1"])
        self.Pad.StartType = "Reference"
        self.Pad.StartOffset = 2
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 12.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 15.0)

    def testStartOffsetForTwoSidedAndSymmetricPad(self):
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()

        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.PadSketch
        self.Pad.StartType = "Offset"
        self.Pad.StartOffset = 2
        self.Pad.SideType = "Two sides"
        self.Pad.Length = 1
        self.Pad.Length2 = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 1.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 3.0)

        self.Pad.SideType = "Symmetric"
        self.Pad.Length = 4
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMin, 0.0)
        self.assertAlmostEqual(self.Pad.Shape.BoundBox.ZMax, 4.0)

    def testPadToFirstCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 2
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.0)

    def testPadtoLastCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0.5, 1), (0.5, 2))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 1
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 3.0)

    def testPadToFaceCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to face on first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 3
        self.Pad1.UpToFace = (self.Pad, ["Face3"])
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.0)

    def testPadTwoDimensionsCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to face on first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.SideType = 1
        self.Pad1.Length = 1.0
        self.Pad1.Length2 = 2.0
        self.Pad1.Reversed = 1
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 4.0)

    def testPadToConcaveCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make a half revolution
        self.RevolutionSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.RevolutionSketch)
        TestSketcherApp.CreateRectangleSketch(self.RevolutionSketch, (9, 0), (10, 5))
        self.Doc.recompute()
        self.Revolution = self.Doc.addObject("PartDesign::Revolution", "Revolution")
        self.Body.addObject(self.Revolution)
        self.Revolution.Profile = self.RevolutionSketch
        self.Revolution.ReferenceAxis = (self.RevolutionSketch, ["V_Axis"])
        self.Revolution.Angle = 180
        self.Doc.recompute()
        # Make a sketch and pad to first
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 0), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Type = 2
        self.Pad.Reversed = True
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.Volume, 2208.0963, places=4)

    def testPadToShapeCase(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Length = 1
        self.Doc.recompute()
        # Make second pad on different plane and pad to first
        self.PadSketch1 = self.Doc.addObject("Sketcher::SketchObject", "SketchPad1")
        self.Body.addObject(self.PadSketch1)
        self.PadSketch1.MapMode = "FlatFace"
        self.PadSketch1.AttachmentSupport = (self.Doc.XZ_Plane, [""])
        self.PadSketch1.AttachmentOffset.Rotation.Axis = Base.Vector(0, 1, 0)
        self.PadSketch1.AttachmentOffset.Rotation.Angle = 0.436332  # 25°
        self.PadSketch1.AttachmentOffset.Base.z = 1
        self.Doc.recompute()
        TestSketcherApp.CreateRectangleSketch(self.PadSketch1, (1, 0), (1, 1))
        self.Doc.recompute()
        self.Pad1 = self.Doc.addObject("PartDesign::Pad", "Pad1")
        self.Body.addObject(self.Pad1)
        self.Pad1.Profile = self.PadSketch1
        self.Pad1.Type = 5
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad1.Shape.Volume, 2.58787, places=4)

    def testPadToPlaneCustomDir(self):
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        # Make first offset cube Pad
        self.PadSketch = self.Doc.addObject("Sketcher::SketchObject", "SketchPad")
        self.Body.addObject(self.PadSketch)
        TestSketcherApp.CreateRectangleSketch(self.PadSketch, (0, 1), (1, 1))
        self.Doc.recompute()
        self.Pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        self.Body.addObject(self.Pad)
        self.Pad.Profile = self.PadSketch
        self.Pad.Type = 3
        self.Doc.Pad.UseCustomVector = True
        self.Doc.Pad.Direction = Base.Vector(0, 1, 1)
        self.Pad.UpToFace = (self.Doc.XZ_Plane, [""])
        self.Doc.recompute()
        self.assertAlmostEqual(self.Pad.Shape.Volume, 1.5)

    # -- several profiles in one feature (#752) ---------------------------

    def _squaresSketch(self, body, name, squares, z=0.0, size=10.0):
        """A sketch on the XY plane, lifted by z, with a square at each (x, y)."""
        xy = [f for f in body.Origin.OriginFeatures if f.Role == "XY_Plane"][0]
        sketch = body.newObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (xy, [""])
        sketch.MapMode = "FlatFace"
        sketch.AttachmentOffset = FreeCAD.Placement(Base.Vector(0, 0, z), FreeCAD.Rotation())
        sketch.MakeInternals = True
        for x, y in squares:
            corners = [
                Base.Vector(x, y, 0),
                Base.Vector(x + size, y, 0),
                Base.Vector(x + size, y + size, 0),
                Base.Vector(x, y + size, 0),
            ]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                sketch.addGeometry(Part.LineSegment(start, end), False)
        return sketch

    def testExtraProfilesFromAnotherSketch(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0)])
        second = self._squaresSketch(body, "Second", [(20, 0)], z=5)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = first
        pad.ExtraProfiles = [(second, "")]
        pad.Length = 10
        self.Doc.recompute()

        self.assertTrue(pad.isValid(), pad.getStatusString())
        self.assertAlmostEqual(pad.Shape.Volume, 2000.0, places=6)
        # Each profile is extruded from its own plane
        self.assertAlmostEqual(pad.Shape.BoundBox.ZMax, 15.0, places=6)
        self.assertIn(second, pad.OutList)
        self.assertIn(pad, second.InList)

    def testSymmetricUpToFaceMirrorsAcrossTheFirstProfile(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0)])
        second = self._squaresSketch(body, "Second", [(20, 0)], z=5)
        plane = body.newObject("PartDesign::Plane", "Limit")
        plane.AttachmentSupport = (first.AttachmentSupport[0][0], [""])
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = FreeCAD.Placement(Base.Vector(0, 0, 20), FreeCAD.Rotation())
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = first
        pad.ExtraProfiles = [(second, "")]
        pad.Type = "UpToFace"
        pad.UpToFace = (plane, [""])
        pad.SideType = "Symmetric"
        self.Doc.recompute()

        self.assertTrue(pad.isValid(), pad.getStatusString())
        # Mirrored across the first profile's plane, z = 0, not the middle of both
        self.assertAlmostEqual(pad.Shape.BoundBox.ZMax, 20.0, places=6)
        self.assertAlmostEqual(pad.Shape.BoundBox.ZMin, -20.0, places=6)

    def testExtraProfilesTakeRegionsOfAnotherSketch(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0), (20, 0)])
        second = self._squaresSketch(body, "Second", [(0, 20), (20, 20)])
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = (first, ["InternalFace1"])
        pad.ExtraProfiles = [(second, "InternalFace1"), (second, "InternalFace2")]
        pad.Length = 5
        self.Doc.recompute()

        self.assertTrue(pad.isValid(), pad.getStatusString())
        self.assertAlmostEqual(pad.Shape.Volume, 3 * 500.0, places=6)

    def testOverlappingProfilesOfTwoSketchesMerge(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0)])
        second = self._squaresSketch(body, "Second", [(5, 0)])
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = first
        pad.ExtraProfiles = [(second, "")]
        pad.Length = 10
        self.Doc.recompute()

        self.assertTrue(pad.isValid(), pad.getStatusString())
        self.assertAlmostEqual(pad.Shape.Volume, 1500.0, places=6)
        self.assertEqual(len(pad.Shape.Solids), 1)

    def testExtraProfileFromAFaceOfTheSolid(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = box.Width = box.Height = 10
        sketch = self._squaresSketch(body, "Sketch", [(20, 0)])
        self.Doc.recompute()
        top = [
            f"Face{i + 1}"
            for i, face in enumerate(box.Shape.Faces)
            if abs(face.CenterOfMass.z - 10) < 1e-7
        ][0]
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.ExtraProfiles = [(box, top)]
        pad.Length = 5
        self.Doc.recompute()

        self.assertTrue(pad.isValid(), pad.getStatusString())
        self.assertAlmostEqual(pad.Shape.Volume, 1000.0 + 500.0 + 500.0, places=6)
        self.assertAlmostEqual(pad.Shape.BoundBox.ZMax, 15.0, places=6)

    def testPocketWithExtraProfiles(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        box = body.newObject("PartDesign::AdditiveBox", "Box")
        box.Length = 40
        box.Width = 40
        box.Height = 10
        first = self._squaresSketch(body, "First", [(5, 5)], z=10, size=5)
        second = self._squaresSketch(body, "Second", [(25, 25)], z=10, size=5)
        self.Doc.recompute()
        pocket = body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = first
        pocket.ExtraProfiles = [(second, "")]
        pocket.Length = 4
        self.Doc.recompute()

        self.assertTrue(pocket.isValid(), pocket.getStatusString())
        self.assertAlmostEqual(pocket.Shape.Volume, 16000.0 - 2 * 100.0, places=6)

    def testExtraProfileOutOfPlaneIsRefused(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0)])
        xz = [f for f in body.Origin.OriginFeatures if f.Role == "XZ_Plane"][0]
        second = body.newObject("Sketcher::SketchObject", "Second")
        second.AttachmentSupport = (xz, [""])
        second.MapMode = "FlatFace"
        corners = [Base.Vector(20, 0, 0), Base.Vector(30, 0, 0), Base.Vector(30, 10, 0)]
        for start, end in zip(corners, corners[1:] + corners[:1]):
            second.addGeometry(Part.LineSegment(start, end), False)
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = first
        pad.ExtraProfiles = [(second, "")]
        self.Doc.recompute()

        self.assertFalse(pad.isValid())
        self.assertIn("parallel", pad.getStatusString())

    def testOneProfileSavesAsBefore(self):
        """ExtraProfiles stays out of the file until it is used, then reads back."""
        import os
        import tempfile
        import zipfile

        body = self.Doc.addObject("PartDesign::Body", "Body")
        first = self._squaresSketch(body, "First", [(0, 0)])
        second = self._squaresSketch(body, "Second", [(20, 0)])
        self.Doc.recompute()
        pad = body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = first
        pad.Length = 10
        self.Doc.recompute()
        self.assertIn("Hidden", pad.getPropertyStatus("ExtraProfiles"))

        def documentXml(path):
            with zipfile.ZipFile(path) as archive:
                return archive.read("Document.xml").decode("utf-8")

        path = os.path.join(tempfile.mkdtemp(), "MultiProfile.FCStd")
        self.Doc.saveAs(path)
        self.assertNotIn('name="ExtraProfiles"', documentXml(path))

        pad.ExtraProfiles = [(second, "")]
        self.Doc.recompute()
        self.assertNotIn("Hidden", pad.getPropertyStatus("ExtraProfiles"))
        self.Doc.save()
        self.assertIn('name="ExtraProfiles"', documentXml(path))

        # Emptied again, it leaves the file again
        pad.ExtraProfiles = []
        self.Doc.recompute()
        self.Doc.save()
        self.assertNotIn('name="ExtraProfiles"', documentXml(path))

        pad.ExtraProfiles = [(second, "")]
        self.Doc.recompute()
        volume = pad.Shape.Volume
        self.Doc.save()
        name = self.Doc.Name
        FreeCAD.closeDocument(name)
        self.Doc = FreeCAD.openDocument(path)
        pad = self.Doc.getObject("Pad")
        self.assertEqual([link[0].Name for link in pad.ExtraProfiles], ["Second"])
        self.Doc.recompute()
        self.assertAlmostEqual(pad.Shape.Volume, volume, places=6)
        self.assertAlmostEqual(volume, 2000.0, places=6)

    def tearDown(self):
        # closing doc (by its own name: the save test reopens it from the file)
        FreeCAD.closeDocument(self.Doc.Name)
        # print ("omit closing document for debugging")
