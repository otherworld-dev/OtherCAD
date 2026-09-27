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

"""GUI regression tests for the folder rows a PartDesign body shows in the tree.

A body shows its Origin, then Sketches, Construction and History folders instead of
its flat feature history. The folders are rows of the tree only: the document and
the selection still see Body > Sketch.

To run tests:
    FreeCAD -t TestBrowserFolders
"""

import time
import unittest

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtCore, QtWidgets

TREE_PARAMS = "User parameter:BaseApp/Preferences/TreeView"
DOCUMENT_TYPE = 1000
OBJECT_TYPE = 1001
FOLDER_TYPE = 1002


def _process_events(wait_ms=50):
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    time.sleep(wait_ms / 1000.0)
    app.processEvents()


def _draw_rectangle(sketch, width, height):
    corners = [
        FreeCAD.Vector(0.0, 0.0, 0.0),
        FreeCAD.Vector(width, 0.0, 0.0),
        FreeCAD.Vector(width, height, 0.0),
        FreeCAD.Vector(0.0, height, 0.0),
    ]
    first = int(sketch.GeometryCount)
    for index in range(4):
        sketch.addGeometry(Part.LineSegment(corners[index], corners[(index + 1) % 4]), False)
    for index in range(4):
        sketch.addConstraint(
            Sketcher.Constraint("Coincident", first + index, 2, first + (index + 1) % 4, 1)
        )


class BrowserFoldersBase(unittest.TestCase):
    """Builds Body: Sketch, Pad, Sketch001 (unused), DatumPlane, ShapeBinder."""

    doc_name = "TestBrowserFolders"

    def setUp(self):
        self.params = FreeCAD.ParamGet(TREE_PARAMS)
        self.saved_pref = self.params.GetBool("BodyFolders", True)
        self.params.SetBool("BodyFolders", True)
        self.doc = FreeCAD.newDocument(self.doc_name)
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self._build_body()
        _process_events(200)

    def tearDown(self):
        FreeCADGui.Selection.clearSelection()
        for name in list(FreeCAD.listDocuments()):
            if name.startswith(self.doc_name):
                FreeCAD.closeDocument(name)
        self.params.SetBool("BodyFolders", self.saved_pref)
        _process_events()

    def _origin_feature(self, body, role):
        for feature in body.Origin.OriginFeatures:
            if feature.Role == role:
                return feature
        self.fail("No origin feature with role " + role)

    def _build_body(self):
        doc = self.doc
        self.body = doc.addObject("PartDesign::Body", "Body")
        doc.recompute()
        xy = self._origin_feature(self.body, "XY_Plane")

        self.sketch = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (xy, [""])
        self.sketch.MapMode = "FlatFace"
        _draw_rectangle(self.sketch, 10.0, 6.0)
        doc.recompute()

        self.pad = self.body.newObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = 10.0
        doc.recompute()

        self.free_sketch = self.body.newObject("Sketcher::SketchObject", "Sketch001")
        self.free_sketch.AttachmentSupport = (xy, [""])
        self.free_sketch.MapMode = "FlatFace"
        doc.recompute()

        self.plane = self.body.newObject("PartDesign::Plane", "DatumPlane")
        self.plane.AttachmentSupport = (xy, [""])
        self.plane.MapMode = "FlatFace"
        doc.recompute()

        self.binder = self.body.newObject("PartDesign::ShapeBinder", "ShapeBinder")
        doc.recompute()

    def _folders(self, body=None):
        body = body or self.body
        return body.ViewObject.claimChildrenFolders()


class TestBodyFolderContents(BrowserFoldersBase):
    """What the body's view provider hands the tree."""

    def test_body_sorts_its_group_into_three_folders(self):
        folders = self._folders()
        self.assertEqual([f[0] for f in folders], ["Sketches", "Construction", "History"])
        contents = {f[0]: [o.Name for o in f[2]] for f in folders}
        self.assertEqual(contents["Sketches"], ["Sketch", "Sketch001"])
        self.assertEqual(contents["Construction"], ["DatumPlane", "ShapeBinder"])
        self.assertEqual(contents["History"], ["Pad"])

    def test_a_consumed_sketch_is_still_in_sketches(self):
        # claimChildren leaves Sketch out because Pad claims it; the folder must not
        contents = {f[0]: [o.Name for o in f[2]] for f in self._folders()}
        self.assertNotIn(self.sketch, self.body.ViewObject.claimChildren())
        self.assertIn("Sketch", contents["Sketches"])

    def test_an_empty_folder_is_left_out(self):
        self.doc.removeObject(self.plane.Name)
        self.doc.removeObject(self.binder.Name)
        self.doc.recompute()
        self.assertEqual([f[0] for f in self._folders()], ["Sketches", "History"])

    def test_the_preference_turns_the_folders_off(self):
        self.params.SetBool("BodyFolders", False)
        _process_events()
        self.assertEqual(self._folders(), [])

    def test_other_view_providers_have_no_folders(self):
        box = self.doc.addObject("Part::Box", "Box")
        part = self.doc.addObject("App::Part", "Part")
        self.doc.recompute()
        self.assertEqual(box.ViewObject.claimChildrenFolders(), [])
        self.assertEqual(part.ViewObject.claimChildrenFolders(), [])
