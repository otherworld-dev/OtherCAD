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
