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

"""GUI regression tests for the LLM bridge, the MCP server an LLM client drives OtherCAD with.

The tools are checked on a padded rectangle, then the same tools through HTTP from a
client thread, the way an MCP client calls them, while the test keeps the main thread
answering.

To run tests:
    FreeCAD -t TestBridge
"""

import base64
import json
import math
import threading
import time
import unittest
import urllib.error
import urllib.request

import FreeCAD
import FreeCADGui
import Part
import Sketcher
from PySide import QtWidgets

import Bridge
import BridgeServer
import BridgeTools

WIDTH, DEPTH, HEIGHT = 10.0, 6.0, 4.0


def process_events(wait_ms=50):
    FreeCADGui.updateGui()
    app = QtWidgets.QApplication.instance()
    app.processEvents()
    time.sleep(wait_ms / 1000.0)
    app.processEvents()


class BridgeCase(unittest.TestCase):
    """A 10 x 6 rectangle padded 4 mm in a body."""

    def setUp(self):
        self.doc = FreeCAD.newDocument("TestBridge")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.body = self.doc.addObject("PartDesign::Body", "Body")
        self.sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        self.sketch.AttachmentSupport = (self.doc.XY_Plane, [""])
        self.sketch.MapMode = "FlatFace"
        self.body.addObject(self.sketch)
        corners = [
            FreeCAD.Vector(0, 0, 0),
            FreeCAD.Vector(WIDTH, 0, 0),
            FreeCAD.Vector(WIDTH, DEPTH, 0),
            FreeCAD.Vector(0, DEPTH, 0),
        ]
        for i in range(4):
            self.sketch.addGeometry(Part.LineSegment(corners[i], corners[(i + 1) % 4]), False)
        for i in range(4):
            self.sketch.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
        self.pad = self.doc.addObject("PartDesign::Pad", "Pad")
        self.pad.Profile = self.sketch
        self.pad.Length = HEIGHT
        self.body.addObject(self.pad)
        self.doc.recompute()
        process_events()

    def tearDown(self):
        if self.doc.Name in FreeCAD.listDocuments():
            FreeCAD.closeDocument(self.doc.Name)
        process_events()


