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

"""GUI regression tests for OtherCAD's flat solid modelling icons.

The icons live under :/icons/othercad with the same names as the stock ones they
replace, and BitmapFactory searches there before :/icons, so a command, a tree
item and a timeline marker all get the flat icon without any of them changing.
That only holds while the search order does, which is what these tests check: the
icon handed out for each name has to be the flat one, not the stock one.

To run tests:
    FreeCAD -t TestOtherCADIcons
"""

import unittest

import FreeCADGui
from PySide import QtCore, QtGui, QtSvg

ICON_DIR = ":/icons/othercad"
SIZE = 64
# Mean difference per channel, out of 255, between the icon handed out and the flat
# SVG drawn directly. Both are the same drawing rasterised twice, so only edge
# antialiasing tells them apart.
SAME = 6.0


def render(path):
    image = QtGui.QImage(SIZE, SIZE, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtCore.Qt.transparent)
    renderer = QtSvg.QSvgRenderer(path)
    painter = QtGui.QPainter(image)
    renderer.render(painter, QtCore.QRectF(0, 0, SIZE, SIZE))
    painter.end()
    return image


def image_of(icon):
    pixmap = icon.pixmap(SIZE, SIZE)
    return pixmap.toImage().convertToFormat(QtGui.QImage.Format_ARGB32_Premultiplied)


def difference(a, b):
    """Mean absolute difference per channel, sampled on every other pixel."""
    if a.size() != b.size():
        b = b.scaled(a.size(), QtCore.Qt.IgnoreAspectRatio, QtCore.Qt.SmoothTransformation)
    total, count = 0, 0
    for y in range(0, a.height(), 2):
        for x in range(0, a.width(), 2):
            ca, cb = a.pixelColor(x, y), b.pixelColor(x, y)
            total += (
                abs(ca.red() - cb.red())
                + abs(ca.green() - cb.green())
                + abs(ca.blue() - cb.blue())
                + abs(ca.alpha() - cb.alpha())
            )
            count += 4
    return total / count


class TestOtherCADIcons(unittest.TestCase):
    """Every flat icon is the one handed out for its name."""

    @classmethod
    def setUpClass(cls):
        if FreeCADGui.getMainWindow() is None:
            raise unittest.SkipTest("The icons need the GUI")
        # The stock icons, and the commands, come with the modules' resources.
        import PartDesignGui  # noqa: F401
        import SketcherGui  # noqa: F401

        cls.names = [
            name[: -len(".svg")]
            for name in QtCore.QDir(ICON_DIR).entryList(["*.svg"], QtCore.QDir.Files)
        ]

    def test_the_set_is_compiled_in(self):
        self.assertIn("PartDesign_Pad", self.names, "the flat icons are not in the resources")
        self.assertGreaterEqual(len(self.names), 48, "some of the flat icons are missing")

    def test_each_name_hands_out_the_flat_icon(self):
        wrong = []
        for name in self.names:
            icon = FreeCADGui.getIcon(name)
            if icon is None or icon.isNull():
                wrong.append("%s: no icon" % name)
                continue
            gap = difference(render("%s/%s.svg" % (ICON_DIR, name)), image_of(icon))
            if gap > SAME:
                wrong.append("%s: %.1f from the flat icon" % (name, gap))
        self.assertEqual(wrong, [], "names that still hand out another icon")

    def test_the_flat_icons_differ_from_the_stock_ones(self):
        """Otherwise the test above would pass with the stock icons in place."""
        for name in ("PartDesign_Pad", "PartDesign_Fillet", "PartDesign_Hole"):
            stock = ":/icons/%s.svg" % name
            self.assertTrue(QtCore.QFile.exists(stock), "no stock icon at " + stock)
            gap = difference(render("%s/%s.svg" % (ICON_DIR, name)), render(stock))
            self.assertGreater(gap, SAME * 3, name + " looks the same as the stock icon")

    def test_the_ribbon_command_shows_the_flat_icon(self):
        """The ribbon takes its buttons' icons from the commands' actions."""
        command = FreeCADGui.Command.get("PartDesign_Extrude")
        self.assertIsNotNone(command, "no PartDesign_Extrude command")
        actions = command.getAction()
        self.assertTrue(actions, "PartDesign_Extrude has no action")
        gap = difference(render(ICON_DIR + "/PartDesign_Pad.svg"), image_of(actions[0].icon()))
        self.assertLessEqual(gap, SAME, "the Extrude button does not show the flat icon")


if __name__ == "__main__":
    unittest.main()
