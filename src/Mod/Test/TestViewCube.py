# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI tests for OtherCAD's view cube (Gui::SoViewCube) and the cube style setting.

To run tests:
    OtherCAD -t TestViewCube
"""

import time
import unittest

import FreeCAD
import FreeCADGui

NAVICUBE_PARAMS = "User parameter:BaseApp/Preferences/NaviCube"


def process_events(wait_ms=30):
    from PySide import QtWidgets

    FreeCADGui.updateGui()
    QtWidgets.QApplication.instance().processEvents()
    time.sleep(wait_ms / 1000.0)
    QtWidgets.QApplication.instance().processEvents()


class ViewCubeTestBase(unittest.TestCase):
    """A fresh document and 3D view, with the cube style put back afterwards."""

    def setUp(self):
        self.group = FreeCAD.ParamGet(NAVICUBE_PARAMS)
        self._had_style = "CubeStyle" in self.group.GetInts()
        self._style = self.group.GetInt("CubeStyle", 0)
        self.doc = FreeCAD.newDocument("TestViewCube")
        self.view = self._active_view()
        self.viewer = self.view.getViewer()
        process_events()

    def tearDown(self):
        if self._had_style:
            self.group.SetInt("CubeStyle", self._style)
        else:
            self.group.RemInt("CubeStyle")
        FreeCAD.closeDocument(self.doc.Name)

    def _active_view(self, timeout=2.0):
        deadline = time.monotonic() + timeout
        while True:
            view = FreeCADGui.getDocument(self.doc.Name).ActiveView
            if view is not None:
                return view
            if time.monotonic() >= deadline:
                self.fail("no 3D view appeared for the test document")
            process_events(20)

    def cube_node(self):
        root = self.viewer.getNaviCubeNode()
        self.assertIsNotNone(root, "the viewer has no navigation cube")
        self.assertEqual(
            root.getNumChildren(), 2, "the cube root should hold a callback and the cube node"
        )
        return root.getChild(1)

    def cube_type(self):
        return self.cube_node().getTypeId().getName().getString()


class TestCubeStyle(ViewCubeTestBase):
    def test_a_fresh_install_uses_the_othercad_cube(self):
        self.group.RemInt("CubeStyle")
        process_events()
        self.assertEqual(self.cube_type(), "SoViewCube")

    def test_the_style_swaps_live(self):
        self.group.SetInt("CubeStyle", 1)
        process_events()
        self.assertEqual(self.cube_type(), "SoNaviCube", "Classic did not bring the old cube back")
        self.group.SetInt("CubeStyle", 0)
        process_events()
        self.assertEqual(self.cube_type(), "SoViewCube", "OtherCAD did not come back")

    def test_the_new_cube_gets_the_controllers_values(self):
        self.group.SetInt("CubeStyle", 0)
        self.view.viewIsometric()
        for _ in range(20):
            process_events()
        cube = self.cube_node()
        self.assertGreater(
            cube.viewportRect.getValue()[2], 0.0, "the controller never gave the cube a viewport"
        )
        # InactiveOpacity differs between profiles, so only check the cube is drawn at all.
        self.assertGreater(cube.opacity.getValue(), 0.0)

    def test_a_swapped_in_cube_is_drawn_straight_away(self):
        """The node swapped in gets the controller's viewport and state without a mouse move.

        Each direction starts from a view whose other node has never been drawn, so an
        unfed node still has its constructor's empty viewport."""
        for start, swapped_in in ((0, "SoNaviCube"), (1, "SoViewCube")):
            with self.subTest(start=start):
                self.group.SetInt("CubeStyle", start)
                doc = FreeCAD.newDocument("TestViewCubeSwap")
                try:
                    view = FreeCADGui.getDocument(doc.Name).ActiveView
                    for _ in range(10):
                        process_events()
                    root = view.getViewer().getNaviCubeNode()
                    self.group.SetInt("CubeStyle", 1 - start)
                    for _ in range(5):
                        process_events()
                    node = root.getChild(1)
                    self.assertEqual(node.getTypeId().getName().getString(), swapped_in)
                    self.assertGreater(
                        node.viewportRect.getValue()[2],
                        0.0,
                        "the %s swapped in was never given the controller's viewport" % swapped_in,
                    )
                    self.assertGreater(node.opacity.getValue(), 0.0)
                finally:
                    FreeCAD.closeDocument(doc.Name)


