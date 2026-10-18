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

"""GUI regression tests for OtherCAD's Fusion-branded defaults (usability Task 5).

To run tests:
    FreeCAD -t TestOtherCADDefaults
"""

import os
import tempfile
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtWidgets

VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"
WEBSITES_PARAMS = "User parameter:BaseApp/Preferences/Websites"
NAVICUBE_PARAMS = "User parameter:BaseApp/Preferences/NaviCube"

FUSION_STYLE = "Gui::FusionNavigationStyle"


class TestNavigationStyleDefault(unittest.TestCase):
    """A fresh install (no NavigationStyle entry yet) must land on the Fusion style,
    not the upstream CAD style FreeCAD ships with."""

    def setUp(self):
        self.view_params = FreeCAD.ParamGet(VIEW_PARAMS)
        # Save whatever the user already had configured, if anything, and remove
        # the entry so the C++ default (View3DSettings.cpp) is what answers.
        self._had_value = "NavigationStyle" in self.view_params.GetStrings()
        self._saved_value = self.view_params.GetString("NavigationStyle", "")
        self.view_params.RemString("NavigationStyle")
        self.doc = None

    def tearDown(self):
        if self._had_value:
            self.view_params.SetString("NavigationStyle", self._saved_value)
        else:
            self.view_params.RemString("NavigationStyle")
        if self.doc is not None:
            FreeCAD.closeDocument(self.doc.Name)

    def _active_view(self, timeout_ms=2000):
        """A view freshly created for a new document can briefly still be None
        while the document/GUI machinery finishes wiring it up."""

        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            gui_doc = FreeCADGui.getDocument(self.doc.Name)
            view = gui_doc.ActiveView
            if view is not None:
                return view
            if time.monotonic() >= deadline:
                self.fail("No active 3D view appeared for the new document")
            FreeCADGui.updateGui()
            time.sleep(0.02)

    def test_navigation_style_defaults_to_fusion_when_absent(self):
        self.doc = FreeCAD.newDocument("TestOtherCADDefaultsNavigation")

        view = self._active_view()

        self.assertEqual(
            view.getNavigationType(),
            FUSION_STYLE,
            "A new view with no NavigationStyle preference set must default to "
            "the Fusion navigation style (View3DSettings.cpp), not the upstream "
            "CAD style",
        )


class TestReportBugUrl(unittest.TestCase):
    """ "Report an Issue" must point at this fork's tracker, not FreeCAD's.

    Std_ReportBug's URL only exists as a C++ string literal inside
    CommandStd.cpp: it is not exposed as a status tip, a whatsThis, or any
    other Python-observable property of the command's QAction (its status
    tip is the generic "Opens the bugtracker to report an issue"), and it is
    never pre-populated into a parameter that Python could read either -- the
    "IssuesPage" parameter is only ever written, with the URL as its value,
    as a side effect of the command actually running.

    So the only way to observe the real value is to run the command and
    capture what it hands to the OS's browser launcher. Gui::OpenURLInBrowser
    does this through Python's own "webbrowser" module (see
    src/Gui/OnlineDocumentation.cpp), so replacing that module's "open"
    function for the duration of the call intercepts the URL without ever
    spawning a real browser.
    """

    def setUp(self):
        self.websites_params = FreeCAD.ParamGet(WEBSITES_PARAMS)
        self._had_value = "IssuesPage" in self.websites_params.GetStrings()
        self._saved_value = self.websites_params.GetString("IssuesPage", "")
        self.websites_params.RemString("IssuesPage")

    def tearDown(self):
        if self._had_value:
            self.websites_params.SetString("IssuesPage", self._saved_value)
        else:
            self.websites_params.RemString("IssuesPage")

    def test_report_bug_opens_the_fork_tracker(self):
        import webbrowser

        opened_urls = []
        original_open = webbrowser.open
        webbrowser.open = lambda url, *args, **kwargs: opened_urls.append(url)
        try:
            FreeCADGui.runCommand("Std_ReportBug", 0)
        finally:
            webbrowser.open = original_open

        self.assertTrue(opened_urls, "Std_ReportBug did not open any URL")
        self.assertIn(
            "otherworld-dev/OtherCAD",
            opened_urls[0],
            "Std_ReportBug must open this fork's issue tracker, not FreeCAD/FreeCAD's",
        )

        # activated() also persists what it opened, so the fork's URL becomes
        # the parameter's effective value from here on.
        self.assertIn("otherworld-dev/OtherCAD", self.websites_params.GetString("IssuesPage", ""))


