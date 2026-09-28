# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2026 FuCadUp contributors                               *
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

"""The New body operation starts a body of its own and leaves the old one alone.

Every body below starts with a 10 x 10 x 10 cube (volume 1000) at the origin, and the
new solid is a 10 x 10 rectangle further along X, so the two never touch and each
volume says which solid ended up where.
"""

import unittest

import FreeCAD
import Part

import PartDesignNewBody

CUBE = 1000.0


class TestNewBody(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestNewBody")
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        cube = self._sketch("Cube", [(0, 0, 10, 10)])
        pad = self.Body.newObject("PartDesign::Pad", "Pad")
        pad.Profile = cube
        pad.Length = 10
        self.Doc.recompute()
        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE, places=3)

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    # -- helpers ---------------------------------------------------------

    def _sketch(self, name, rectangles, body=None):
        body = body or self.Body
        sketch = body.newObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (body.Origin.OriginFeatures[3], [""])  # XY_Plane
        sketch.MapMode = "FlatFace"
        self._draw(sketch, rectangles)
        self.Doc.recompute()
        return sketch

    def _draw(self, sketch, rectangles):
        for x0, y0, x1, y1 in rectangles:
            corners = [
                FreeCAD.Vector(x0, y0, 0),
                FreeCAD.Vector(x1, y0, 0),
                FreeCAD.Vector(x1, y1, 0),
                FreeCAD.Vector(x0, y1, 0),
            ]
            for start, end in zip(corners, corners[1:] + corners[:1]):
                sketch.addGeometry(Part.LineSegment(start, end), False)

    def _newBodyPad(self, profile, length=5, name="NewPad"):
        pad = self.Body.newObject("PartDesign::Pad", name)
        pad.Profile = profile
        pad.Length = length
        pad.Operation = "NewBody"
        self.Doc.recompute()
        return pad

    def _bodies(self):
        return [obj for obj in self.Doc.Objects if obj.isDerivedFrom("PartDesign::Body")]

    def _assertValid(self):
        for obj in self.Doc.Objects:
            self.assertTrue(obj.isValid(), f"{obj.Name}: {obj.getStatusString()}")

    # -- the feature in the body it was made in --------------------------

    def testNewBodyLeavesTheBodysSolidAlone(self):
        pad = self._newBodyPad(self._sketch("Other", [(20, 0, 30, 10)]))

        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE, places=3)
        self.assertAlmostEqual(pad.AddSubShape.Volume, 500.0, places=3)

    def testNewBodyRevolveLeavesTheBodysSolidAlone(self):
        sketch = self._sketch("Other", [(20, 0, 30, 10)])
        revolve = self.Body.newObject("PartDesign::Revolution", "NewRevolve")
        revolve.Profile = sketch
        revolve.ReferenceAxis = (sketch, ["H_Axis"])
        revolve.Angle = 90
        revolve.Operation = "NewBody"
        self.Doc.recompute()

        self.assertTrue(revolve.isValid(), revolve.getStatusString())
        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE, places=3)
        self.assertGreater(revolve.AddSubShape.Volume, 0)

    # -- moving it out ---------------------------------------------------

    def testMovesIntoABodyOfItsOwn(self):
        sketch = self._sketch("Other", [(20, 0, 30, 10)])
        pad = self._newBodyPad(sketch)

        newBody = PartDesignNewBody.moveToNewBody(pad)

        self.assertIsNotNone(newBody)
        self.assertEqual(len(self._bodies()), 2)
        self.assertIn(pad, newBody.Group)
        self.assertIn(sketch, newBody.Group)
        self.assertNotIn(pad, self.Body.Group)
        self.assertIs(newBody.Tip, pad)
        self.assertIsNone(pad.BaseFeature)
        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE, places=3)
        self.assertAlmostEqual(newBody.Shape.Volume, 500.0, places=3)
        self._assertValid()

    def testMovedSketchIsAttachedToTheNewBodysOrigin(self):
        sketch = self._sketch("Other", [(20, 0, 30, 10)])
        newBody = PartDesignNewBody.moveToNewBody(self._newBodyPad(sketch))

        support = sketch.AttachmentSupport[0][0]
        self.assertIn(support, newBody.Origin.OriginFeatures)

    def testNewBodyFollowsThePlacementOfTheOldOne(self):
        self.Body.Placement.Base = FreeCAD.Vector(100, 0, 0)
        self.Doc.recompute()
        pad = self._newBodyPad(self._sketch("Other", [(20, 0, 30, 10)]))

        newBody = PartDesignNewBody.moveToNewBody(pad)

        self.assertAlmostEqual(newBody.Shape.BoundBox.XMin, 120.0, places=3)
        self.assertAlmostEqual(newBody.Shape.BoundBox.XMax, 130.0, places=3)

    def testTheFirstSolidOfABodyStaysPut(self):
        body = self.Doc.addObject("PartDesign::Body", "Empty")
        sketch = self._sketch("First", [(20, 0, 30, 10)], body=body)
        pad = body.newObject("PartDesign::Pad", "FirstPad")
        pad.Profile = sketch
        pad.Length = 5
        pad.Operation = "NewBody"
        self.Doc.recompute()

        self.assertIsNone(PartDesignNewBody.moveToNewBody(pad))
        self.assertIn(pad, body.Group)
        self.assertAlmostEqual(body.Shape.Volume, 500.0, places=3)

    def testOtherOperationsStayPut(self):
        pad = self._newBodyPad(self._sketch("Other", [(20, 0, 30, 10)]))
        pad.Operation = "Join"
        self.Doc.recompute()

        self.assertIsNone(PartDesignNewBody.moveToNewBody(pad))
        self.assertEqual(len(self._bodies()), 1)

    # -- inputs that have to stay behind ----------------------------------

    def testSharedSketchIsBoundNotMoved(self):
        sketch = self._sketch("Shared", [(20, 0, 30, 10)])
        join = self.Body.newObject("PartDesign::Pad", "JoinPad")
        join.Profile = sketch
        join.Length = 5
        self.Doc.recompute()
        pad = self._newBodyPad(sketch, length=3)

        newBody = PartDesignNewBody.moveToNewBody(pad)

        self.assertIn(sketch, self.Body.Group)
        binder = pad.Profile[0]
        self.assertTrue(binder.isDerivedFrom("PartDesign::SubShapeBinder"))
        self.assertIn(binder, newBody.Group)
        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE + 500.0, places=3)
        self.assertAlmostEqual(newBody.Shape.Volume, 300.0, places=3)
        self._assertValid()

    def testASharedSketchsNormalIsNoInput(self):
        """Extrude points ReferenceAxis at the sketch's N_Axis, which a binder cannot hold."""
        sketch = self._sketch("Shared", [(20, 0, 30, 10)])
        join = self.Body.newObject("PartDesign::Pad", "JoinPad")
        join.Profile = sketch
        join.Length = 5
        self.Doc.recompute()
        pad = self._newBodyPad(sketch, length=3)
        pad.ReferenceAxis = (sketch, ["N_Axis"])
        self.Doc.recompute()

        newBody = PartDesignNewBody.moveToNewBody(pad)

        binders = [o for o in newBody.Group if o.isDerivedFrom("PartDesign::SubShapeBinder")]
        self.assertEqual(len(binders), 1, "only the profile needs a binder")
        self.assertAlmostEqual(newBody.Shape.Volume, 300.0, places=3)
        self._assertValid()

    def testBoundProfileFollowsTheSketch(self):
        sketch = self._sketch("Shared", [(20, 0, 30, 10)])
        join = self.Body.newObject("PartDesign::Pad", "JoinPad")
        join.Profile = sketch
        join.Length = 5
        self.Doc.recompute()
        pad = self._newBodyPad(sketch, length=3)
        newBody = PartDesignNewBody.moveToNewBody(pad)

        sketch.deleteAllGeometry()
        self._draw(sketch, [(20, 0, 32, 10)])
        self.Doc.recompute()

        self.assertAlmostEqual(newBody.Shape.Volume, 360.0, places=3)

    def testPickedRegionsSurviveBinding(self):
        sketch = self._sketch("Regions", [(20, 0, 30, 10), (40, 0, 50, 10)])
        join = self.Body.newObject("PartDesign::Pad", "JoinPad")
        join.Profile = sketch
        join.Length = 5
        self.Doc.recompute()
        pad = self._newBodyPad((sketch, ["InternalFace1"]), length=3)
        self.assertAlmostEqual(pad.AddSubShape.Volume, 300.0, places=3)

        newBody = PartDesignNewBody.moveToNewBody(pad)

        self.assertAlmostEqual(newBody.Shape.Volume, 300.0, places=3)
        self._assertValid()

    def testSketchProjectingTheOldBodyStays(self):
        sketch = self._sketch("Projecting", [(20, 0, 30, 10)])
        sketch.addExternal("Pad", "Edge1")
        self.Doc.recompute()
        pad = self._newBodyPad(sketch)

        newBody = PartDesignNewBody.moveToNewBody(pad)

        self.assertIn(sketch, self.Body.Group)
        self.assertAlmostEqual(newBody.Shape.Volume, 500.0, places=3)
        self._assertValid()

    def testRevolveAxisOnAStayingSketchIsBound(self):
        sketch = self._sketch("Shared", [(20, 0, 30, 10)])
        join = self.Body.newObject("PartDesign::Pad", "JoinPad")
        join.Profile = sketch
        join.Length = 5
        self.Doc.recompute()
        revolve = self.Body.newObject("PartDesign::Revolution", "NewRevolve")
        revolve.Profile = sketch
        revolve.ReferenceAxis = (sketch, ["H_Axis"])
        revolve.Angle = 90
        revolve.Operation = "NewBody"
        self.Doc.recompute()
        expected = revolve.AddSubShape.Volume

        newBody = PartDesignNewBody.moveToNewBody(revolve)

        self.assertAlmostEqual(newBody.Shape.Volume, expected, places=3)
        self._assertValid()

    # -- undo ------------------------------------------------------------

    def testOneUndoPutsItAllBack(self):
        self.Doc.UndoMode = 1
        sketch = self._sketch("Other", [(20, 0, 30, 10)])
        pad = self._newBodyPad(sketch)

        self.Doc.openTransaction("New body")
        PartDesignNewBody.moveToNewBody(pad)
        self.Doc.commitTransaction()
        self.Doc.undo()
        self.Doc.recompute()

        self.assertEqual(len(self._bodies()), 1)
        self.assertIn(pad, self.Body.Group)
        self.assertIn(sketch, self.Body.Group)
        self.assertAlmostEqual(self.Body.Shape.Volume, CUBE, places=3)
