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

"""GUI regression tests for the colour of the navigation bar's icons.

The bar floats over the canvas carrying stock FreeCAD view icons, which draw their
geometry in a cyan family (#16d0d2, #34e0e2, #2bdbdd) that has nothing to do with
the accent the rest of the fork's chrome is painted in. The bar therefore recolours
the icons it shows onto the accent hue.

The recolour has to happen on the buttons. The QActions behind them are the shared
command actions the ribbon and the menus show as well, so writing to those would
drag the new colour across the whole application.

To run tests:
    FreeCAD -t TestNavigationBarIcons
"""

import re
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

from PinnedPreferences import PinnedPreferences, othercad_dark

MAIN_WINDOW_PARAMS = "User parameter:BaseApp/Preferences/MainWindow"
THEMES_PARAMS = "User parameter:BaseApp/Preferences/Themes"

# The bar is styled by OtherCAD.qss and coloured from the pack's accents. A test run
# never applies the OtherCAD Dark pack, so on any profile that had not saved it these
# tests read a bare stylesheet with no NavigationBar rules at all.
THEME_SETTINGS = ("StyleSheet", "Theme")
NAVIGATION_BAR_RULE = "QToolBar#NavigationBar QToolButton:hover"

# Measured over every icon the bar carries, FreeCAD's cyan covers hues 175 to 186
# and then stops dead: nothing until 196, and the blues those same icons are drawn
# with start at 206. The band sits in that gap. It has to stop short of where the
# accent lands too, or it could not tell a recoloured pixel from the cyan it came
# from - a dark one quantises down as far as 195 once it is over the plate.
CYAN_HUE_LOW = 170
CYAN_HUE_HIGH = 190

# Where the accent lands, wide enough for the whole blue corner of the wheel.
BLUE_HUE_LOW = 191
BLUE_HUE_HIGH = 235

# Below this a pixel is a grey and its hue says nothing.
MIN_SATURATION = 60

ICON_EXTENT = 18

# Anything less and the accent stops reading against what it sits on. WCAG asks
# this much of a graphic that carries meaning, which is what these icons are.
MIN_CONTRAST = 3.0

# The plate the buttons sit on, darken(@PrimaryColor, 20) in OtherCAD.qss.
PLATE_RED = 0x26
PLATE_GREEN = 0x26
PLATE_BLUE = 0x26


def image_of(icon):
    """The icon rendered at the size the bar asks for."""
    pixmap = icon.pixmap(QtCore.QSize(ICON_EXTENT, ICON_EXTENT))
    return pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32)


def visible_hsv(image):
    """Hue, saturation and value of every pixel as it lands on the bar's plate.

    Judged composited rather than raw. An anti-aliased edge arrives carrying an
    alpha of a few counts, and the premultiplied round trip a QPixmap makes of it
    rounds a dark accent blue straight back onto the cyan hue it came from: at an
    alpha of 8, (0, 22, 32) premultiplies to (0, 1, 1) and comes back (0, 32, 32).
    Over the plate those pixels are its grey, and a hue nobody can see is not a
    colour this bar can be said to draw.
    """
    pixels = []
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            alpha = color.alpha()
            if alpha == 0:
                continue
            weight = alpha / 255.0
            over = QtGui.QColor(
                round(color.red() * weight + PLATE_RED * (1 - weight)),
                round(color.green() * weight + PLATE_GREEN * (1 - weight)),
                round(color.blue() * weight + PLATE_BLUE * (1 - weight)),
            )
            hue, saturation, value, _ = over.getHsv()
            pixels.append((hue, saturation, value))
    return pixels


def count_in_band(pixels, low, high, min_saturation=MIN_SATURATION):
    return sum(
        1 for hue, saturation, _ in pixels if saturation >= min_saturation and low <= hue <= high
    )


def linear(channel):
    value = channel / 255.0
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    return (
        0.2126 * linear(color.red())
        + 0.7152 * linear(color.green())
        + 0.0722 * linear(color.blue())
    )