class TestDatumScaleDefault(unittest.TestCase):
    """A fresh install must draw the origin bigger than upstream draws it.

    Asserted as a ratio against the scale upstream ships rather than against a
    number, so the test says what the default is for -- an origin you can hit when
    you are picking a plane to sketch on -- without restating the sizes ViewParams
    multiplies together to get there.
    """

    def setUp(self):
        self.view_params = FreeCAD.ParamGet(VIEW_PARAMS)
        # Save whatever the user already had, then remove it so the C++ default
        # (ViewParams.cpp) is what answers.
        self._had_value = "DatumScale" in self.view_params.GetFloats()
        self._saved_value = self.view_params.GetFloat("DatumScale", 0.0)
        self.view_params.RemFloat("DatumScale")

    def tearDown(self):
        if self._had_value:
            self.view_params.SetFloat("DatumScale", self._saved_value)
        else:
            self.view_params.RemFloat("DatumScale")

    def drawnExtent(self, name):
        """How far an origin plane reaches, in a document made just now.

        A new document each time because ViewProviderPlane reads the scale as it
        attaches: the handler that resizes what is already on screen runs delayed,
        so a plane built before the parameter moved keeps the size it was built at.

        Read from the plane's own coordinates, which ViewProviderPlane::updatePlaneSize
        writes as DatumPlaneSize times the scale. A bounding box of the plane is no use:
        the datum sits under an SoShapeScale that keeps it a constant size on screen,
        and that factor depends on the camera and on whether the view has drawn yet.
        Under xvfb's software OpenGL it had not, and the box came back as nonsense such
        as -352914 or 4e32 while the same test passed on a desktop.
        """
        from pivy import coin

        doc = FreeCAD.newDocument(name)
        try:
            FreeCADGui.ActiveDocument = FreeCADGui.getDocument(doc.Name)
            lcs = doc.addObject("App::LocalCoordinateSystem", "LCS")
            doc.recompute()
            lcs.ViewObject.Visibility = True
            FreeCADGui.updateGui()

            plane = doc.getObject("XY_Plane")
            self.assertIsNotNone(plane, "the coordinate system grew no XY plane")

            search = coin.SoSearchAction()
            search.setType(coin.SoCoordinate3.getClassTypeId())
            search.setInterest(coin.SoSearchAction.ALL)
            # Whether the drawn square is on show depends on the display mode switch.
            search.setSearchingAll(True)
            # The coordinates are a part of the SoShapeScale node kit, which a search does
            # not enter unless told to. The setting is global, so it is put back after.
            searched_kits = coin.SoBaseKit.isSearchingChildren()
            coin.SoBaseKit.setSearchingChildren(True)
            try:
                search.apply(plane.ViewObject.RootNode)
            finally:
                coin.SoBaseKit.setSearchingChildren(searched_kits)

            # A path into a node kit ends at the kit unless it is read as a full path.
            paths = search.getPaths()
            reach = [
                point.getValue()[0]
                for index in range(paths.getLength())
                for point in coin.cast(paths[index], "SoFullPath").getTail().point.getValues()
            ]
            self.assertTrue(reach, "the XY plane has no coordinates to measure")
            return max(reach)
        finally:
            FreeCAD.closeDocument(doc.Name)

    def test_the_origin_is_drawn_three_times_the_size_upstream_draws_it(self):
        by_default = self.drawnExtent("TestOtherCADDefaultsDatumScaleDefault")

        self.view_params.SetFloat("DatumScale", 100.0)
        upstream = self.drawnExtent("TestOtherCADDefaultsDatumScaleUpstream")

        self.assertGreater(upstream, 0.0, "the plane is drawn with no extent at all")
        self.assertAlmostEqual(
            by_default,
            3.0 * upstream,
            delta=0.5,
            msg="a fresh install draws the origin plane out to %.1f, where upstream's "
            "scale gives %.1f: the default is not three times it" % (by_default, upstream),
        )


