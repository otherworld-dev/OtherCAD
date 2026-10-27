# Changelog

All notable changes to OtherCAD are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

OtherCAD is a fork of FreeCAD. It was called FuCadUp up to 26.4.0, and began from FuCad
26.3.2. Changes that come in from upstream FreeCAD merges are not listed, only the work
done in this fork.

## [Unreleased]

### Added

- LLM Bridge, in the Tools menu, lets an LLM client read, look at and change the open
  model over MCP, on this computer only, at `http://127.0.0.1:7720/mcp`. It is off
  until switched on.
  - To read the model it can list documents, the timeline and an object's properties,
    measure shapes, find faces and edges by what they are (the top face, the vertical
    edges), read a sketch's constraints and degrees of freedom, see the selection and
    take screenshots.
  - To change it, it can make and save documents, start sketches on a plane or face,
    add geometry and constraints, change dimensions, pad, pocket, fillet and chamfer,
    set properties and expressions, move the timeline's tip, delete, undo and redo, and
    run Python for anything else.
  - It is asked to fully constrain its sketches and to tie positions to the part rather
    than to the origin. It can project other features' edges into a sketch and drive
    dimensions with expressions, so a hole stays put relative to the edge when the part
    is resized. A pad or pocket of a sketch that is not fully constrained comes with a
    warning.
  - The seam down a hole's wall is not offered as an edge to fillet.
  - Desktop apps that only start stdio servers reach it through
    `Mod/Bridge/BridgeStdio.py`, which needs only Python. If OtherCAD is not running
    yet, the tools appear once its bridge is switched on.
  - Each change is one undo step named "Bridge: ...". A change that leaves the model
    in error is undone and the errors are reported back. So is a pad or pocket that adds
    or removes no material, with a hint to reverse it.
  - Changes wait while a task panel is open.
  - The ReadOnly and AllowPython preferences limit what clients may do.
- Features can be suppressed from the timeline's right-click menu. A suppressed feature
  is drawn greyed out and struck through, and its tooltip says so.
- Repeat Last Command, at the top of the right-click menu in the 3D view and in the
  Edit menu, runs the last modelling command again and is named after it, for example
  Repeat Extrude.
- J starts a joint in an assembly, as in Fusion.
- A feature that fails to build has a red border on the timeline as well as its small
  error badge.
- When an edge or face a Fillet, Chamfer, Draft, Shell or face tool used has gone after
  an earlier feature was changed, the feature says which one and what to do, for example
  "Edge5 of Pad no longer exists. Edit Fillet to remove it or pick another.", and its
  panel lists the reference as missing so it can be removed and picked again.
- A feature panel says at its top why the feature cannot be built while a value is
  wrong, and again if OK is pressed on it, instead of only in the Report view.

### Changed

- FuCadUp is now OtherCAD. It has a new logo, a padded O in place of the F, and new
  executable names (OtherCAD and OtherCADCmd). Settings now live in an OtherCAD folder, so
  nothing carries over from FuCadUp. The theme, stylesheets and icons that came from FuCad
  are renamed to match.
- Extrude, Revolve, Hole, Sweep, Loft and Coil with nothing selected wait for a click
  in the 3D view, as in Fusion, instead of listing sketches by name. Click a region of
  a sketch to build from that region, or a curve to use the whole sketch. The body's
  sketches are shown while it waits, so another region of a sketch you have already
  used is one click away, and more regions can be added once the feature has started.
- L and the Line button in a sketch draw lines one after another from the end of the
  last, as Fusion's Line does, until Esc. M switches the next segment to an arc. The
  single line is still in the Create menu as Single Line (G, L).
- The editor for stored preferences is called Edit Stored Preferences instead of Edit
  Parameters, so searching the commands for parameters no longer leads to it.
- The model tree now groups a body's contents into Sketches, Construction and History
  folders, with the origin kept on its own row. A row only goes grey when it is rolled
  back, and a hidden row just shows its crossed eye instead of going grey. Turn it
  off under Preferences > Display > UI, "Group body contents into folders".
- The timeline now shows the history of whichever body you last selected, not just the
  active one, and acting on it from there activates that body first.

### Fixed

