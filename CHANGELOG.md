# Changelog

All notable changes to OtherCAD are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

OtherCAD is a fork of FreeCAD. It was called FuCadUp up to 26.4.0, and began from FuCad
26.3.2. Changes that come in from upstream FreeCAD merges are not listed, only the work
done in this fork.

## [Unreleased]

### Added

- The model tree shows which body is active, like the radio button on a Fusion component:
  every body row ends in a ring, filled on the active body, and clicking a ring makes that
  body active. The timeline names its body as well, marked the same way and in bold when
  it is the active one, and clicking the name activates the body it shows.
- AI Chat, in the Tools menu, is a panel where you talk to Claude about the open model
  without setting up an MCP client. It uses the plan you are signed in to in Claude Code,
  so Claude Code must be installed. Claude gets the LLM Bridge's tools and nothing else:
  no shell, files or web, and none of your Claude Code settings. Replies stream in, tool
  calls are shown as they run, and a reply can be stopped. The model can be changed
  mid-conversation. The panel follows the bridge's ReadOnly and AllowPython settings
  but does not need the bridge switched on. While a reply is on its way, Gwyn climbs
  out of his portal beside a word on what Claude is doing.
  - It can also use Claude through the Anthropic API with an API key: pick
    "Claude (API key)" and paste a key with Key…, or set ANTHROPIC_API_KEY. The
    model's tools run inside OtherCAD, and a request Claude declines is retried
    on another model. Opus 5.5, Sonnet 5.5 and Haiku 4.5 are offered.
  - Before the AI runs Python, a dialog shows the code and waits for Run or Don't run.
  - Stopping a reply no longer prints a ConnectionResetError traceback.
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
  - Calls take turns. A call that comes in while another one is still running, or while
    the model is recomputing, now waits for it to finish rather than running in the middle
    of it. A call that can't start within 20 s is turned away with nothing changed, and one
    that runs past 50 s is reported as still running so the client knows not to repeat it.
  - While a call runs, its name and arguments are kept in `BridgeLastCall.json` in the
    user config folder. If OtherCAD dies in the middle of a call, the next session warns
    about that call in the report view and tells the client which call it was, so it is
    not simply run again.
  - A new `cancel` tool stops the call that is running, such as a `run_python` loop that
    never ends: its Python is interrupted and its changes are undone, and the next call
    works as normal. A call the client gives up on (MCP `notifications/cancelled`, as
    clients send on their own timeout) is stopped the same way. Before, a runaway call
    held OtherCAD until it finished or the process died.
  - Cancel stops a boolean operation as well, such as a clash check between two
    coincident copies of a big assembly: the boolean raises "Boolean operation
    cancelled" and the call is undone. Scripts can do the same with
    `Part.requestBreak(True)`, which stops every boolean until `Part.requestBreak(False)`.
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
- Change Parameters, under Modify on the SOLID tab, lists the document's user
  parameters and the model's dimensions in one place, as Fusion's Parameters dialog
  does. User parameters can be added with a unit and a value or formula, renamed (the
  formulas that use one follow the new name), edited and deleted while nothing uses
  them; they live in a variable set called Parameters, made when the first one is
  added. Named sketch dimensions, feature sizes such as an extrude's distance, and
  values that formulas link can be edited there too. Each edit is one undo step and
  recomputes the model.
- The value boxes on feature gizmos take formulas, such as `Width * 2`: Enter, Tab or
  clicking away binds the value to it, and a formula that cannot be used is turned
  away with the reason. A value driven by a formula keeps its gizmo, shows the formula
  in its box and its value in the tooltip, and typing a number over the formula or
  dragging the gizmo replaces it.
- A feature that still builds, but only because an edge or face it used was lost and
  one in the same place was found instead, is drawn in yellow on the timeline, with a
  warning badge in the model tree. Its tooltip says what moved, for example "Edge5 of
  Pad was lost and Edge1, in the same place, is used instead.", and right-clicking it
  offers Edit to Reselect. The warning goes once the feature has been edited, or the
  change that caused it is undone.
- One Extrude or Revolve can be built from several profiles at once, as in Fusion:
  regions of different sketches, whole sketches and flat faces of the solid. While the
  panel's Select is on, the body's sketches are shown, and clicking a region, a sketch's
  curve or a flat face adds it; clicking it again takes it out. Selecting several before
  starting the command does the same. Extrude takes each profile from its own plane, so
  the extra ones must lie in planes parallel to the first. Revolve turns them all about
  the same axis. Profiles that overlap are merged. A feature with one profile is saved
  exactly as before.