# The cube as upstream ships it, and the shape the fork draws instead
# (NaviCubeSettings::parameterChanged in View3DSettings.cpp).
UPSTREAM_CUBE_SHAPE = {
    "CubeStyle": 1,
    "ChamferSize": 0.12,
    "CubeSize": 132,
    "ShowCS": True,
    "BorderWidth": 1.1,
    "FontWeight": 0,
}
FORK_CUBE_SHAPE = {
    "CubeStyle": 1,
    "ChamferSize": 0.06,
    "CubeSize": 150,
    "ShowCS": False,
    "BorderWidth": 0.7,
    "FontWeight": 57,
}

# (list the names, read one, write one, remove one) for each kind of parameter.
PARAMETER_KINDS = (
    ("GetFloats", "GetFloat", "SetFloat", "RemFloat"),
    ("GetInts", "GetInt", "SetInt", "RemInt"),
    ("GetUnsigneds", "GetUnsigned", "SetUnsigned", "RemUnsigned"),
    ("GetBools", "GetBool", "SetBool", "RemBool"),
    ("GetStrings", "GetString", "SetString", "RemString"),
)
SETTER_FOR_TYPE = {bool: "SetBool", int: "SetInt", float: "SetFloat", str: "SetString"}


def snapshot_group(group):
    """Every entry in the group, as (setter, remover, name, value)."""
    entries = []
    for list_names, getter, setter, remover in PARAMETER_KINDS:
        for name in getattr(group, list_names)():
            entries.append((setter, remover, name, getattr(group, getter)(name)))
    return entries


def clear_group(group):
    for _, remover, name, _ in snapshot_group(group):
        getattr(group, remover)(name)


def restore_group(group, entries):
    clear_group(group)
    for setter, _, name, value in entries:
        getattr(group, setter)(name, value)


def differing_samples(first, second, tolerance=3):
    """How many sampled pixels differ between two renders by more than tolerance."""
    if first.size() != second.size():
        return first.width() * first.height()
    count = 0
    for y in range(0, first.height(), 2):
        for x in range(0, first.width(), 2):
            a = first.pixelColor(x, y)
            b = second.pixelColor(x, y)
            if (
                max(abs(a.red() - b.red()), abs(a.green() - b.green()), abs(a.blue() - b.blue()))
                > tolerance
            ):
                count += 1
    return count