def contrast_ratio(first, second):
    lighter = max(relative_luminance(first), relative_luminance(second))
    darker = min(relative_luminance(first), relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


def style_block(sheet, selector):
    """The declarations the resolved stylesheet gives this selector."""
    index = sheet.find(selector)
    if index < 0:
        return ""
    opening = sheet.find("{", index)
    return sheet[opening : sheet.find("}", opening)]


def declared_color(block, pattern):
    found = re.search(pattern, block)
    return QtGui.QColor(found.group(1)) if found else None


class TestNavigationBarIcons(unittest.TestCase):
    """The bar's icons must read in the accent, without disturbing the shared actions."""

    def setUp(self):
        for pins in (
            PinnedPreferences(THEMES_PARAMS, othercad_dark(THEMES_PARAMS)),
            PinnedPreferences(
                MAIN_WINDOW_PARAMS, othercad_dark(MAIN_WINDOW_PARAMS, THEME_SETTINGS)
            ),
        ):
            pins.pin()
            self.addCleanup(pins.restore)
        self.waitForStyleSheet()

        self.doc = FreeCAD.newDocument("TestNavigationBarIcons")
        FreeCADGui.ActiveDocument = FreeCADGui.getDocument(self.doc.Name)
        FreeCADGui.activeDocument().activeView()
        self.bar = self.navigationBar()

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def waitForStyleSheet(self, timeout=5.0):
        """Setting StyleSheet reloads it from a parameter observer, not at once."""
        app = QtWidgets.QApplication.instance()
        deadline = time.monotonic() + timeout
        while NAVIGATION_BAR_RULE not in app.styleSheet():
            if time.monotonic() >= deadline:
                self.fail("OtherCAD.qss was not applied within %.0fs of being set" % timeout)
            FreeCADGui.updateGui()
            app.processEvents()
            time.sleep(0.02)

    def navigationBar(self):
        bars = [
            widget
            for widget in QtWidgets.QApplication.instance().allWidgets()
            if widget.objectName() == "NavigationBar" and widget.isVisible()
        ]
        self.assertTrue(bars, "no navigation bar is floating over the 3D view")
        return bars[-1]

    def buttons(self):
        """The bar's command buttons, paired with the action each one shows."""
        pairs = []
        for button in self.bar.findChildren(QtWidgets.QToolButton):
            action = button.defaultAction()
            if action is None or button.icon().isNull():
                continue
            pairs.append((button, action))
        self.assertTrue(pairs, "the navigation bar carries no command buttons")
        return pairs

    def buttonFor(self, command):
        for button, action in self.buttons():
            if action.objectName() == command:
                return button
        self.fail("the navigation bar has no '%s' button" % command)

    def test_no_button_icon_is_left_in_freecad_cyan(self):
        for button, action in self.buttons():
            pixels = visible_hsv(image_of(button.icon()))
            left = count_in_band(pixels, CYAN_HUE_LOW, CYAN_HUE_HIGH)
            self.assertEqual(
                left,
                0,
                "'%s' still draws %d cyan pixels" % (action.objectName(), left),
            )

    def test_the_cyan_turns_into_the_accent_blue(self):
        recoloured = 0
        for button, action in self.buttons():
            stock = count_in_band(visible_hsv(image_of(action.icon())), CYAN_HUE_LOW, CYAN_HUE_HIGH)
            if not stock:
                continue
            recoloured += 1
            blue = count_in_band(visible_hsv(image_of(button.icon())), BLUE_HUE_LOW, BLUE_HUE_HIGH)
            self.assertGreaterEqual(
                blue,
                stock,
                "'%s' lost %d of its %d cyan pixels instead of moving them onto the "
                "accent" % (action.objectName(), stock - blue, stock),
            )
        self.assertTrue(recoloured, "no icon on the bar was cyan to begin with")

    def test_draw_style_keeps_its_red_slash(self):
        pixels = visible_hsv(image_of(self.buttonFor("Std_DrawStyle").icon()))
        red = sum(
            1 for hue, saturation, _ in pixels if saturation >= 100 and (hue <= 12 or hue >= 348)
        )
        self.assertGreaterEqual(red, 4, "the slash across the draw style icon went blue")

    def test_axis_cross_keeps_its_coloured_arms(self):
        pixels = visible_hsv(image_of(self.buttonFor("Std_AxisCross").icon()))
        green = count_in_band(pixels, 80, 140, min_saturation=100)
        self.assertGreaterEqual(green, 3, "the axis cross lost its green arm")

    def test_every_button_state_keeps_the_accent_icons_legible(self):
        """The icons are the accent, so a state that fills with it buries them.

        The border of each state is drawn in the accent, which is the same colour
        the icons are recoloured onto, so it stands in for them here.
        """
        sheet = QtWidgets.QApplication.instance().styleSheet()
        for state in ("hover", "checked"):
            block = style_block(sheet, "QToolBar#NavigationBar QToolButton:%s" % state)
            background = declared_color(block, r"background-color:\s*(#[0-9a-fA-F]{6})")
            accent = declared_color(block, r"border:\s*\d+px\s+solid\s+(#[0-9a-fA-F]{6})")
            self.assertIsNotNone(background, ":%s declares no fill" % state)
            self.assertIsNotNone(accent, ":%s declares no accent border" % state)

            ratio = contrast_ratio(accent, background)
            self.assertGreaterEqual(
                ratio,
                MIN_CONTRAST,
                ":%s fills the button with %s, leaving the accent at %.2f:1 against "
                "it" % (state, background.name(), ratio),
            )

    def test_the_shared_command_actions_keep_their_stock_icons(self):
        """Recolouring the buttons must not reach the ribbon and the menus."""
        untouched = 0
        for _, action in self.buttons():
            stock = count_in_band(visible_hsv(image_of(action.icon())), CYAN_HUE_LOW, CYAN_HUE_HIGH)
            if stock:
                untouched += 1
        self.assertTrue(
            untouched,
            "every shared command action lost its cyan: the recolour was written "
            "onto the actions rather than onto the bar's buttons",
        )


if __name__ == "__main__":
    unittest.main()
