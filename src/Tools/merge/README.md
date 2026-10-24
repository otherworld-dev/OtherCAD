# Merging FreeCAD upstream

OtherCAD tracks FreeCAD's `main`. Upstream lands roughly 85 commits a week, so
the gap grows quickly and the cost of closing it grows faster than the gap does.

## Cadence

Merge weekly. Conflicts do not scale linearly with how long you wait: at a week
they are mostly two branches adding a line to the same `CMakeLists.txt`, but at
a month both sides have had time to restructure the same code, and a file that
has been reorganised on both sides cannot be merged at all — it has to be taken
from upstream and have our changes reapplied by hand.

For reference, the 2026-09-10 merge covered four weeks (359 commits, 68 merged
PRs) and produced 24 conflicts, two of which were total rewrites.

## The steps

```sh
git fetch upstream main

# 1. Cost first, before deciding anything. Touches nothing.
python src/Tools/merge/preview_merge.py

# 2. Merge on a branch, never on main.
git checkout -b merge/upstream-$(date +%Y-%m)
git merge upstream/main

# 3. Resolve, then audit before building: both of these failures are silent.
python src/Tools/merge/check_merge.py

# 4. Submodules move with upstream.
git submodule update --init --recursive

# 5. Build and test (see the test note below), then fast-forward main.
```

## What the audit catches

`check_merge.py` compares committed blobs, following renames on both sides, and
reports four things:

- **GONE** — a file we had changed is nowhere in the merged tree. Usually a
  deliberate deletion; occasionally a resolution that lost it.
- **LOST** — the merged file is byte-identical to upstream's, so the resolution
  took their side wholesale. This caught a real one in the 2026-09-11 merge,
  where upstream had renamed the packaging directory out from under a file we
  had branded.
- **THINNED** — most of the lines we added to a file are gone. A prompt to look,
  not a verdict: upstream restructuring around us legitimately rewrites them.
- **ENDINGS** — endings that no longer match upstream's for that file. Most of
  this tree is CRLF while upstream drifts to LF file by file; matching them is
  what stops the next merge seeing a whole file as changed.

## What it does not catch

It is one check, not a substitute for building. Two failures got past it in the
merge it was written for, and both were found by the compiler minutes later:

- A declaration kept whose definition upstream's refactor removed. Upstream
  reparented a task panel onto a new base class; keeping "our" side of a hunk
  preserved a method declaration whose body had gone, and it linked no further.
- Code of ours deleted in an earlier merge that upstream later started using.
  A parallel enum was dropped as unused; upstream then built on it.

Neither is detectable by comparing our changes against upstream's. Build and run
the tests every time, and treat a clean audit as "nothing obviously dropped"
rather than "the merge is good".

## Where conflicts keep coming from

Roughly 440 source files differ from upstream. These are the ones upstream also
changes often, so they are worth checking first:

| Area | Ours |
| --- | --- |
| `Mod/Sketcher/Gui/ViewProviderSketch.cpp`, `EditModeCoinManager.cpp` | snapping, face preselection |
| `Gui/View3DInventorViewer.cpp`, `Gui/SoFCDB.cpp` | viewport grid, Fusion navigation style |
| `Gui/Application.cpp`, `App/Application.cpp` | ribbon, startup |
| `Mod/PartDesign/App/Feature*.cpp` | the merged additive/subtractive operation model |
| `*/CMakeLists.txt` | both sides adding files |

The PartDesign ones are structural rather than accidental. Making one tool both
additive and subtractive is the point of the fork, so every upstream change to
those features touches it. Expect that cost rather than trying to remove it.

## Testing after a merge

Qt's widget tests need the platform plugin on the environment or they fail in a
way that looks like a real breakage:

```sh
export QT_PLUGIN_PATH=$PWD/.pixi/envs/default/Library/lib/qt6/plugins
export QT_QPA_PLATFORM_PLUGIN_PATH=$QT_PLUGIN_PATH/platforms
pixi run -- ctest --test-dir build/release --output-on-failure
pixi run -- build/release/bin/OtherCADCmd.exe -t TestPartDesignApp
pixi run -- build/release/bin/OtherCAD.exe -t TestTimeline
```

Judge a GUI suite by its `Ran N tests` line rather than by the exit code alone.

If a run dies, `src/Tools/read_crash_report.py --latest` prints the most recent
crash report, and the exception code usually places the fault on its own.
