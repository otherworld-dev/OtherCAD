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

"""Reading the Operation property out of a document FreeCAD wrote.

Upstream FreeCAD gives each feature class only the operations it can perform:
an additive feature offers {"Union"}, a subtractive one {"Subtraction",
"Common"}. OtherCAD offers all four operations on every feature, because one
tool is both. A document stores the index into the list, so the numbering does
not line up and a pocket saved by FreeCAD as index 0 would read here as Join
and quietly turn into a pad.

FreeCAD builds those short lists as custom enumerations, which means the value
names travel with the document. That is what these tests lean on, and it is
what the migration reads instead of the index. Assigning a sequence to the
property is exactly how a custom enumeration is made, so the documents saved
below are byte-for-byte what FreeCAD writes.
"""

import os
import shutil
import tempfile
import unittest

import FreeCAD
import Part

OURS = ["Join", "Cut", "Intersect", "NewBody"]


class TestOperationMigration(unittest.TestCase):
    def setUp(self):
        self.Doc = FreeCAD.newDocument("PartDesignTestOperationMigration")
        self.tempdir = tempfile.mkdtemp(prefix="PDOperationMigration")

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            if name.startswith("PartDesignTestOperationMigration"):
                FreeCAD.closeDocument(name)
        shutil.rmtree(getattr(self, "tempdir", ""), ignore_errors=True)

    # -- helpers ---------------------------------------------------------

    def _sketch(self, name, width, height):
        sketch = self.Doc.addObject("Sketcher::SketchObject", name)
        sketch.AttachmentSupport = (self.Doc.XY_Plane, [""])
        sketch.MapMode = "FlatFace"
        corners = [
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(width, 0, 0),
            FreeCAD.Vector(width, height, 0),
            FreeCAD.Vector(0, height, 0),
        ]
        for start, end in zip(corners, corners[1:] + corners[:1]):
            sketch.addGeometry(Part.LineSegment(start, end), False)
        return sketch

    def _body_with_pad_and_pocket(self):
        body = self.Doc.addObject("PartDesign::Body", "Body")
        self.Doc.recompute()

        sketch = self._sketch("SketchPad", 20.0, 20.0)
        body.addObject(sketch)
        self.Doc.recompute()
        pad = self.Doc.addObject("PartDesign::Pad", "Pad")
        pad.Profile = sketch
        pad.Length = 10.0
        body.addObject(pad)
        self.Doc.recompute()

        sketch2 = self._sketch("SketchPocket", 5.0, 5.0)
        body.addObject(sketch2)
        self.Doc.recompute()
        pocket = self.Doc.addObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = sketch2
        pocket.Length = 5.0
        pocket.Reversed = True
        body.addObject(pocket)
        self.Doc.recompute()

        return body, pad, pocket

    def _save_and_reopen(self):
        path = os.path.join(self.tempdir, "migration.FCStd")
        name = self.Doc.Name
        self.Doc.saveAs(path)
        FreeCAD.closeDocument(name)
        self.Doc = FreeCAD.openDocument(path)
        return self.Doc

    # -- tests -----------------------------------------------------------

    def testSubtractiveOperationWrittenByFreeCADIsReadByName(self):
        """FreeCAD's "Subtraction" is index 0, which is Join here."""

        body, pad, pocket = self._body_with_pad_and_pocket()
        cut_volume = pocket.Shape.Volume
        self.assertLess(cut_volume, pad.Shape.Volume)

        # What FreeCAD's Pocket constructor leaves behind, and what it saves. The
        # enumeration is swapped after the last recompute on purpose: FreeCAD stores the
        # shape its own subtractive feature produced, so the file has to carry the
        # already-cut solid next to the operation name this build cannot number.
        pocket.Operation = [["Subtraction", "Common"], 0]
        pad.Operation = [["Union"], 0]

        doc = self._save_and_reopen()
        reopened_pad = doc.getObject("Pad")
        reopened_pocket = doc.getObject("Pocket")

        self.assertEqual(reopened_pocket.Operation, "Cut")
        self.assertEqual(reopened_pad.Operation, "Join")

        # The whole point: recomputing on the migrated operation still removes material
        # rather than adding it.
        doc.recompute()
        self.assertAlmostEqual(reopened_pocket.Shape.Volume, cut_volume, places=5)
        self.assertLess(reopened_pocket.Shape.Volume, reopened_pad.Shape.Volume)

    def testCommonOperationWrittenByFreeCADBecomesIntersect(self):
        """FreeCAD's "Common" is index 1, which is Cut here."""

        body, pad, pocket = self._body_with_pad_and_pocket()

        pocket.Operation = [["Subtraction", "Common"], 1]
        self.Doc.recompute()

        doc = self._save_and_reopen()
        self.assertEqual(doc.getObject("Pocket").Operation, "Intersect")

    def testMigrationRestoresOurOwnEnumeration(self):
        """A migrated feature has to offer all four operations again."""

        body, pad, pocket = self._body_with_pad_and_pocket()

        pocket.Operation = [["Subtraction", "Common"], 0]
        self.Doc.recompute()

        doc = self._save_and_reopen()
        reopened = doc.getObject("Pocket")
        self.assertEqual(reopened.getEnumerationsOfProperty("Operation"), OURS)

        # And the restored list still means what it says.
        reopened.Operation = "Intersect"
        doc.recompute()
        self.assertEqual(reopened.Operation, "Intersect")

    def testDocumentsWrittenHereAreLeftAlone(self):
        """Our own files carry no enumeration, so nothing is translated."""

        body, pad, pocket = self._body_with_pad_and_pocket()
        self.assertEqual(pocket.Operation, "Cut")

        pocket.Operation = "Intersect"
        self.Doc.recompute()
        volume = pocket.Shape.Volume

        doc = self._save_and_reopen()
        reopened = doc.getObject("Pocket")

        self.assertEqual(reopened.Operation, "Intersect")
        self.assertEqual(reopened.getEnumerationsOfProperty("Operation"), OURS)
        self.assertAlmostEqual(reopened.Shape.Volume, volume, places=5)

    def testNewBodySurvivesAReload(self):
        """The operation FreeCAD has no name for still has to round-trip."""

        body, pad, pocket = self._body_with_pad_and_pocket()

        pocket.Operation = "NewBody"
        self.Doc.recompute()

        doc = self._save_and_reopen()
        self.assertEqual(doc.getObject("Pocket").Operation, "NewBody")


if __name__ == "__main__":
    unittest.main()