class TestBridgeTools(BridgeCase):
    def test_every_tool_has_a_description_and_an_object_schema(self):
        for tool in BridgeTools.TOOLS.values():
            self.assertTrue(tool.description, tool.name)
            self.assertEqual(tool.schema["type"], "object", tool.name)
            for required in tool.schema["required"]:
                self.assertIn(required, tool.schema["properties"], tool.name)

    def test_the_timeline_lists_the_body_features_up_to_the_tip(self):
        timeline = BridgeTools.call("get_timeline", {"document": self.doc.Name})
        names = [f["name"] for f in timeline["features"]]
        self.assertEqual(names, ["Sketch", "Pad"])
        self.assertEqual(timeline["tip"], "Pad")
        self.assertFalse(any(f["rolled_back"] for f in timeline["features"]))

        self.body.Tip = self.sketch
        timeline = BridgeTools.call("get_timeline", {"document": self.doc.Name})
        self.assertTrue(timeline["features"][1]["rolled_back"])

    def test_a_feature_in_error_carries_its_message(self):
        self.pad.Length = 0.0
        self.doc.recompute()
        pad = BridgeTools.call("get_timeline", {"document": self.doc.Name})["features"][1]
        self.assertIn("Invalid", pad["state"])
        self.assertTrue(pad.get("error"))

    def test_the_shape_is_measured_in_mm(self):
        shape = BridgeTools.call("get_shape", {"name": "Pad", "document": self.doc.Name})
        self.assertAlmostEqual(shape["volume"], WIDTH * DEPTH * HEIGHT, places=4)
        self.assertEqual(shape["solids"], 1)
        self.assertEqual(shape["faces"], 6)
        for got, wanted in zip(shape["bound_box"]["size"], (WIDTH, DEPTH, HEIGHT)):
            self.assertAlmostEqual(got, wanted, places=4)
        for got, wanted in zip(shape["center_of_mass"], (WIDTH / 2, DEPTH / 2, HEIGHT / 2)):
            self.assertAlmostEqual(got, wanted, places=4)

    def test_the_top_face_can_be_found_by_what_it_is(self):
        found = BridgeTools.call(
            "describe_faces",
            {
                "name": "Pad",
                "surface": "Plane",
                "normal": "+Z",
                "sort_by": "z",
                "descending": True,
                "limit": 1,
                "document": self.doc.Name,
            },
        )
        self.assertEqual(found["matched"], 1)
        top = found["faces"][0]
        self.assertAlmostEqual(top["center"][2], HEIGHT, places=4)
        self.assertAlmostEqual(top["area"], WIDTH * DEPTH, places=4)
        # The name it gives is the one a sketch attaches to
        face = self.pad.Shape.getElement(top["face"])
        self.assertAlmostEqual(face.CenterOfMass.z, HEIGHT, places=4)

    def test_the_sketch_reports_its_solver_state(self):
        sketch = BridgeTools.call("get_sketch", {"name": "Sketch", "document": self.doc.Name})
        self.assertEqual(len(sketch["geometry"]), 4)
        self.assertEqual(sketch["geometry"][0]["start"], [0.0, 0.0, 0.0])
        self.assertEqual(sketch["dof"], self.sketch.DoF)
        self.assertGreater(sketch["dof"], 0)
        self.assertFalse(sketch["fully_constrained"])
        self.assertEqual(sketch["conflicting"], [])

        # Two different lengths on one line cannot both hold
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 10.0))
        self.sketch.addConstraint(Sketcher.Constraint("Distance", 0, 12.0))
        self.doc.recompute()
        sketch = BridgeTools.call("get_sketch", {"name": "Sketch", "document": self.doc.Name})
        self.assertTrue(sketch["conflicting"])
        self.assertEqual(sketch["constraints"][-1]["value"], 12.0)

    def test_objects_are_found_by_label_and_unknown_ones_are_reported(self):
        self.pad.Label = "Base plate"
        found = BridgeTools.call("get_object", {"name": "Base plate", "document": self.doc.Name})
        self.assertEqual(found["name"], "Pad")
        self.assertEqual(found["properties"]["Length"], "4.0 mm")
        with self.assertRaises(BridgeTools.ToolError):
            BridgeTools.call("get_object", {"name": "Nothing", "document": self.doc.Name})

    def test_wrong_arguments_are_reported_rather_than_raised(self):
        with self.assertRaises(BridgeTools.ToolError):
            BridgeTools.call("get_shape", {"document": self.doc.Name})
        with self.assertRaises(BridgeTools.ToolError):
            BridgeTools.call("get_shape", {"name": "Pad", "colour": "red"})

    def test_a_screenshot_is_a_png_and_leaves_the_camera_alone(self):
        view = FreeCADGui.getDocument(self.doc.Name).ActiveView
        if not hasattr(view, "saveImage"):
            raise unittest.SkipTest("No 3D view in this test environment")
        view.viewFront()
        process_events()
        before_position = view.getCameraNode().position.getValue()
        before_orientation = view.getCameraOrientation()
        image = BridgeTools.call(
            "screenshot",
            {"view": "iso", "fit": True, "width": 320, "height": 240, "document": self.doc.Name},
        )
        self.assertIsInstance(image, BridgeTools.Image)
        self.assertTrue(image.data.startswith(b"\x89PNG"))
        # Compared as values: the camera's text form rounds differently after a round trip
        self.assertTrue(view.getCameraOrientation().isSame(before_orientation, 1e-6))
        self.assertTrue(view.getCameraNode().position.getValue().equals(before_position, 1e-5))


