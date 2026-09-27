"""Fusion letter shortcuts resolve without a chord wait and yield to sketch tools.

To run tests:
    FreeCAD -t TestFusionShortcuts
"""

import importlib
import time
import unittest
import FreeCAD
import FreeCADGui
import Part
from PySide import QtCore, QtGui, QtWidgets

# FreeCAD's PySide shim (Ext/PySide) re-exports only the modules it wraps, and
# QtTest is not one of them, so the binding module is imported directly. The
# classes are the same objects either way, so its QTest drives widgets that came
# through the shim just as well.
QtTest = None
# Only the Qt6 binding is tried. A machine can carry a half-installed PySide2
# beside it, whose import raises something other than ImportError, and anything
# raised here happens while the whole -t 0 run is still loading its tests, so it
# takes every suite down rather than this one. Whatever a candidate throws, it
# is not usable, and QtTest of None already skips the tests that need it.
for _binding in ("PySide6.QtTest", "PySide.QtTest"):
    try:
        QtTest = importlib.import_module(_binding)
        break
    except Exception:  # pragma: no cover - depends on which binding is installed
        continue

SKETCHER_PARAMS = "User parameter:BaseApp/Preferences/Mod/Sketcher"

# The Part selection filters, and the chords they were moved to. Their old
# "X, S"/"E, S"/"F, S"/"C, S" all began with a letter a Fusion tool now holds,
# and a Fusion letter fires at once rather than waiting for a chord that starts
# with it, so none of the four could complete. U is free - Draft's "U, P" is the
# only chord on it - and none of these second letters collides there.
FILTER_CHORDS = (
    ("Part_VertexSelection", "U, V"),
    ("Part_EdgeSelection", "U, E"),
    ("Part_FaceSelection", "U, F"),
    ("Part_RemoveSelectionGate", "U, C"),
)

# The commands that can dimension the radius of a selected circle from a "K, x"
# chord, most specific first; see _live_radius_chord below.
RADIUS_COMMANDS = ("Sketcher_ConstrainRadiam", "Sketcher_ConstrainRadius")