class TestNaviCubeDefaults(unittest.TestCase):
    """A fresh install must draw the navigation cube the way the fork dresses it.

    The shape is a C++ default and so reaches every theme; the dark colours belong
    to the OtherCAD Dark preference pack, since the Light and Classic packs keep their
    own light cube. The cube is compared by rendering it: none of its geometry can
    be read from Python, as the chamfer is a private member of SoNaviCube rather
    than a field.

    These render the Classic cube (CubeStyle 1), whose chamfer and fonts they were
    written for; TestViewCube covers the OtherCAD cube.

    Every cube preference the user has set is put aside for the test and restored
    afterwards.
    """

    # Two renders of the same settings may still differ in a stray sample or two.
    SAME = 5
    # Below this, two settings are not visibly different on the cube.
    DIFFERENT = 20

    def setUp(self):
        self.group = FreeCAD.ParamGet(NAVICUBE_PARAMS)
        self._saved = snapshot_group(self.group)
        clear_group(self.group)

    def tearDown(self):
        restore_group(self.group, self._saved)

    def render(self, **settings):
        """A view rendered with exactly these cube preferences set.

        A new document each time: a view reads the cube preferences as it is
        created, and a cube built before an entry was removed would keep what
        the entry said, so a stale cube could pass for the defaults.
        """
        clear_group(self.group)
        for name, value in settings.items():
            getattr(self.group, SETTER_FOR_TYPE[type(value)])(name, value)

        doc = FreeCAD.newDocument("TestOtherCADDefaultsNaviCube")
        try:
            view = self.activeView(doc)
            previous, stable = None, 0
            deadline = time.monotonic() + 5.0
            while stable < 10 and time.monotonic() < deadline:
                FreeCADGui.updateGui()
                time.sleep(0.01)
                current = str(view.getCameraOrientation())
                stable = stable + 1 if current == previous else 0
                previous = current

            path = os.path.join(tempfile.gettempdir(), "TestOtherCADDefaultsNaviCube.png")
            view.saveImage(path, 480, 360, "Current")
            image = QtGui.QImage(path)
        finally:
            FreeCAD.closeDocument(doc.Name)

        self.assertFalse(image.isNull(), "the view could not be rendered")
        return image

    def activeView(self, doc, timeout_ms=2000):
        deadline = time.monotonic() + (timeout_ms / 1000.0)
        while True:
            view = FreeCADGui.getDocument(doc.Name).ActiveView
            if view is not None:
                return view
            if time.monotonic() >= deadline:
                self.fail("No active 3D view appeared for the new document")
            FreeCADGui.updateGui()
            time.sleep(0.02)

    def test_a_fresh_install_draws_the_fork_cube_shape(self):
        by_default = self.render(CubeStyle=1)
        fork = self.render(**FORK_CUBE_SHAPE)
        upstream = self.render(**UPSTREAM_CUBE_SHAPE)

        self.assertGreater(
            differing_samples(fork, upstream),
            self.DIFFERENT,
            "the fork and upstream cube shapes render alike, so this test cannot tell them apart",
        )
        self.assertLessEqual(
            differing_samples(by_default, fork),
            self.SAME,
            "with no cube preferences set, the cube is not drawn in the fork shape "
            "(bevel 0.06, 150 px, no axis cross, 0.7 edges, medium labels)",
        )

    def test_a_bevel_below_the_old_floor_still_changes_the_cube(self):
        """SoNaviCube used to clamp the chamfer to 0.05, so anything sharper was ignored."""
        at_old_floor = self.render(CubeStyle=1, ChamferSize=0.05)
        below_it = self.render(CubeStyle=1, ChamferSize=0.02)

        self.assertGreater(
            differing_samples(at_old_floor, below_it),
            self.DIFFERENT,
            "a 0.02 bevel draws the same cube as 0.05: the chamfer is still clamped at 0.05",
        )

    def test_labels_fall_back_to_the_application_font(self):
        """With no font chosen the labels used to be hard-coded Arial, whatever the UI used."""
        family = QtWidgets.QApplication.font().family()
        by_default = self.render(**FORK_CUBE_SHAPE)
        in_the_ui_font = self.render(FontString=family, **FORK_CUBE_SHAPE)

        self.assertLessEqual(
            differing_samples(by_default, in_the_ui_font),
            self.SAME,
            "with no font chosen, the cube labels are not drawn in the UI font %r" % family,
        )

        if family.lower() != "arial":
            in_arial = self.render(FontString="Arial", **FORK_CUBE_SHAPE)
            self.assertGreater(
                differing_samples(in_the_ui_font, in_arial),
                self.DIFFERENT,
                "labels in %r and in Arial render alike, so this test cannot tell the "
                "fallback apart" % family,
            )

    def test_the_othercad_dark_pack_dresses_the_cube_smoked(self):
        import xml.etree.ElementTree as ElementTree

        path = os.path.join(
            FreeCAD.getResourceDir(), "Gui", "PreferencePacks", "OtherCAD Dark", "OtherCAD Dark.cfg"
        )
        self.assertTrue(os.path.isfile(path), "no OtherCAD Dark preference pack at %s" % path)
        tree = ElementTree.parse(path)

        cube = next(
            (group for group in tree.iter("FCParamGroup") if group.get("Name") == "NaviCube"),
            None,
        )
        self.assertIsNotNone(cube, "the OtherCAD Dark pack has no NaviCube group")
        values = {entry.get("Name"): entry.get("Value") for entry in cube}
        accent = next(
            entry.get("Value")
            for entry in tree.iter("FCUInt")
            if entry.get("Name") == "ThemeAccentColor1"
        )

        self.assertNotIn(
            "Color",
            values,
            "the pack still sets NaviCube/Color, which nothing reads - the cube takes BaseColor",
        )
        self.assertEqual(
            values.get("EmphaseColor"),
            "2829625599",
            "cube edges, labels and controls are not the light grey #a8a8a8",
        )
        self.assertEqual(values.get("HiliteColor"), accent, "the cube hover is not the accent")
        self.assertEqual(values.get("InactiveOpacity"), "100", "the cube is not solid at rest")
        self.assertIn("BaseColor", values, "the pack leaves the cube faces at the light default")
        self.assertEqual(
            values.get("BaseColor"),
            "707406520",
            "the cube faces are not the smoked #2a2a2a at 72% alpha",
        )
        base = int(values["BaseColor"])
        brightest = max((base >> 24) & 0xFF, (base >> 16) & 0xFF, (base >> 8) & 0xFF)
        self.assertLess(brightest, 80, "the cube faces are not dark: BaseColor %08x" % base)
