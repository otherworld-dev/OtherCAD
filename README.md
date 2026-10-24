<img src="/.github/images/othercad-banner.png" width="900" alt="OtherCAD"/>

### A Fusion 360-style fork of FreeCAD

OtherCAD is a fork of [FreeCAD](https://www.freecad.org), the open-source parametric
3D modeler. It began as a fork of [FuCad](https://github.com/FadyFaheem/FuCad) by Fady
Faheem, whose Fusion-style interface it grew out of. It keeps FreeCAD's geometry kernel, document model, Python API and
`.FCStd` file format intact, and reworks the user experience along the lines of
Fusion 360: a unified, task-driven interface instead of a workbench-per-discipline
layout.

Because the core is unchanged, OtherCAD opens existing FreeCAD documents and runs
existing FreeCAD macros and addons.

The name contracts **Fu**sion and Free**CAD**; the *Up* stands for
**U**nified **P**arametric — Fusion's task-driven workflow over FreeCAD's
parametric core.

[Upstream project](https://www.freecad.org) •
[Upstream documentation](https://wiki.freecad.org) •
[Upstream repository](https://github.com/FreeCAD/FreeCAD)

<img src="/.github/images/partdesign.png" width="800"/>

Status
------

OtherCAD is an early-stage fork under active development. There are no precompiled
releases yet; build from source.

Compiling
---------

OtherCAD uses FreeCAD's build system unchanged. See the
[Developers Handbook – Getting Started](https://freecad.github.io/DevelopersHandbook/gettingstarted/)
for platform-specific build instructions and dependencies.

Underlying technology
---------------------

* **OpenCASCADE** — the geometry kernel
* **Coin3D** — Open Inventor-compliant 3D scene representation
* **Python** — broad scripting API, compatible with FreeCAD's
* **Qt** — graphical user interface

Reporting issues
----------------

Report problems with OtherCAD on the [OtherCAD issue tracker](https://github.com/otherworld-dev/OtherCAD/issues).

If you can reproduce the same problem in upstream FreeCAD, please report it to the
[FreeCAD issue tracker](https://github.com/FreeCAD/FreeCAD/issues) instead, so the
fix benefits both projects.

Usage & getting help
--------------------

OtherCAD's scripting API and core concepts are FreeCAD's, so the FreeCAD documentation
applies:

- [Getting started](https://wiki.freecad.org/Getting_started)
- [Frequent questions](https://wiki.freecad.org/FAQ/en)
- [Scripting](https://wiki.freecad.org/Power_users_hub)
- [Developers Handbook](https://freecad.github.io/DevelopersHandbook/)
- [FreeCAD forum](https://forum.freecad.org)

Please do not report OtherCAD-specific problems to the FreeCAD forum or issue tracker;
OtherCAD is not affiliated with or endorsed by the FreeCAD project or the
[FreeCAD Project Association](https://fpa.freecad.org).

License and attribution
-----------------------

OtherCAD is a derivative work of FreeCAD and FuCad, Copyright (C) 2001-2026 FreeCAD
contributors and FuCad contributors.

OtherCAD is free and open-source software licensed under the GNU Lesser General Public
License, version 2.1 or (at your option) any later version (LGPL-2.1-or-later), the
same terms as upstream FreeCAD. See [LICENSE](LICENSE) for the full text and
[src/Doc/LICENSE.html](src/Doc/LICENSE.html) for details on the licenses of bundled
third-party components.

The names "FreeCAD" and "FuCad" and their logos belong to their respective projects and
are used here only to identify the upstream work from which OtherCAD is derived.