- Features can be dragged along the timeline to move them earlier or later in their body,
  as in Fusion. A line shows where the feature will land, red when it cannot go there: a
  feature cannot move in front of something it is built on, nor past something built on
  it, and the status bar says which. A move is one undo step.
- Features side by side on the timeline can be grouped, as in Fusion: select them and
  choose Group from the right-click menu. A group folds into one marker, and a double
  click or Expand unfolds it. Its menu also has Rename Group and Ungroup. A folded group
  is dragged as one; a feature dragged out of an unfolded group leaves it, and one
  dropped between two of its members joins it. Groups are saved with the document and
  never change the model. A deleted feature drops out of its group, and an empty group
  goes. The step buttons and keys step over a folded group.
- Offset Face, Move Face and Press/Pull on a face put an arrow on the face, along its
  normal, with its distance in a box beside it, as in Fusion. Drag the arrow or type in
  the box. Move Face keeps its X, Y and Z fields and gains an Along normal field, which
  the arrow drives.
- Offset Face and Press/Pull work on curved faces too: the face grows or shrinks by the
  distance along its own normal, so offsetting a cylinder or a hole's wall changes its
  radius. Move Face still works only on flat faces, and says to use Offset Face for a
  curved one.
- Move (M, and Move on the ribbon) puts three arrows and three turning handles on the
  selected body or object, coloured by axis, with their values in boxes in the view, as
  Fusion's Move does. The body follows as you drag or type, turning about its middle, and
  the panel keeps X, Y and Z distance and angle fields. OK keeps the whole move as one
  undo step; Cancel puts it back. Picking a feature moves its body. With a face picked, M
  moves that face with Move Face instead of being greyed out. The numeric Placement
  dialog is still under Edit > Placement.

### Changed

- The timeline's playhead is easier to find and to grab. It has a grip at each end, like
  Fusion's history marker, and a grab area wider than its line, and it lights up under the
  mouse. Drag it to see the part as it was earlier in its history.
- A long body name on the timeline is cut short with "…", leaving the room for markers,
  and given in full when you hover over it.
- Orbiting and hovering over big models is much smoother. Under the default "Auto"
  render cache no object ever cached its drawing, so every frame sent every face of every
  object to the graphics card again. Objects now cache as "Distributed" does, as the viewer
  already intended; on a 1600-object model a frame takes about a sixth of the work. The
  first draw after opening takes a little longer while the caches are built. The corner
  axis cross also stopped rebuilding its letter textures on every frame.
- FreeCAD's Addon Manager is no longer part of OtherCAD. Add-ons OtherCAD wants are built
  in instead. A workbench folder dropped into the user's Mod folder still loads, and the
  manager can be built back with -DBUILD_ADDONMGR=ON.
- OtherCAD starts a little faster. Two things on the start screen made Qt look through
  every fallback font on the system: the arrow after the ribbon's workspace name, which was
  a character and is now drawn, and the first start page's list of languages, each named in
  its own script, which was laid out on every start although it is shown only once. The
  page is now built when it is opened.
- Big sketches solve much faster. Every solve checks the sketch for redundant and
  conflicting constraints, and in sketches over about 250 lines that check took around a
  second. It now takes a few milliseconds. On a 576-line test sketch a solve drops from
  1 s to 0.12 s, a recompute from 3.1 s to 1.1 s, and leaving the sketch from 2.7 s to 0.9 s.
- Big documents open and recompute faster. The timeline used to rebuild and restyle its
  markers again and again while a file was loading or a recompute was running. It now
  waits until the work is done, and it restyles only the markers whose look changed. Shape
  checks before each boolean now run on all cores. On a 1600-object model, opening drops
  from about 32 s to 21 s, and changing an early dimension in a 42-feature body from
  about 36 s to 21 s.
- A new feature goes into the body of what it is made from, as in Fusion. Sketching on a
  face, extruding a sketch or face, or filleting an edge of a body other than the active
  one makes that body active and works there, instead of refusing or asking about a copy.
  With no body active the selection's body is used, and a document without a body gets one
  silently with the first feature (one undo takes both back). The body picker is left
  only for a document with several bodies, none active and nothing selected. A new
  document still starts empty.
- An up-to face, axis, direction or other reference on another body comes into the
  feature's own body as a shape binder, without the copy/cross-reference question.
- Dragging the timeline's playhead rolls the model back and forward as it goes, as in
  Fusion, instead of only when it is let go. A whole drag is one undo step, however
  many features it passes.
- The Start page is redone. A sidebar holds a New design button, which starts a body
  ready to sketch on, with Open and the other new file types listed under it. Recent
  files and examples are cards with the thumbnail filling the top, a file type badge
  and, for recent files, how long ago they were saved. A filter narrows every list at
  once, and the Fusion-style shortcuts are shown as key caps.
