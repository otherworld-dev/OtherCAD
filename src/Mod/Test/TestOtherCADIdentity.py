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

"""Regression tests for the application's name and artwork.

The app was called FuCadUp until it was renamed OtherCAD. The name is set in
several places rather than one, so these tests check the ones a user sees: the
name the app reports, the folder its settings live in, and the icon, splash and
About artwork it asks for, which have to exist in the compiled resources.

To run tests:
    OtherCAD -t TestOtherCADIdentity
"""

import os
import unittest
from pathlib import Path

import FreeCAD

# Config keys that carry the brand. Paths are left out on purpose: the checkout
# a developer builds from can still be in a folder with the old name.
BRAND_KEYS = (
    "ExeName",
    "ExeVendor",
    "AppIcon",
    "SplashScreen",
    "AboutImage",
    "DesktopFileName",
    "MaintainerUrl",
    "CopyrightInfo",
)


class TestOtherCADIdentity(unittest.TestCase):
    """The app calls itself OtherCAD and nothing it shows still says FuCadUp."""

    def test_the_app_is_called_othercad(self):
        self.assertEqual(FreeCAD.ConfigGet("ExeName"), "OtherCAD")
        self.assertEqual(FreeCAD.ConfigGet("ExeVendor"), "OtherCAD")
        self.assertEqual(FreeCAD.ConfigGet("DesktopFileName"), "dev.otherworld.OtherCAD")

    def test_no_brand_setting_still_says_fucadup(self):
        for key in BRAND_KEYS:
            with self.subTest(key=key):
                self.assertNotIn("fucadup", FreeCAD.ConfigGet(key).lower())

    def test_the_banner_credits_freecad_and_fucad(self):
        banner = FreeCAD.ConfigGet("CopyrightInfo")
        self.assertTrue(banner.startswith("OtherCAD is a fork of FreeCAD"), banner)
        self.assertIn("FuCad", banner)

    def test_the_splash_text_uses_the_other_family_palette(self):
        # Teal for messages and muted grey for the version, as on the family brand sheet.
        self.assertEqual(FreeCAD.ConfigGet("SplashTextColor").upper(), "#22D3C4")
        self.assertEqual(FreeCAD.ConfigGet("SplashInfoColor").upper(), "#8A97A3")

    def test_settings_live_in_an_othercad_folder(self):
        if any(os.environ.get(name) for name in ("FREECAD_USER_HOME", "FREECAD_USER_DATA")):
            self.skipTest("the settings folder is overridden by the environment")
        parts = Path(FreeCAD.getUserAppDataDir()).parts
        self.assertIn("OtherCAD", parts)
        self.assertNotIn("FuCadUp", parts)


class TestOtherCADArtwork(unittest.TestCase):
    """The icon, splash and About images the app asks for are compiled in."""

    @classmethod
    def setUpClass(cls):
        import FreeCADGui

        if FreeCADGui.getMainWindow() is None:
            raise unittest.SkipTest("The artwork lives in the GUI resources")

    def resource(self, key):
        from PySide import QtCore

        name = FreeCAD.ConfigGet(key)
        found = [
            path
            for path in (f":/icons/{name}.svg", f":/icons/{name}.png")
            if QtCore.QFile.exists(path)
        ]
        self.assertTrue(found, f"{key} asks for '{name}', which is not in the resources")
        return found[0]

    def test_the_app_icon_is_compiled_in(self):
        self.assertTrue(self.resource("AppIcon").startswith(":/icons/othercad"))

    def test_the_splash_screen_is_compiled_in(self):
        self.resource("SplashScreen")

    def test_the_about_image_is_compiled_in(self):
        self.resource("AboutImage")


if __name__ == "__main__":
    unittest.main()