- The New body operation of Extrude, Revolve, Sweep, Loft, Coil and the primitives now
  makes a new body. Before, the body the feature was made in lost everything that came
  before it and no new body appeared. On OK the feature moves into a body of its own,
  which becomes the active one, and the whole thing is one undo step.
- Select Other on the ribbon, in a menu or from the command palette did nothing, as it
  looked under the pointer while the pointer was on the button. It now waits for a click
  in the 3D view and opens its menu there. Esc stops it waiting.
- A sketch dimension that would over-constrain the sketch is added as a driven dimension,
  as in Fusion, with a note in the status bar. Before, it went in as a driving one, and
  typing a different value into it left the sketch in conflict with none of its
  dimensions editable.
- The steps of a MultiTransform no longer show on the timeline as features of their own.
  Stepping the history could stop on one and make it the body's tip.
- Extrude and the other profile tools open ready to pick regions only when the sketch
  cannot be used whole, where the region they start on is just a stand-in. A sketch
  such as a square with a hole no longer opens in picking mode, and editing a feature
  no longer sets the first click to replace the regions picked before.
- Moving a body's first feature to another body (Move object to other body in the tree)
  no longer empties the body it came from.
- The Tasks panel on the right-hand overlay is no longer cut off at the edge of the
  screen when a sketch's panels need more width than the overlay had. The overlay grows
  while they need it and goes back to its own width afterwards.

## [26.4.0] - 2026-09-25

The first FuCadUp release. It carries on from FuCad 26.3.2 with a new name, a reworked
ribbon and timeline, values shown in the 3D view while you edit, new pattern tools and a
new view cube. The fork is up to date with FreeCAD as of 9 September 2026.

### Added

- Values in the 3D view on feature gizmos, the Extrude arrow and the Revolve and taper
  angle handles show their value in a box on the dimension line, which you can type
  into directly. Enter finishes the feature, Tab moves to the next value and Esc cancels.
  It can be turned off in the preferences.
- In the Sketcher a dimension's value can be typed into a box on the dimension itself,
  rather than in a separate dialog. Double-clicking an existing value opens the same box,
  including while a constraint tool is open, and the whole value is selected so typing
  replaces it.
- The Measure tool shows the measurement under the cursor while you hover, before
  anything is picked.
- Create Sketch waits for a click on a face or plane to sketch on, the same as Fusion,
  instead of asking in a dialog first.
- Sketcher snapping to the grid and to key points (origin, vertices, crossings, midpoints
  and quadrants). Grid snapping only catches the cursor within 8 px of a grid line so it
  still moves freely in between, and geometry snaps take priority over the grid. Each
  snap shows a small glyph.
- An adaptive grid on the XY plane in every 3D view, stepping in 10 mm (or 1 in) as you
  zoom. It can be turned off in the preferences.
- A Fusion navigation style in the navigation style pickers. Right-button orbit only
  starts once the pointer has moved a few pixels, so a slightly shaky right click still
  opens the marking menu.
- Ribbon panels fold into drop-downs when the window is narrow, and panels can be
  rearranged by drag and drop, with a way to reset the layout.
- A block at the left of the ribbon to switch workbench, and the ribbon now names the
  workspace rather than the workbench.
- A new view cube, flat and tiled 3x3 so edges and corners are easy to click, with home,
  roll and menu controls that fade in when you hover over it. The old cube is still
  available under Preferences as the Classic style.
- Linear and Polar Pattern have been reworked. Originals and directions are picked in the
  task panel fields, the pattern starts sized to the features it copies, spacing is set
  by dragging an arrow in the view, the polar angle by a handle, and the number of copies
  can be typed in a box beside the arrow. Copies are capped at 1000 per direction.
- A flat icon set for the SOLID tab and the face tools.

### Changed

- The application is renamed from FuCad to FuCadUp, with a new icon, splash screen,
  installer artwork and executable names (FuCadUp and FuCadUpCmd).
- The SOLID tab stays usable while editing a sketch. Choosing Extrude, Revolve and so on
  finishes the sketch first and then starts the command, where before those buttons were
  greyed out.