- The Start page checkbox reads "Show this page on startup" and stores what it shows,
  in place of "Do not show this Start page again".
- The version number now follows FreeCAD's. The first three numbers are the FreeCAD
  version the build is based on (26.3.0, as of the 9 September 2026 merge), and a fourth
  number counts OtherCAD releases on top of it, so this release is 26.3.0.1. 26.4.0 was
  numbered ahead of FreeCAD, which would have let addons that need FreeCAD 26.4 install.
  Settings are kept per version, so copy `v26-4` to `v26-3` in the OtherCAD settings
  folder to keep them.
- FuCadUp is now OtherCAD, one of Otherworld Dev's Other family of tools, and takes the
  family's look: a night-blue icon with a teal ring round a sketched cube, a wordmark with
  "CAD" in bold teal, and new splash, About, installer and file icons to match. It also
  has new executable names (OtherCAD and OtherCADCmd). Settings now live in an OtherCAD folder, so
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
  - Pressing on the end of the last segment and dragging draws an arc tangent to it, as
    in Fusion. Letting go places the arc, and the lines carry on from its end.
- The editor for stored preferences is called Edit Stored Preferences instead of Edit
  Parameters, so searching the commands for parameters no longer leads to it.
- The model tree now groups a body's contents into Sketches, Construction and History
  folders, with the origin kept on its own row. A row only goes grey when it is rolled
  back, and a hidden row just shows its crossed eye instead of going grey. Turn it
  off under Preferences > Display > UI, "Group body contents into folders".
- The timeline now shows the history of whichever body you last selected, not just the
  active one, and acting on it from there activates that body first.

### Fixed

- When a long history scrolled, the timeline's scroll bar covered the bottom of the
  feature icons. The strip is now a little taller and the bar sits below them.
- `doc.recompute()` called while the document is already recomputing returns -1, and
  `obj.recompute(True)` returns False. Both skip the rebuild, but returned 0 and True as
  if all was well, so a script carried on with a model that had not been rebuilt.
- A recompute that runs past 30 seconds says so once in the report view, naming the
  object it has got to (the time is the `RecomputeWarnSeconds` preference under
  `BaseApp/Preferences/Document`). Before, a long one looked like a stuck document.
- An LLM Bridge change says when its rebuild was skipped because the document was still
  recomputing, or when objects still need a recompute after it, instead of reporting
  plain success.
- Closing a document while it recomputes no longer crashes or freezes OtherCAD. A close
  asked for in the middle of a recompute (from a timer, a script or a click handled while
  the rebuild processes events) used to delete the document under it, and a close on the
  main thread while the background recompute rebuilt it froze the GUI, each waiting for
  the other. Now the recompute stops at the next object and the document closes once it
  has finished, unless the document is opened again before then. Without the GUI the
  close is refused with an error instead.
- On Windows the background recompute ran the GUI's document updates on its own thread,
  because the hooks that hand them to the main thread never reached the App module there.
- The Offset Face and Move Face panels showed only the list of faces: their Offset and
  X, Y and Z fields never appeared, so the distance could not be changed there.
- A sketch point snapped to an arc's midpoint, a circle or arc quadrant, or a crossing
  now stays there. Before, all of these got a plain point-on-curve constraint and slid
  along the curve. An arc midpoint now adds a construction radius that the arc's ends are
  symmetric about, a quadrant puts the point on the circle and lines it up with the
  centre horizontally or vertically, and a crossing puts the point on both curves.
- An object bound to a spreadsheet alias now follows the alias after rows or columns are
  inserted above or before its cell. Before, changing the moved cell left the object alone
  and changing whatever cell took its old place updated it instead. The same happened
  when the object was bound before the sheet had first recomputed.
- Undoing rows inserted above aliased cells no longer breaks those aliases. Objects bound
  to them failed with "Property not found" until the file was closed and opened again.
- The Measure tool's hover values now show on Linux and macOS builds made with clang, where
  they were always missing.
- A click on the view cube that lands exactly on the line between two tiles now picks a
  tile instead of nothing.
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
- Revolve can intersect or make a new body when it goes up to a face, the first face or
  the last face. These only worked with an angle before, and the up-to types gave an
  error. Up to a face also works with nothing before it in the body, which is where a
  new body ends up.
- Revolve with Cut up to a face, like the old Groove, left only the material it should
  have taken away.
- Revolve up to a face with more than one profile failed with "Could not revolve the
  sketch!".
- A New body Revolve about an origin axis did not move into a body of its own on OK.

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