class TestBridgeActions(BridgeCase):
    def _call(self, name, arguments):
        return BridgeTools.call(name, dict(arguments, document=self.doc.Name))

    def _volume(self, name="Pad"):
        return self._call("get_shape", {"name": name})["volume"]

    def test_a_part_can_be_modelled_from_an_empty_document(self):
        doc = FreeCAD.newDocument("TestBridgeEmpty")
        try:
            made = BridgeTools.call("new_sketch", {"on": "XY", "document": doc.Name})
            self.assertEqual(doc.getObject(made["body"]).TypeId, "PartDesign::Body")
            added = BridgeTools.call(
                "sketch_add",
                {
                    "sketch": made["sketch"],
                    "geometry": [{"type": "rectangle", "corner": [0, 0], "size": [20, 10]}],
                    "constraints": [
                        {
                            "type": "DistanceX",
                            "refs": [["new0", "start"], ["new0", "end"]],
                            "value": 20,
                        },
                        {
                            "type": "DistanceY",
                            "refs": [["new1", "start"], ["new1", "end"]],
                            "value": 10,
                        },
                        {"type": "Coincident", "refs": [["new0", "start"], "origin"]},
                    ],
                    "document": doc.Name,
                },
            )
            self.assertEqual(len(added["geometry"]), 4)
            self.assertEqual(added["dof"], 0)
            self.assertTrue(added["fully_constrained"])

            padded = BridgeTools.call(
                "pad", {"profile": made["sketch"], "length": 5, "document": doc.Name}
            )
            self.assertFalse(padded["rolled_back"])
            self.assertIn(padded["feature"], padded["created"])
            shape = BridgeTools.call("get_shape", {"name": padded["feature"], "document": doc.Name})
            self.assertAlmostEqual(shape["volume"], 1000.0, places=4)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def test_a_pocket_cuts_through_the_pad(self):
        made = self._call("new_sketch", {"on": "XY"})
        self._call(
            "sketch_add",
            {
                "sketch": made["sketch"],
                "geometry": [{"type": "circle", "center": [5, 3], "radius": 1}],
            },
        )
        self._call("pocket", {"profile": made["sketch"], "type": "ThroughAll", "symmetric": True})
        tip = self.body.Tip
        self.assertEqual(tip.TypeId, "PartDesign::Pocket")
        self.assertAlmostEqual(
            tip.Shape.Volume, WIDTH * DEPTH * HEIGHT - math.pi * HEIGHT, places=3
        )

    def test_a_pocket_that_cuts_nothing_is_undone_with_a_hint(self):
        # From the XY plane at the bottom of the pad, a pocket cuts down, away from the
        # solid: it builds without an error and removes nothing
        made = self._call("new_sketch", {"on": "XY"})
        self._call(
            "sketch_add",
            {
                "sketch": made["sketch"],
                "geometry": [{"type": "circle", "center": [5, 3], "radius": 1}],
            },
        )
        with self.assertRaises(BridgeTools.ActionFailed) as caught:
            self._call("pocket", {"profile": made["sketch"], "type": "ThroughAll"})
        details = caught.exception.details
        self.assertTrue(details["rolled_back"])
        self.assertIn("reversed", details["errors"][0]["error"])
        self.assertEqual(self.body.Tip, self.pad)
        self.assertEqual([o for o in self.doc.Objects if o.TypeId == "PartDesign::Pocket"], [])

        self._call("pocket", {"profile": made["sketch"], "type": "ThroughAll", "reversed": True})
        self.assertAlmostEqual(
            self.body.Tip.Shape.Volume, WIDTH * DEPTH * HEIGHT - math.pi * HEIGHT, places=3
        )

    def test_a_pad_inside_the_solid_is_undone(self):
        made = self._call("new_sketch", {"on": "XY"})
        self._call(
            "sketch_add",
            {
                "sketch": made["sketch"],
                "geometry": [{"type": "circle", "center": [5, 3], "radius": 1}],
            },
        )
        with self.assertRaises(BridgeTools.ActionFailed) as caught:
            self._call("pad", {"profile": made["sketch"], "length": 2})
        self.assertIn("added no material", caught.exception.details["errors"][0]["error"])
        self.assertEqual(self.body.Tip, self.pad)

    def test_the_origin_ref_can_be_written_as_a_list(self):
        added = self._call(
            "sketch_add",
            {
                "sketch": "Sketch",
                "constraints": [{"type": "Coincident", "refs": [[0, "start"], ["origin"]]}],
            },
        )
        constraint = self.sketch.Constraints[added["constraints"][0]]
        self.assertEqual((constraint.Second, constraint.SecondPos), (-1, 1))

    def test_a_sketch_goes_on_a_face_found_by_what_it_is(self):
        top = self._call(
            "describe_faces",
            {"name": "Pad", "normal": "+Z", "sort_by": "z", "descending": True, "limit": 1},
        )["faces"][0]["face"]
        made = self._call("new_sketch", {"on": f"Pad:{top}"})
        sketch = self.doc.getObject(made["sketch"])
        self.assertEqual(sketch.AttachmentSupport[0][1], (top,))
        self.assertAlmostEqual(sketch.Placement.Base.z, HEIGHT, places=4)
        with self.assertRaises(BridgeTools.ToolError):
            self._call("new_sketch", {"on": "Pad:Face99"})

    def test_a_change_that_breaks_the_model_is_undone_with_its_errors(self):
        made = self._call("new_sketch", {"on": "XY"})
        # One line is not a closed profile, so a pad of it fails
        self._call(
            "sketch_add",
            {
                "sketch": made["sketch"],
                "geometry": [{"type": "line", "start": [0, 0], "end": [5, 0]}],
            },
        )
        objects = len(self.doc.Objects)
        undo_count = self.doc.UndoCount
        with self.assertRaises(BridgeTools.ActionFailed) as caught:
            self._call("pad", {"profile": made["sketch"], "length": 3})
        details = caught.exception.details
        self.assertTrue(details["rolled_back"])
        self.assertTrue(details["errors"])
        self.assertEqual(len(self.doc.Objects), objects)
        self.assertEqual(self.doc.UndoCount, undo_count)
        self.assertTrue(self.pad.isValid())

    def test_conflicting_constraints_are_undone_and_named(self):
        with self.assertRaises(BridgeTools.ActionFailed) as caught:
            self._call(
                "sketch_add",
                {
                    "sketch": "Sketch",
                    "constraints": [
                        {"type": "Distance", "refs": [[0]], "value": 10},
                        {"type": "Distance", "refs": [[0]], "value": 12},
                    ],
                },
            )
        error = caught.exception.details["errors"][0]
        self.assertEqual(error["name"], "Sketch")
        self.assertTrue(error["conflicting"])
        self.assertEqual(len(self.sketch.Constraints), 4)

    def test_a_property_or_an_expression_drives_the_model(self):
        report = self._call("set_property", {"name": "Pad", "property": "Length", "value": "8 mm"})
        self.assertEqual(report["changed"]["Pad"], ["Length"])
        self.assertAlmostEqual(self._volume(), WIDTH * DEPTH * 8, places=4)
        self._call("set_property", {"name": "Pad", "property": "Length", "expression": "3 * 2 mm"})
        self.assertAlmostEqual(self.pad.Length.Value, 6.0)
        with self.assertRaises(BridgeTools.ToolError) as caught:
            self._call("set_property", {"name": "Pad", "property": "Lenght", "value": 3})
        self.assertIn("Length", str(caught.exception))

    def test_sketch_values_change_by_name(self):
        self._call(
            "sketch_add",
            {
                "sketch": "Sketch",
                "constraints": [
                    {
                        "type": "DistanceX",
                        "refs": [[0, "start"], [0, "end"]],
                        "value": 10,
                        "name": "width",
                    }
                ],
            },
        )
        self._call("sketch_set_value", {"sketch": "Sketch", "constraint": "width", "value": 15})
        self.assertAlmostEqual(self.sketch.Constraints[-1].Value, 15.0)
        line = self.sketch.Geometry[0]
        self.assertAlmostEqual(line.EndPoint.x - line.StartPoint.x, 15.0, places=4)

    def test_edges_found_by_direction_are_filleted(self):
        found = self._call("describe_edges", {"name": "Pad", "direction": "Z"})
        self.assertEqual(found["matched"], 4)
        edges = [f"Pad:{e['edge']}" for e in found["edges"]]
        made = self._call("fillet", {"edges": edges, "radius": 1})
        corner_loss = 4 * (1 - math.pi / 4) * HEIGHT
        self.assertAlmostEqual(
            self.doc.getObject(made["feature"]).Shape.Volume,
            WIDTH * DEPTH * HEIGHT - corner_loss,
            places=3,
        )
        rim = self._call("describe_edges", {"name": "Pad", "of_face": "Face1"})
        self.assertEqual(rim["matched"], 4)

    def test_the_tip_rolls_the_timeline_back(self):
        # A sketch cannot carry the tip, so with no solid before it the history rolls
        # off its start, as the playhead does
        moved = self._call("set_tip", {"feature": "Sketch"})
        self.assertIsNone(moved["tip"])
        self.assertIsNone(self.body.Tip)
        self.assertTrue(self.body.isValid())
        timeline = self._call("get_timeline", {})
        self.assertTrue(timeline["features"][1]["rolled_back"])

        self._call("set_tip", {"feature": "Pad"})
        self.assertEqual(self.body.Tip, self.pad)

    def test_deleting_a_feature_others_need_is_refused_unless_kept(self):
        with self.assertRaises(BridgeTools.ActionFailed):
            self._call("delete_object", {"name": "Sketch"})
        self.assertIsNotNone(self.doc.getObject("Sketch"))
        self.assertTrue(self.pad.isValid())

    def test_a_change_can_be_undone_and_redone(self):
        self._call("set_property", {"name": "Pad", "property": "Length", "value": 9})
        undone = self._call("undo", {})
        self.assertEqual(undone["undone"], ["Bridge: Set Length"])
        self.assertAlmostEqual(self.pad.Length.Value, HEIGHT)
        self._call("redo", {})
        self.assertAlmostEqual(self.pad.Length.Value, 9.0)

    def test_python_returns_output_and_the_last_value(self):
        ran = self._call("run_python", {"code": "x = 21\nprint('hello')\nx * 2"})
        self.assertEqual(ran["output"], "hello\n")
        self.assertEqual(ran["result"], "42")
        # Names persist between calls, and doc is the document
        ran = self._call("run_python", {"code": "x + len(doc.Objects) * 0"})
        self.assertEqual(ran["result"], "21")
        ran = self._call("run_python", {"code": "doc.addObject('Part::Box', 'Box')\nNone"})
        self.assertIn("Box", ran["created"])

    def test_python_that_raises_is_undone_with_its_traceback(self):
        with self.assertRaises(BridgeTools.ActionFailed) as caught:
            self._call(
                "run_python",
                {"code": "doc.addObject('Part::Box', 'Doomed')\nprint('made it')\n1 / 0"},
            )
        details = caught.exception.details
        self.assertIn("ZeroDivisionError", details["traceback"])
        self.assertNotIn("BridgeActions", details["traceback"])
        self.assertEqual(details["output"], "made it\n")
        self.assertTrue(details["rolled_back"])
        self.assertIsNone(self.doc.getObject("Doomed"))

    def test_changes_wait_while_the_user_has_a_task_panel_open(self):
        FreeCADGui.getDocument(self.doc.Name).setEdit(self.pad.Name)
        process_events(100)
        try:
            if not FreeCADGui.Control.activeDialog():
                raise unittest.SkipTest("The Pad task panel did not open")
            with self.assertRaises(BridgeTools.ToolError):
                self._call("set_property", {"name": "Pad", "property": "Length", "value": 9})
            # Reading still works
            self._call("get_timeline", {})
        finally:
            FreeCADGui.getDocument(self.doc.Name).resetEdit()
            process_events(100)
            if FreeCADGui.Control.activeDialog():
                FreeCADGui.Control.closeDialog()
                process_events(100)
        self.assertAlmostEqual(self.pad.Length.Value, HEIGHT)

    def test_read_only_preferences_hide_the_tools_that_change_things(self):
        # Never started, so only the socket needs closing
        server = BridgeServer.Server("127.0.0.1", 0, read_only=True)
        try:
            answer = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            tools = {t["name"]: t for t in answer["result"]["tools"]}
            self.assertIn("get_timeline", tools)
            self.assertNotIn("pad", tools)
            self.assertNotIn("run_python", tools)
            self.assertTrue(tools["get_timeline"]["annotations"]["readOnlyHint"])
            refused = server.handle(
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "pad"}}
            )
            self.assertEqual(refused["error"]["code"], -32602)
        finally:
            server.httpd.server_close()
        server = BridgeServer.Server("127.0.0.1", 0, allow_python=False)
        try:
            answer = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            names = {t["name"] for t in answer["result"]["tools"]}
            self.assertIn("pad", names)
            self.assertNotIn("run_python", names)
        finally:
            server.httpd.server_close()


