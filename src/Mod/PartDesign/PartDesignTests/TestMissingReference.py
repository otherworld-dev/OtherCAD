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

"""What a dress-up feature says when an element it was built on has gone.

A 10 x 10 square is padded and one of its corners is filleted or shelled. The
sketch then becomes a triangle, so that corner, and the edge or face the feature
used, no longer exists. The feature used to fail with the shape's internal name for
the element, such as "Invalid edge link: ;#11:6;:G;XTR;:H1307:7,E.Edge5".
"""

import unittest

import FreeCAD
import Part
import Sketcher


class TestMissingReference(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestMissingReference")
        self.Body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Sketch = self.Body.newObject("Sketcher::SketchObject", "Sketch")
        self.Sketch.AttachmentSupport = (self.Body.Origin.OriginFeatures[3], [""])  # XY_Plane
        self.Sketch.MapMode = "FlatFace"
        self._draw([(0, 0), (10, 0), (10, 10), (0, 10)])
        self.Pad = self.Body.newObject("PartDesign::Pad", "Pad")
        self.Pad.Profile = self.Sketch
        self.Pad.Length = 10
        self.Doc.recompute()

    def tearDown(self):
        FreeCAD.closeDocument(self.Doc.Name)

    def _draw(self, corners):
        points = [FreeCAD.Vector(x, y, 0) for x, y in corners]
        for start, end in zip(points, points[1:] + points[:1]):
            self.Sketch.addGeometry(Part.LineSegment(start, end), False)
        count = len(points)
        for i in range(count):
            self.Sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % count, 1))

    def _corner_edge(self):
        """The upright edge at the corner (10, 10), the one a triangle does not have."""
        for index, edge in enumerate(self.Pad.Shape.Edges, start=1):
            a, b = (vertex.Point for vertex in edge.Vertexes)
            if abs(a.z - b.z) > 5 and abs(a.x - 10) < 1e-6 and abs(a.y - 10) < 1e-6:
                return f"Edge{index}"
        self.fail("no upright edge at (10, 10)")

    def _corner_face(self):
        """The side face at x = 10, which a triangle turns into a sloping one."""
        for index, face in enumerate(self.Pad.Shape.Faces, start=1):
            box = face.BoundBox
            if abs(box.XMin - 10) < 1e-6 and abs(box.XMax - 10) < 1e-6:
                return f"Face{index}"
        self.fail("no side face at x = 10")

    def _make_triangle(self):
        self.Sketch.deleteAllGeometry()
        self._draw([(0, 0), (10, 0), (0, 10)])
        self.Doc.recompute()

    def testAFilletSaysWhichEdgeHasGone(self):
        edge = self._corner_edge()
        fillet = self.Body.newObject("PartDesign::Fillet", "Fillet")
        fillet.Base = (self.Pad, [edge])
        fillet.Radius = 1
        self.Doc.recompute()
        self.assertTrue(fillet.isValid(), fillet.getStatusString())

        self._make_triangle()

        self.assertFalse(fillet.isValid())
        self.assertEqual(
            fillet.getStatusString(),
            f"{edge} of Pad no longer exists. Edit Fillet to remove it or pick another.",
        )

    def testAChamferSaysWhichEdgeHasGone(self):
        edge = self._corner_edge()
        chamfer = self.Body.newObject("PartDesign::Chamfer", "Chamfer")
        chamfer.Base = (self.Pad, [edge])
        chamfer.Size = 1
        self.Doc.recompute()
        self.assertTrue(chamfer.isValid(), chamfer.getStatusString())

        self._make_triangle()

        self.assertFalse(chamfer.isValid())
        self.assertIn(f"{edge} of Pad no longer exists", chamfer.getStatusString())

    def testAShellSaysWhichFaceHasGone(self):
        face = self._corner_face()
        shell = self.Body.newObject("PartDesign::Thickness", "Shell")
        shell.Base = (self.Pad, [face])
        shell.Value = 1
        self.Doc.recompute()
        self.assertTrue(shell.isValid(), shell.getStatusString())

        self._make_triangle()

        self.assertFalse(shell.isValid())
        self.assertIn("no longer exists", shell.getStatusString())