class TestHoverFade(ViewCubeTestBase):
    """The controls fade in over about 150 ms and out over about 250 ms."""

    def setUp(self):
        super().setUp()
        from PySide import QtCore, QtGui

        self.QtCore, self.QtGui = QtCore, QtGui
        self.group.SetInt("CubeStyle", 0)
        self.viewer.setNaviCubeCorner(1)  # top right
        self.view.viewFront()
        for _ in range(20):
            process_events()
        self.viewport = self.view.graphicsView().viewport()

    def _cube_centre(self):
        size = self.group.GetInt("CubeSize", 150)
        offset_x = self.group.GetInt("OffsetX", 0)
        offset_y = self.group.GetInt("OffsetY", 0)
        ratio = self.viewport.devicePixelRatioF()
        centre_x = self.viewport.width() - (offset_x / ratio + 0.55 * size)
        centre_y = offset_y / ratio + 0.55 * size
        return self.QtCore.QPoint(round(centre_x), round(centre_y))

    def _away(self):
        return self.QtCore.QPoint(20, self.viewport.height() - 20)

    def _move(self, pos):
        QtCore, QtGui = self.QtCore, self.QtGui
        event = QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            QtCore.QPointF(pos),
            QtCore.QPointF(self.viewport.mapToGlobal(pos)),
            QtCore.Qt.NoButton,
            QtCore.Qt.NoButton,
            QtCore.Qt.NoModifier,
        )
        QtGui.QGuiApplication.sendEvent(self.viewport, event)

    def _wait_for(self, predicate, timeout=0.6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            process_events(5)
            if predicate():
                return True
        return predicate()

    def _opacity(self):
        return self.cube_node().controlsOpacity.getValue()

    def test_entering_the_cube_fades_the_controls_in(self):
        self._move(self._away())
        self.assertTrue(self._wait_for(lambda: self._opacity() == 0.0))
        self._move(self._cube_centre())
        self.assertTrue(self.cube_node().controlsLive.getValue(), "controls not live on entering")
        seen = []
        self._wait_for(lambda: seen.append(self._opacity()) or seen[-1] >= 0.999, timeout=0.4)
        self.assertGreaterEqual(
            seen[-1], 0.999, "the controls did not reach full opacity in 400 ms"
        )
        self.assertTrue(
            any(0.0 < value < 0.999 for value in seen),
            "the controls jumped straight to full opacity instead of fading in: %r" % seen,
        )

    def test_a_fading_control_cannot_be_clicked(self):
        self._move(self._cube_centre())
        self._wait_for(lambda: self._opacity() >= 0.999)
        self._move(self._away())
        # The node's fields are written as the cube is drawn, so wait for the next frame.
        self.assertTrue(
            self._wait_for(lambda: not self.cube_node().controlsLive.getValue(), timeout=0.1),
            "the controls still answer clicks after leaving the cube",
        )
        self.assertGreater(
            self._opacity(), 0.0, "the controls were already gone: this did not catch a fade"
        )
        self.assertTrue(self._wait_for(lambda: self._opacity() == 0.0, timeout=0.5))

    def _click(self, pos):
        QtCore, QtGui = self.QtCore, self.QtGui
        for kind, buttons in (
            (QtCore.QEvent.MouseButtonPress, QtCore.Qt.LeftButton),
            (QtCore.QEvent.MouseButtonRelease, QtCore.Qt.NoButton),
        ):
            event = QtGui.QMouseEvent(
                kind,
                QtCore.QPointF(pos),
                QtCore.QPointF(self.viewport.mapToGlobal(pos)),
                QtCore.Qt.LeftButton,
                buttons,
                QtCore.Qt.NoModifier,
            )
            QtGui.QGuiApplication.sendEvent(self.viewport, event)
            process_events(20)

    def test_a_step_triangle_stays_until_the_pointer_leaves_the_cube(self):
        """After one 45-degree step the view is no longer face-on, but the triangles the user
        is clicking stay, so the next click steps again rather than snapping to a tile."""
        size = self.group.GetInt("CubeSize", 150)
        centre = self._cube_centre()
        north = self.QtCore.QPoint(centre.x(), round(centre.y() - size / 2 + 0.15 * size))
        self._move(centre)
        self._move(north)
        self.assertEqual(
            self.cube_node().hiliteId.getValue(), 27, "the North triangle is not under the pointer"
        )
        self._click(north)
        for _ in range(20):
            process_events()
        self.assertTrue(
            self.cube_node().trianglesLatched.getValue(), "the triangles went after one step"
        )
        self._move(self._away())
        self.assertTrue(
            self._wait_for(lambda: not self.cube_node().trianglesLatched.getValue(), timeout=0.3),
            "the triangles stayed latched after the pointer left the cube",
        )

    def test_leaving_the_view_fades_the_controls_out(self):
        self._move(self._cube_centre())
        self._wait_for(lambda: self._opacity() >= 0.999)
        leave = self.QtCore.QEvent(self.QtCore.QEvent.Leave)
        self.QtGui.QGuiApplication.sendEvent(self.viewport, leave)
        self.assertTrue(
            self._wait_for(lambda: self._opacity() == 0.0, timeout=0.5),
            "the controls stayed up after the pointer left the view",
        )


class TestCubeStylePreference(unittest.TestCase):
    """The preferences dialog is modal and its .ui is compiled into the binary, so this reads
    the page's source; test_the_style_swaps_live covers what the parameter then does."""

    def _repo_root(self):
        import os

        here = os.path.dirname(os.path.abspath(__file__))
        while True:
            if os.path.exists(os.path.join(here, ".git")):
                return here
            parent = os.path.dirname(here)
            if parent == here:
                return None
            here = parent

    def test_the_navigation_page_offers_the_cube_style(self):
        import os
        import xml.etree.ElementTree as ElementTree

        root = self._repo_root()
        if root is None:
            self.skipTest("not running from a source checkout")
        path = os.path.join(root, "src", "Gui", "PreferencePages", "DlgSettingsNavigation.ui")
        tree = ElementTree.parse(path)
        combo = next((w for w in tree.iter("widget") if w.get("name") == "naviCubeStyle"), None)
        self.assertIsNotNone(combo, "the Navigation page has no cube style combo")
        props = {p.get("name"): p for p in combo.findall("property")}
        self.assertEqual(props["prefEntry"].find("cstring").text, "CubeStyle")
        self.assertEqual(props["prefPath"].find("cstring").text, "NaviCube")
        items = [i.find("property/string").text for i in combo.findall("item")]
        self.assertEqual(items, ["OtherCAD", "Classic"], "item order must match CubeStyle 0 and 1")