class TestFusionShortcuts(unittest.TestCase):
    def setUp(self):
        self.doc = FreeCAD.newDocument("FusionShortcuts")
        # CommandBase::getAction() does not build an action on demand, so a
        # Sketcher constraint command's action (and therefore its shortcut)
        # may not exist until the Sketcher workbench has been activated at
        # least once. Activate it before switching to PartDesignWorkbench,
        # which the Body/sketch test below needs.
        FreeCADGui.activateWorkbench("SketcherWorkbench")
        FreeCADGui.activateWorkbench("PartDesignWorkbench")

    def tearDown(self):
        FreeCAD.closeDocument(self.doc.Name)

    # -- helpers ---------------------------------------------------------

    def _shortcut_of(self, command):
        # Command.getShortcut() (CommandPyImp.cpp) reads the QAction's shortcut
        # and is null-safe: it returns "" rather than raising if the command
        # has no action yet, so a missing action fails the exact-value assert
        # below cleanly instead of raising IndexError out of getAction()[0].
        return FreeCADGui.Command.get(command).getShortcut()

    def _process_events(self, wait_ms=0):
        FreeCADGui.updateGui()
        app = QtWidgets.QApplication.instance()
        app.processEvents()
        if wait_ms:
            time.sleep(wait_ms / 1000.0)
            app.processEvents()

    def _key_window(self):
        """The QWindow a keystroke has to go through for an accelerator to resolve.

        A QKeyEvent handed to QApplication.sendEvent reaches the widget's own
        keyPressEvent but never QShortcutMap, so no QAction shortcut would fire and
        the test would say nothing about ShortcutManager::checkShortcut. QTest's
        QWindow overload goes in through qt_handleKeyEvent, the same entry point the
        platform plugin uses for a real key, and flushes the window-system queue
        before it returns.
        """

        if QtTest is None:
            raise unittest.SkipTest("This PySide build has no QtTest, so no key can be delivered")

        window = FreeCADGui.getMainWindow().windowHandle()
        if window is None:
            raise unittest.SkipTest("The main window has no native handle in this environment")

        return window

    def _send_key(self, key):
        QtTest.QTest.keyClick(self._key_window(), key, QtCore.Qt.NoModifier, 0)

    def _focus_the_view(self):
        """Put the keyboard focus where a modelling keystroke would land."""

        window = FreeCADGui.getMainWindow()
        window.activateWindow()
        window.raise_()

        target = window
        try:
            view = FreeCADGui.getDocument(self.doc.Name).ActiveView
            viewport = view.graphicsView().viewport()
            if viewport.width() > 0 and viewport.height() > 0:
                target = viewport
        except (AttributeError, RuntimeError):
            pass

        target.setFocus(QtCore.Qt.OtherFocusReason)
        self._process_events(50)
        return target

    @staticmethod
    def _visible_palette():
        """The command palette while it is on screen, or None.

        CommandPalette is a Qt::Popup top-level named "CommandPalette"
        (Gui/Ribbon/CommandPalette.cpp) and a singleton that hides rather than
        deletes itself, so the object outliving a close has to be filtered out by
        visibility rather than by existence.
        """

        popup = QtWidgets.QApplication.activePopupWidget()
        if popup is not None and popup.objectName() == "CommandPalette":
            return popup

        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.objectName() == "CommandPalette" and widget.isVisible():
                return widget

        return None

    def _close_the_palette(self):
        if self._visible_palette() is None:
            return

        self._send_key(QtCore.Qt.Key_Escape)
        self._process_events(50)

        palette = self._visible_palette()
        if palette is not None:
            palette.hide()
            self._process_events(50)

    # -- tests -----------------------------------------------------------

    def test_palette_has_priority_over_chords(self):
        # FreeCADGui.ShortcutManager is not exposed to Python, so read the
        # priority ShortcutManager::setPriority wrote straight from the
        # parameter group it uses (ShortcutManager.cpp: hShortcuts is
        # ".../Preferences/Shortcut", hPriorities is its "Priorities" group).
        hPriorities = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Shortcut/Priorities")
        prio = hPriorities.GetInt("Std_CommandPalette")
        self.assertGreater(prio, 0)

    def test_coincident_and_symmetric_left_bare_letters(self):
        # Sketcher_ConstrainCoincidentUnified and Sketcher_ConstrainCoincident
        # swap "K, K"/"K, Q" between them based on the UnifiedCoincident
        # preference (CommandConstraints.cpp), rather than both being forced
        # onto one value from DefaultShortcuts.cpp's table - so the expected
        # value here has to follow that same preference.
        hConstraints = FreeCAD.ParamGet(
            "User parameter:BaseApp/Preferences/Mod/Sketcher/Constraints"
        )
        unified = hConstraints.GetBool("UnifiedCoincident", True)
        expected = "K, K" if unified else "K, Q"
        self.assertEqual(self._shortcut_of("Sketcher_ConstrainCoincidentUnified"), expected)
        self.assertEqual(self._shortcut_of("Sketcher_ConstrainSymmetric"), "K, M")
        self.assertEqual(self._shortcut_of("Sketcher_CreateCircle"), "C")

    def test_l_draws_lines_one_after_another(self):
        # Fusion's Line carries on from the end of each segment until Esc, which is the
        # polyline here. The single line keeps its upstream chord.
        self.assertEqual(self._shortcut_of("Sketcher_CreatePolyline"), "L")
        self.assertEqual(self._shortcut_of("Sketcher_CreateLine"), "G, L")

    def test_part_selection_filters_use_the_free_u_prefix(self):
        """The four Part selection filters answer to U rather than to a Fusion letter."""

        for command, chord in FILTER_CHORDS:
            cmd = FreeCADGui.Command.get(command)
            self.assertIsNotNone(cmd, command + " is not registered")
            # Empty while the command has no action of its own, which is the normal
            # state for these four; the group below carries the live accelerator.
            reported = cmd.getInfo()["shortcut"]
            self.assertIn(reported, ("", chord), command)

        # Nothing puts the four in a menu or a toolbar of their own, so their
        # commands never build an action; the accelerator that actually fires is
        # the one PartCmdSelectFilter::createAction copies onto the entries of its
        # drop-down group, which is what is read back here.
        FreeCADGui.activateWorkbench("PartWorkbench")
        self._process_events(50)
        group = FreeCADGui.Command.get("Part_SelectFilter")
        self.assertIsNotNone(group, "Part_SelectFilter is not registered")
        actions = group.getAction()
        if len(actions) != len(FILTER_CHORDS):
            raise unittest.SkipTest(
                "The Part_SelectFilter group has not been built in this session "
                "({} entries), so its accelerators cannot be read".format(len(actions))
            )

        found = [action.shortcut().toString() for action in actions]
        self.assertEqual(found, [chord for _, chord in FILTER_CHORDS])

    def test_k_c_is_bound_in_the_default_dimensioning_mode(self):
        """K, C dimensions a circle without SeparatedDimensioningTools switched on.

        It used to sit on Sketcher_CompConstrainRadDia, a drop-down that only builds
        an action in the separated mode, so in the default mode the chord did nothing.
        """

        hGeneral = FreeCAD.ParamGet(SKETCHER_PARAMS + "/dimensioning")
        if hGeneral.GetBool("SeparatedDimensioningTools", False):
            self.skipTest("SeparatedDimensioningTools is on in this profile")
        self.assertEqual(self._shortcut_of("Sketcher_ConstrainRadiam"), "K, C")
        self.assertEqual(self._live_radius_chord(), ("Sketcher_ConstrainRadiam", "K, C"))

    def test_placement_and_measure_inactive_inside_sketch(self):
        body = self.doc.addObject("PartDesign::Body", "Body")
        sketch = body.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = (self.doc.getObject("XY_Plane"), [""])
        sketch.MapMode = "FlatFace"
        self.doc.recompute()
        FreeCADGui.Selection.addSelection(body)
        FreeCADGui.ActiveDocument.setEdit(sketch.Name)
        QtWidgets.QApplication.processEvents()
        try:
            self.assertFalse(FreeCADGui.Command.get("Std_Placement").isActive())
            self.assertFalse(FreeCADGui.Command.get("Std_Measure").isActive())
        finally:
            FreeCADGui.ActiveDocument.resetEdit()

    def test_s_opens_the_palette_without_the_chord_wait(self):
        """S puts the palette up on the keystroke itself, not ShortcutTimeout later."""

        self._key_window()  # skips early if keys cannot be delivered at all

        # Prove the palette can be found before making its absence a failure: it is
        # a singleton that does not exist at all until something asks for it.
        FreeCADGui.runCommand("Std_CommandPalette", 0)
        self._process_events(100)
        if self._visible_palette() is None:
            raise unittest.SkipTest(
                "No visible top-level named 'CommandPalette' after running "
                "Std_CommandPalette, so the palette cannot be located here"
            )
        self._close_the_palette()
        self.assertIsNone(self._visible_palette())

        self._focus_the_view()

        try:
            self._send_key(QtCore.Qt.Key_S)
            # Once, and with no wait: "S, B" and friends are still bound, so a
            # palette that only appeared after a sleep would be the chord timeout
            # expiring rather than checkShortcut flushing on the priority.
            QtWidgets.QApplication.instance().processEvents()

            palette = self._visible_palette()
            self.assertIsNotNone(
                palette, "S did not open the command palette on the keystroke itself"
            )
            self.assertTrue(palette.isVisible())
        finally:
            self._close_the_palette()

    def _live_radius_chord(self):
        """A "K, x" chord that is really bound, and the command it belongs to.

        DefaultShortcuts.cpp puts Sketcher_ConstrainRadiam on "K, C", but a
        command only carries a shortcut once something has built its action, so
        fall back to Sketcher_ConstrainRadius, which keeps its own "K, R", rather
        than pressing a chord that is bound to nothing.
        """

        for command in RADIUS_COMMANDS:
            chord = self._shortcut_of(command)
            if len(chord) == 4 and chord.startswith("K, ") and chord[3].isalpha():
                return command, chord

        raise unittest.SkipTest(
            "No 'K, x' chord is bound in this session ({}), so there is no chord "
            "to complete".format(
                ", ".join(
                    "{}={!r}".format(name, self._shortcut_of(name)) for name in RADIUS_COMMANDS
                )
            )
        )

    def test_k_chords_still_complete_inside_a_sketch(self):
        """A chord whose first key is not a Fusion letter still waits for its second."""

        self._key_window()  # skips early if keys cannot be delivered at all

        hSketcher = FreeCAD.ParamGet(SKETCHER_PARAMS)
        # A dimensional constraint otherwise opens a modal dialog asking for its
        # value, which would stall the run inside exec().
        asked = hSketcher.GetBool("ShowDialogOnDistanceConstraint", True)
        hSketcher.SetBool("ShowDialogOnDistanceConstraint", False)

        sketch = self.doc.addObject("Sketcher::SketchObject", "Sketch")
        sketch.addGeometry(
            Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), 10.0), False
        )
        self.doc.recompute()

        FreeCADGui.activateWorkbench("SketcherWorkbench")
        FreeCADGui.ActiveDocument.setEdit(sketch.Name, 0)
        self._process_events(200)
        try:
            command, chord = self._live_radius_chord()
            second = getattr(QtCore.Qt, "Key_" + chord[3].upper())

            self._focus_the_view()
            FreeCADGui.Selection.clearSelection()
            FreeCADGui.Selection.addSelection(self.doc.Name, sketch.Name, "Edge1")
            self._process_events(100)

            before = sketch.ConstraintCount

            # K on its own is bound to nothing, so the chord has to stay open for
            # its second key - which is the behaviour the Fusion letters give up.
            self._send_key(QtCore.Qt.Key_K)
            QtWidgets.QApplication.instance().processEvents()
            self.assertEqual(sketch.ConstraintCount, before, "K alone already changed the sketch")

            self._send_key(second)
            deadline = time.monotonic() + 0.6
            while sketch.ConstraintCount == before and time.monotonic() < deadline:
                self._process_events(20)

            self.assertEqual(
                sketch.ConstraintCount,
                before + 1,
                "{} ({}) did not dimension the selected circle".format(chord, command),
            )
        finally:
            FreeCADGui.ActiveDocument.resetEdit()
            self._process_events(50)
            hSketcher.SetBool("ShowDialogOnDistanceConstraint", asked)