class TestBridgeServer(BridgeCase):
    @classmethod
    def setUpClass(cls):
        cls.was_running = Bridge.isRunning()
        if cls.was_running:
            raise unittest.SkipTest("The bridge is already running in this session")
        cls.url = Bridge.start(port=0, token="")

    @classmethod
    def tearDownClass(cls):
        if not cls.was_running:
            Bridge.stop()

    def _post(self, body, headers=None, timeout=20.0):
        """POST from a client thread while the main thread keeps answering tool calls."""

        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(self.url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        outcome = {}

        def send():
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = response.read()
                    outcome["status"] = response.status
                    outcome["body"] = json.loads(raw) if raw else None
            except urllib.error.HTTPError as error:
                outcome["status"] = error.code
                outcome["body"] = None
            except Exception as error:
                outcome["error"] = error

        client = threading.Thread(target=send, daemon=True)
        client.start()
        deadline = time.monotonic() + timeout
        while client.is_alive() and time.monotonic() < deadline:
            QtWidgets.QApplication.instance().processEvents()
            time.sleep(0.01)
        client.join(1.0)
        self.assertFalse(client.is_alive(), "The bridge did not answer")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["status"], outcome["body"]

    def _call(self, name, arguments):
        status, body = self._post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
        self.assertEqual(status, 200)
        return body["result"]

    def test_a_client_can_initialize_and_list_the_tools(self):
        status, body = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "TestBridge", "version": "1"},
                },
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", body["result"]["capabilities"])

        status, body = self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(status, 202)

        status, body = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in body["result"]["tools"]}
        self.assertTrue({"get_timeline", "describe_faces", "get_sketch", "screenshot"} <= names)

    def test_a_tool_call_runs_on_the_main_thread_and_returns_json(self):
        result = self._call("get_timeline", {"document": self.doc.Name})
        self.assertFalse(result["isError"])
        timeline = json.loads(result["content"][0]["text"])
        self.assertEqual(timeline["tip"], "Pad")

    def test_a_tool_error_comes_back_as_an_error_result(self):
        result = self._call("get_shape", {"name": "Nothing", "document": self.doc.Name})
        self.assertTrue(result["isError"])
        self.assertIn("Nothing", result["content"][0]["text"])

    def test_an_undone_change_comes_back_as_an_error_with_its_details(self):
        result = self._call("delete_object", {"name": "Sketch", "document": self.doc.Name})
        self.assertTrue(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn("undone", text)
        self.assertIn('"rolled_back": true', text)
        self.assertIsNotNone(self.doc.getObject("Sketch"))

    def test_a_screenshot_comes_back_as_an_image(self):
        view = FreeCADGui.getDocument(self.doc.Name).ActiveView
        if not hasattr(view, "saveImage"):
            raise unittest.SkipTest("No 3D view in this test environment")
        result = self._call("screenshot", {"width": 160, "height": 120, "document": self.doc.Name})
        self.assertEqual(result["content"][0]["type"], "image")
        self.assertTrue(base64.b64decode(result["content"][0]["data"]).startswith(b"\x89PNG"))

    def test_an_unknown_method_or_tool_is_a_json_rpc_error(self):
        status, body = self._post({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
        self.assertEqual(body["error"]["code"], -32601)
        status, body = self._post(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "rm_rf"}}
        )
        self.assertEqual(body["error"]["code"], -32602)

    def test_a_web_page_cannot_reach_the_bridge(self):
        status, _ = self._post(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