- The timeline is drawn as a strip without a title bar. Its rollback position is saved
  with the document, the arrows step back one feature at a time, and it only takes the
  Home and End keys while it has focus.
- Task dialogs keep their buttons in a footer and use the same names as the ribbon.
- Single-letter Fusion shortcuts fire ahead of the older multi-key shortcuts, and the
  modelling letters are kept out of the way while a sketch is being edited.
- The Part selection filters moved to U followed by V, E, F or C.
- Leave Sketch is Ctrl+Shift+Return, since Ctrl+Return is used by the on-view parameters.
- The Extrude arrow holds still when it is dragged back through the profile, and flips
  direction once per crossing rather than juddering.
- Windows builds now sign every binary in the bundle rather than about 40% of them, once
  signing is set up. Windows builds are unsigned for the time being.
- Sketcher snapping is now measured in real screen pixels. Before, a view wider than it is
  tall shrank every snap distance by its aspect ratio, so the 15 px grid band was about
  8 px in a 16:9 window. The default grid band is now 8 px, which feels the same as before
  in a 16:9 window, and points on a curve (midpoints, quadrants, crossings) are caught
  within the full 8 px snap radius rather than about 4.5 px.
- K then C adds a radius or diameter dimension (radius on an arc, diameter on a circle)
  in the default dimensioning mode. It was bound to a tool that only exists when the
  separate dimensioning tools are switched on, so it did nothing.
- The Left and Right arrow keys pan about 1.8 times further in a 16:9 window, the same
  distance as Up and Down. The old distance came from a rounding mistake.

### Fixed

- In a 3D view taller than it is wide, points were projected to the wrong place on
  screen, 166 px out in the portrait window it was measured in. This moved the pattern
  arrows away from where they were drawn, pivoted "orbit at cursor" somewhere other than
  under the cursor, made the bounding box orbit jump on the first drag and changed which
  facets the Mesh lasso kept. This is a FreeCAD bug.
- Pressing OK in Preferences wrote 10 mm into the Sketcher grid size, so a user working
  in inches got a metric grid from then on. An unset grid size now shows and keeps the
  unit schema's default (10 mm, or 1 inch in an imperial schema).
- Changing the unit system from the status bar with a document open left the 3D view's
  grid at its old spacing until something else rebuilt it.
- The colour bar (FEM results and other colour scales) kept the label width it first
  measured, so after the view changed size, or an image was saved at another size, the
  bar could sit too far right with its labels cut off. This is a FreeCAD bug.
- A zero-length camera move (for example `viewPosition` with a duration of 0) hung the
  application whenever view animations were turned on. This is a FreeCAD bug.
- Calling a 3D viewer method with arguments after `isSpinning()` from Python crashed the
  application, as the viewer kept one handler for both calling styles. This is a FreeCAD
  bug.
- The Tasks panel could be narrower than the dialog in it, which cut controls off with
  wider fonts such as DejaVu Sans on Linux. This is a FreeCAD bug.
- Leaving the event loop with `SystemExit` crashed during PySide clean-up and lost the
  output.
- PartDesign features from a FreeCAD document lost their add or subtract operation when
  opened. The Operation property is now read by name, so they keep it.
- An error after picking features for a pattern no longer closes FuCadUp.
- Esc during a pattern keeps the tool open, and a lost Esc key release no longer swallows
  the next one.
- The first-start page and the navigation indicator no longer overwrite the chosen
  navigation style.
- Hovering over an origin plane stays on the plane under the cursor.
- The view cube's lines no longer block clicks on the tiles under them, and its
  triangles stay correct on a rolled face.

## FuCad 26.3.2 and earlier

The FuCad releases by Fady Faheem (26.3.0 to 26.3.2, August 2026) that FuCadUp is built
on. They added the Fusion-style ribbon and FuCad Dark theme, a contextual Sketch tab,
the app bar in place of the title bar, the command palette on S, the marking menu, the
floating navigation bar and model browser, Fusion letter shortcuts, the feature timeline
with rollback, merged add and subtract operations with Press/Pull and the face tools,
picking a profile region by clicking inside it, and Insert Canvas. See
[FuCad](https://github.com/FadyFaheem/FuCad) for their history.
