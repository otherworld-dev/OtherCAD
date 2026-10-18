# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI visual regression test for selection/preselection ordering.

Run with:
    FreeCAD -t TestSelectionVisual
"""

from contextlib import suppress
import time
import unittest

import FreeCAD
import FreeCADGui
from FreeCADGui import Selection
import Part

from PinnedPreferences import PinnedPreferences, othercad_dark

try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide import QtGui as QtWidgets  # type: ignore


PART_PLANE_TYPE = f"{Part.__name__}::Plane"
VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"

# The overlay colours come from the OtherCAD Dark pack, which a test run never applies.
# Without it the built-in fallbacks are #0ac8ff for preselection and #00abff for
# selection, close enough that preselecting a selected face barely changes it, so the
# ordering these tests look for only shows up with the pack's colours in place.
OVERLAY_COLOURS = ("SelectionColor", "HighlightColor")


class TestSelectionVisual(unittest.TestCase):
    """Verify that live preselection draws above selection overlays."""

    _COLOR_DELTA_MIN = 0.15
    _COLOR_DELTA_RESTORE_MAX = 0.05

    def setUp(self):
        # Before the view exists, so it is built with these colours.
        pins = PinnedPreferences(VIEW_PARAMS, othercad_dark(VIEW_PARAMS, OVERLAY_COLOURS)).pin()
        self.addCleanup(pins.restore)

        self.doc = FreeCAD.newDocument("TestSelectionVisual")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        self.view = FreeCADGui.ActiveDocument.ActiveView
        self.viewer = self.view.getViewer()
        self._had_axis_cross = self.view.hasAxisCross()
        self.view.setAxisCross(False)

        self._had_navi_cube = self.viewer.isEnabledNaviCube()
        self.viewer.setEnabledNaviCube(False)

    def tearDown(self):
        with suppress(Exception):
            Selection.clearPreselection()
        with suppress(Exception):
            Selection.clearSelection()

        with suppress(Exception):
            self.view.setAxisCross(self._had_axis_cross)

        self._set_navi_cube_enabled(self._had_navi_cube)

        if FreeCAD.getDocument(self.doc.Name):
            FreeCAD.closeDocument(self.doc.Name)

    def test_preselection_overrides_selection_overlay(self):
        plane = self._create_test_plane()
        self._prepare_view()

        base_color = self._center_pixel_color()

        Selection.addSelection(plane)
        self._flush_gui()
        selection_color = self._center_pixel_color()

        Selection.setPreselection(plane, "Face1")
        self._flush_gui()
        preselection_color = self._center_pixel_color()

        self.assertGreater(
            self._color_distance(base_color, selection_color),
            self._COLOR_DELTA_MIN,
            msg=(
                "Selection overlay did not visibly change the rendered face. "
                f"base={base_color}, selection={selection_color}"
            ),
        )
        self.assertGreater(
            self._color_distance(selection_color, preselection_color),
            self._COLOR_DELTA_MIN,
            msg=(
                "Preselection did not visibly override the selection overlay. "
                f"selection={selection_color}, preselection={preselection_color}"
            ),
        )

    def test_selection_can_be_cleared(self):
        plane = self._create_test_plane()
        self._prepare_view()

        base_color = self._center_pixel_color()

        Selection.addSelection(plane)
        self._flush_gui()
        selection_color = self._center_pixel_color()

        Selection.clearSelection()
        self._flush_gui()
        cleared_color = self._center_pixel_color()

        self._assert_color_changed(
            base_color,
            selection_color,
            "Selection overlay did not visibly change the rendered face.",
        )
        self._assert_color_restored(
            base_color,
            cleared_color,
            "Clearing selection did not restore the original rendering.",
        )

    def test_preselection_can_be_cleared(self):
        plane = self._create_test_plane()
        self._prepare_view()

        base_color = self._center_pixel_color()

        Selection.setPreselection(plane, "Face1")
        self._flush_gui()
        preselection_color = self._center_pixel_color()

        Selection.clearPreselection()
        self._flush_gui()
        cleared_color = self._center_pixel_color()

        self._assert_color_changed(
            base_color,
            preselection_color,
            "Preselection overlay did not visibly change the rendered face.",
        )
        self._assert_color_restored(
            base_color,
            cleared_color,
            "Clearing preselection did not restore the original rendering.",
        )

    def test_whole_object_selection_matches_face_selection(self):
        """Selecting the whole object must paint its face the colour selecting the face does.

        The selection root tints a wholly selected subtree with an emissive glow in
        the selection colour, and SoBrepFaceSet also repaints the lit faces in it,
        so a whole-object selection came out at about twice the colour and clipped -
        #0696d7 rendered as #1cffff - while a single selected face, which only gets
        the lit repaint, showed the colour itself.
        """
        view_params = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/View")
        had_color = "SelectionColor" in view_params.GetUnsigneds()
        saved_color = view_params.GetUnsigned("SelectionColor", 0)
        # A mid colour, so doubling it overshoots visibly instead of hiding in a
        # channel that was already near the top.
        view_params.SetUnsigned("SelectionColor", self._pack_color((0.30, 0.45, 0.60)))
        try:
            plane = self._create_test_plane()
            self._prepare_view()
            # Preselection draws flat in its own colour; a pointer resting over the
            # plane would paint over both samples and hide the difference.
            self._set_preselection_mode("OFF")

            base_color = self._rendered_center_color()

            Selection.addSelection(plane, "Face1")
            self._flush_gui()
            face_color = self._rendered_center_color()

            Selection.clearSelection()
            Selection.addSelection(plane)
            self._flush_gui()
            whole_color = self._rendered_center_color()
        finally:
            self._set_preselection_mode("AUTO")
            if had_color:
                view_params.SetUnsigned("SelectionColor", saved_color)
            else:
                view_params.RemUnsigned("SelectionColor")

        # Without these, a capture that came back blank would make the two samples
        # equal and pass the comparison below.
        self._assert_color_changed(
            base_color, face_color, "Selecting the face did not visibly change it."
        )
        self._assert_color_changed(
            base_color, whole_color, "Selecting the whole object did not visibly change its face."
        )
        self.assertLess(
            self._color_distance(face_color, whole_color),
            self._COLOR_DELTA_RESTORE_MAX,
            msg=(
                "Selecting the whole object painted its face a different colour than "
                f"selecting the face itself. face={face_color}, whole={whole_color}"
            ),
        )

    def _set_preselection_mode(self, mode):
        """Switch this viewer's live preselection on or off.

        The EnablePreselection preference is only read when settings are applied,
        so the field on the viewer's SoFCUnifiedSelection node is set directly.
        """
        from pivy import coin

        node_type = coin.SoType.fromName(coin.SbName("SoFCUnifiedSelection"))
        self.assertFalse(node_type.isBad(), "SoFCUnifiedSelection is not a registered node type")
        search = coin.SoSearchAction()
        search.setType(node_type)
        search.setInterest(coin.SoSearchAction.FIRST)
        search.apply(self.viewer.getSoRenderManager().getSceneGraph())
        path = search.getPath()
        self.assertIsNotNone(path, "the viewer has no SoFCUnifiedSelection node")
        path.getTail().getField("preselectionMode").set(mode)

    def _rendered_center_color(self):
        """The centre pixel of an offscreen render of the view.

        grabFramebuffer() comes back all black in this build - the capture contract
        in TestView3DFramebufferCapture fails the same way - so this renders the
        scene offscreen instead.
        """
        image = self.viewer.renderToImage(width=400, height=300, samples=0)
        color = image.pixelColor(image.width() // 2, image.height() // 2)
        return (color.redF(), color.greenF(), color.blueF())

    @staticmethod
    def _pack_color(rgb):
        r, g, b = (int(round(channel * 255)) for channel in rgb)
        return (r << 24) | (g << 16) | (b << 8) | 0xFF

    def _create_test_plane(self):
        plane = self.doc.addObject(PART_PLANE_TYPE, "Plane")
        plane.Length = 40
        plane.Width = 40
        plane.ViewObject.ShapeColor = (0.66, 0.66, 0.74)
        self.doc.recompute()
        return plane

    def _prepare_view(self):
        self.view.viewTop()
        self._set_orthographic_if_supported()
        self.view.fitAll()
        self._flush_gui()

    def _set_orthographic_if_supported(self):
        with suppress(Exception):
            self.view.setCameraType("Orthographic")

    def _set_navi_cube_enabled(self, enabled):
        with suppress(Exception):
            self.viewer.setEnabledNaviCube(enabled)

    def _flush_gui(self):
        for _ in range(4):
            FreeCADGui.updateGui()
            QtWidgets.QApplication.processEvents()
            self.view.redraw()
            time.sleep(0.05)

    def _center_pixel_color(self):
        image = self.viewer.grabFramebuffer()
        color = image.pixelColor(image.width() // 2, image.height() // 2)
        return (color.redF(), color.greenF(), color.blueF())

    def _assert_color_changed(self, before, after, message):
        self.assertGreater(
            self._color_distance(before, after),
            self._COLOR_DELTA_MIN,
            msg=f"{message} before={before}, after={after}",
        )

    def _assert_color_restored(self, expected, actual, message):
        self.assertLess(
            self._color_distance(expected, actual),
            self._COLOR_DELTA_RESTORE_MAX,
            msg=f"{message} expected={expected}, actual={actual}",
        )

    @staticmethod
    def _color_distance(lhs, rhs):
        return sum((a - b) ** 2 for a, b in zip(lhs, rhs)) ** 0.5
