# SPDX-License-Identifier: LGPL-2.1-or-later

"""GUI regression tests for render caching of objects in the 3D view.

The Render Cache preference defaults to "Auto", which leaves caching to Coin's own
heuristics. The viewer switches those heuristics off (COIN_AUTO_CACHING=0) and falls back to
"Distributed" for its own separators, but every object's root was still set to AUTO, which
then never cached. Each frame sent every face of every object again, and a 1600-object model
drew at around 15 fps. An object's root now caches unless caching is switched off.

To run tests:
    FreeCAD -t TestRenderCaching
"""

import unittest

import FreeCAD
import FreeCADGui

VIEW_PARAMS = "User parameter:BaseApp/Preferences/View"


class TestRenderCaching(unittest.TestCase):
    def setUp(self):
        try:
            from pivy import coin
        except ImportError:
            raise unittest.SkipTest("pivy is not available")
        self.coin = coin
        self.doc = FreeCAD.newDocument("TestRenderCaching")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    def _expected(self):
        mode = FreeCAD.ParamGet(VIEW_PARAMS).GetInt("RenderCache", 0)
        return self.coin.SoSeparator.OFF if mode == 2 else self.coin.SoSeparator.ON

    def test_an_object_root_caches_its_rendering(self):
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        FreeCADGui.updateGui()
        root = box.ViewObject.RootNode
        self.assertEqual(
            root.renderCaching.getValue(),
            self._expected(),
            "under Auto the root was left on AUTO, which never caches with Coin's heuristics off",
        )

    def test_every_kind_of_object_root_caches(self):
        objects = [
            self.doc.addObject("Part::Cylinder", "Cylinder"),
            self.doc.addObject("PartDesign::Body", "Body"),
            self.doc.addObject("App::Link", "Link"),
        ]
        objects[2].LinkedObject = objects[0]
        self.doc.recompute()
        FreeCADGui.updateGui()
        for obj in objects:
            with self.subTest(obj=obj.TypeId):
                self.assertEqual(obj.ViewObject.RootNode.renderCaching.getValue(), self._expected())


if __name__ == "__main__":
    unittest.main()
