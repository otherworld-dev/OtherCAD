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

"""Set preferences for the length of a GUI test, then put them back as they were.

A GUI test that depends on a preference has to set it rather than trust it. A
long-lived profile carries values that a fresh one never has, and a test run
starts from a fresh one on CI. Three suites passed for months on a developer's
machine and failed on every clean profile for that reason:

- the OtherCAD Dark preference pack is never applied during a test run, since the
  first-start theme selector that would apply it returns early for one, so its
  colours and stylesheet were only there because the profile had saved them;
- a default the fork has since changed (DatumScale went from 100 to 300) was only
  right where the profile stored it explicitly, and a test that recomputed it with
  the old fallback got the old answer everywhere else.

PinnedPreferences snapshots each entry it is given, including whether it existed
at all, sets the pinned value, and restore() puts every one back exactly: an entry
that was absent is removed rather than left behind with a value.
"""

import os
import xml.etree.ElementTree as ElementTree

import FreeCAD

# How each kind of entry is listed, read, written and removed on a ParameterGrp.
_ACCESSORS = {
    "bool": ("GetBools", "GetBool", "SetBool", "RemBool"),
    "unsigned": ("GetUnsigneds", "GetUnsigned", "SetUnsigned", "RemUnsigned"),
    "int": ("GetInts", "GetInt", "SetInt", "RemInt"),
    "float": ("GetFloats", "GetFloat", "SetFloat", "RemFloat"),
    "string": ("GetStrings", "GetString", "SetString", "RemString"),
}

# The element names a .cfg file uses for each kind.
_CFG_KINDS = {
    "FCBool": "bool",
    "FCUInt": "unsigned",
    "FCInt": "int",
    "FCFloat": "float",
    "FCText": "string",
}

_USER_PREFIX = "User parameter:"


class PinnedPreferences:
    """Pin some entries of one preference group, and restore them afterwards.

    `values` maps each entry name to (kind, value), where kind is one of bool,
    unsigned, int, float or string. Colours are unsigned, which is why the kind is
    given rather than guessed from the value.
    """

    def __init__(self, group_path, values):
        self.group_path = group_path
        self.values = dict(values)
        self._saved = None

    def pin(self):
        group = FreeCAD.ParamGet(self.group_path)
        self._saved = []
        for name, (kind, value) in self.values.items():
            listing, getter, setter, _ = _ACCESSORS[kind]
            present = name in getattr(group, listing)()
            previous = getattr(group, getter)(name) if present else None
            self._saved.append((name, kind, present, previous))
            getattr(group, setter)(name, value)
        return self

    def restore(self):
        if self._saved is None:
            return
        group = FreeCAD.ParamGet(self.group_path)
        for name, kind, present, previous in reversed(self._saved):
            _, _, setter, remover = _ACCESSORS[kind]
            if present:
                getattr(group, setter)(name, previous)
            else:
                getattr(group, remover)(name)
        self._saved = None


def othercad_dark(group_path, names=None):
    """One group of the OtherCAD Dark preference pack, as {name: (kind, value)}.

    Read from the pack file that ships with the build, so a test pins what a
    OtherCAD Dark user actually gets rather than a copy of it that can drift. `names`
    narrows it to those entries, and every one of them must be in the pack.
    """

    path = os.path.join(
        FreeCAD.getResourceDir(), "Gui", "PreferencePacks", "OtherCAD Dark", "OtherCAD Dark.cfg"
    )
    if not os.path.isfile(path):
        raise FileNotFoundError("no OtherCAD Dark preference pack at %s" % path)

    wanted = ["Root"] + group_path.replace(_USER_PREFIX, "").split("/")
    root = ElementTree.parse(path).getroot()

    def find(element, depth):
        for child in element:
            if child.tag == "FCParamGroup" and child.get("Name") == wanted[depth]:
                if depth == len(wanted) - 1:
                    return child
                return find(child, depth + 1)
        return None

    group = find(root, 0)
    if group is None:
        raise KeyError("the OtherCAD Dark pack has no %s group" % group_path)

    values = {}
    for entry in group:
        kind = _CFG_KINDS.get(entry.tag)
        if kind is None:
            continue
        raw = entry.get("Value")
        if raw is None:
            raw = (entry.text or "").strip()
        if kind == "bool":
            value = raw not in ("0", "", "false", "False")
        elif kind in ("unsigned", "int"):
            value = int(raw)
        elif kind == "float":
            value = float(raw)
        else:
            value = raw
        values[entry.get("Name")] = (kind, value)

    if names is not None:
        missing = [name for name in names if name not in values]
        if missing:
            raise KeyError("the OtherCAD Dark pack sets none of %s in %s" % (missing, group_path))
        values = {name: values[name] for name in names}
    return values
