# SPDX-License-Identifier: LGPL-2.1-or-later

"""The bridge's tools that change the model.

Each change is one undo step named "Bridge: ...". The model is rebuilt afterwards, and
if that leaves a feature in error that was not before, the change is undone and the
errors are handed back, unless the caller asks to keep it.
"""

import ast
import contextlib
import difflib
import io
import math
import traceback

import FreeCAD

from BridgeTools import (
    DOCUMENT_ARG,
    ActionFailed,
    ToolError,
    _active_body,
    _document,
    _object,
    _value,
    tool,
)

MAX_OUTPUT = 20000

# Properties a rebuild touches on its own, not worth reporting as changed
QUIET_PROPERTIES = {"Shape", "Label2", "Visibility", "_Version", "AddSubShape", "SuppressedShape"}

KEEP_ARG = {
    "keep_on_error": {
        "type": "boolean",
        "description": "Keep the change even if the model then rebuilds with errors "
        "(default: undo it and report the errors).",
    }
}

POSITIONS = {"start": 1, "end": 2, "center": 3, "centre": 3, "mid": 3}


# -- running a change --------------------------------------------------------


class _Recorder:
    """Notes which objects a change creates, deletes and alters."""

    def __init__(self, doc):
        self.doc = doc
        self.created = []
        self.deleted = []
        self.changed = {}

    def _ours(self, obj):
        try:
            return obj.Document == self.doc
        except Exception:
            return False

    def slotCreatedObject(self, obj):
        if self._ours(obj):
            self.created.append(obj.Name)

    def slotDeletedObject(self, obj):
        if self._ours(obj):
            self.deleted.append(obj.Name)

    def slotChangedObject(self, obj, prop):
        if prop not in QUIET_PROPERTIES and self._ours(obj):
            self.changed.setdefault(obj.Name, set()).add(prop)


def _check_ready():
    """Refuse to change the model under an open task panel, as a script would break it."""

    try:
        import FreeCADGui
    except ImportError:
        return
    if FreeCADGui.Control.activeDialog():
        raise ToolError(
            "A task panel is open in OtherCAD (the user is editing something). Ask the "
            "user to finish or close it, then try again."
        )


def _error_entry(obj):
    entry = {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
    try:
        entry["error"] = obj.getStatusString()
    except Exception:
        pass
    if obj.isDerivedFrom("Sketcher::SketchObject"):
        entry["conflicting"] = list(obj.ConflictingConstraints)
        entry["redundant"] = list(obj.RedundantConstraints)
        entry["malformed"] = list(obj.MalformedConstraints)
    return entry


def _abort(doc):
    doc.abortTransaction()
    doc.recompute()


def change(doc, label, func, keep_on_error=False, summary=None):
    """Run func as one undo step, rebuild, and report or undo what it did.

    func may return a dict merged into the report; summary, if given, is called after
    the rebuild for more of it (a sketch's degrees of freedom, say).
    """

    _check_ready()
    broken_before = {o.Name for o in doc.Objects if not o.isValid()}
    recorder = _Recorder(doc)
    FreeCAD.addDocumentObserver(recorder)
    doc.openTransaction(f"Bridge: {label}")
    try:
        try:
            extra = func() or {}
        finally:
            # What the rebuild then touches is its own doing, not the caller's
            FreeCAD.removeDocumentObserver(recorder)
        doc.recompute()
    except ToolError as error:
        _abort(doc)
        if isinstance(error, ActionFailed):
            error.details["rolled_back"] = True
        raise
    except Exception as error:
        _abort(doc)
        text = "".join(traceback.format_exception_only(type(error), error)).strip()
        raise ActionFailed(f"{label} failed: {text}", {"rolled_back": True, "error": text})

    created = [n for n in dict.fromkeys(recorder.created) if doc.getObject(n) is not None]
    deleted = [n for n in recorder.deleted if n not in recorder.created]
    changed = {
        name: sorted(props)
        for name, props in recorder.changed.items()
        if name not in created and doc.getObject(name) is not None
    }
    errors = [_error_entry(o) for o in doc.Objects if not o.isValid() and o.Name not in broken_before]
    report = {"change": label, "created": created, "deleted": deleted, "changed": changed}
    report.update(extra)
    if errors:
        report["errors"] = errors
    if errors and not keep_on_error:
        _abort(doc)
        report["rolled_back"] = True
        raise ActionFailed(
            f"{label} left {len(errors)} object(s) in error, so it was undone", report
        )
    doc.commitTransaction()
    report["rolled_back"] = False
    if summary:
        report.update(summary())
    return report


# -- references --------------------------------------------------------------


def _split_ref(text):
    """'Pad:Face6' or 'Pad.Face6' into ('Pad', 'Face6')."""

    for sep in (":", "."):
        if sep in text:
            name, sub = text.rsplit(sep, 1)
            return name, sub
    return text, ""


def _element(doc, text):
    name, sub = _split_ref(text)
    obj = _object(doc, name)
    if sub:
        try:
            obj.Shape.getElement(sub)
        except Exception:
            raise ToolError(f"{obj.Name} has no {sub}") from None
    return obj, sub


def _body(doc, name=None, create=False):
    if name:
        body = _object(doc, name)
        if body.TypeId != "PartDesign::Body":
            raise ToolError(f"{body.Name} is a {body.TypeId}, not a body")
        return body
    body = _active_body(doc)
    if body is None:
        bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
        body = bodies[0] if bodies else None
    if body is None and create:
        body = doc.addObject("PartDesign::Body", "Body")
        try:
            import FreeCADGui

            view = FreeCADGui.getDocument(doc.Name).ActiveView
            if hasattr(view, "setActiveObject"):
                view.setActiveObject("pdbody", body)
        except Exception:
            pass
    if body is None:
        raise ToolError(f"{doc.Name} has no body")
    return body


def _body_of(obj):
    parent = obj.getParentGeoFeatureGroup()
    if parent is None or parent.TypeId != "PartDesign::Body":
        raise ToolError(f"{obj.Name} is not in a body")
    return parent


def _origin_plane(body, which):
    role = f"{which}_Plane"
    for feature in body.Origin.OriginFeatures:
        if getattr(feature, "Role", "") == role:
            return feature
    raise ToolError(f"{body.Name} has no {role}")


def _set_enum(obj, prop, value):
    allowed = obj.getEnumerationsOfProperty(prop)
    if value not in allowed:
        raise ToolError(f"{prop} must be one of {', '.join(allowed)}, not '{value}'")
    setattr(obj, prop, value)


# -- Python ------------------------------------------------------------------

_session = {}


def _namespace(doc):
    if not _session:
        import FreeCADGui
        import Part
        import Sketcher

        _session.update(
            {
                "__name__": "__bridge__",
                "FreeCAD": FreeCAD,
                "App": FreeCAD,
                "FreeCADGui": FreeCADGui,
                "Gui": FreeCADGui,
                "Part": Part,
                "Sketcher": Sketcher,
                "Vector": FreeCAD.Vector,
            }
        )
    _session["doc"] = doc
    return _session


def _clip(text):
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + f"\n... {len(text) - MAX_OUTPUT} more characters"


@tool(
    "run_python",
    "Run Python inside OtherCAD with the full FreeCAD API, for anything the other tools do "
    "not cover. FreeCAD (also App), FreeCADGui (Gui), Part, Sketcher, Vector and doc (the "
    "active document) are ready; names you define persist between calls. Printed output is "
    "returned, and the value of a final bare expression as result. The code runs as one "
    "undo step and the model is rebuilt afterwards; an exception or a rebuild error undoes "
    "it. It runs on the GUI thread, so never loop forever or wait for input.",
    {"code": {"type": "string"}, **DOCUMENT_ARG, **KEEP_ARG},
    required=("code",),
    readonly=False,
    destructive=True,
)
def run_python(code, document=None, keep_on_error=False):
    try:
        tree = ast.parse(code, "<bridge>", "exec")
    except SyntaxError as error:
        raise ToolError(f"SyntaxError: {error}") from None
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        last = ast.Expression(tree.body.pop().value)
    out = io.StringIO()
    doc = _document(document) if (document or FreeCAD.ActiveDocument) else None
    namespace = _namespace(doc)

    def run():
        result = {}
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                exec(compile(tree, "<bridge>", "exec"), namespace)
                if last is not None:
                    value = eval(compile(last, "<bridge>", "eval"), namespace)
                    if value is not None:
                        result["result"] = _clip(repr(value))
        except Exception as error:
            # Leave out this frame, so the traceback starts in the caller's code
            lines = traceback.format_exception(type(error), error, error.__traceback__.tb_next)
            raise ActionFailed(
                f"The code raised {type(error).__name__}: {error}",
                {"output": _clip(out.getvalue()), "traceback": _clip("".join(lines))},
            ) from None
        result["output"] = _clip(out.getvalue())
        return result

    if doc is None:
        # No document to hold an undo step yet, as when the code makes the first one
        _check_ready()
        result = run()
        result["documents"] = list(FreeCAD.listDocuments())
        return result
    return change(doc, "Python", run, keep_on_error)


# -- sketches ----------------------------------------------------------------


@tool(
    "new_sketch",
    "Start a sketch in a body, on an origin plane (XY, XZ, YZ) or on a planar face such as "
    "Pad:Face6 (find faces with describe_faces). Uses the active body, or the first; makes "
    "a body if there is none.",
    {
        "on": {"type": "string", "description": "XY, XZ, YZ, or Object:FaceN."},
        "body": {"type": "string", "description": "Body name or label."},
        "label": {"type": "string"},
        **DOCUMENT_ARG,
    },
    required=("on",),
    readonly=False,
)
def new_sketch(on, body=None, label=None, document=None):
    doc = _document(document)

    def make():
        plane = on.strip().upper().replace("_PLANE", "")
        target = _body(doc, body, create=True)
        if plane in ("XY", "XZ", "YZ"):
            support = (_origin_plane(target, plane), [""])
        else:
            obj, sub = _element(doc, on)
            if not sub.startswith("Face"):
                raise ToolError(f"Sketch on a face such as {obj.Name}:Face6, not '{on}'")
            if obj.Shape.getElement(sub).Surface.__class__.__name__ != "Plane":
                raise ToolError(f"{obj.Name}:{sub} is not flat, so a sketch cannot lie on it")
            support = (obj, [sub])
        sketch = target.newObject("Sketcher::SketchObject", "Sketch")
        sketch.AttachmentSupport = support
        sketch.MapMode = "FlatFace"
        if label:
            sketch.Label = label
        return {"sketch": sketch.Name, "body": target.Name}

    return change(doc, "New sketch", make)


def _point(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        raise ToolError(f"A point is [x, y], not {value!r}")
    return FreeCAD.Vector(float(value[0]), float(value[1]), 0)


def _geometry(item):
    """Part geometry for one sketch_add item, and the constraints that hold its shape."""

    import Part

    kind = str(item.get("type", "")).lower()
    if kind == "line":
        return [Part.LineSegment(_point(item["start"]), _point(item["end"]))], []
    if kind == "circle":
        circle = Part.Circle(_point(item["center"]), FreeCAD.Vector(0, 0, 1), float(item["radius"]))
        return [circle], []
    if kind == "arc":
        circle = Part.Circle(_point(item["center"]), FreeCAD.Vector(0, 0, 1), float(item["radius"]))
        start = math.radians(float(item["start_angle"]))
        end = math.radians(float(item["end_angle"]))
        return [Part.ArcOfCircle(circle, start, end)], []
    if kind == "point":
        return [Part.Point(_point(item["at"]))], []
    if kind in ("rectangle", "polygon"):
        if kind == "rectangle":
            x, y = _point(item["corner"]).x, _point(item["corner"]).y
            w, h = (float(v) for v in item["size"])
            corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        else:
            corners = [tuple(p) for p in item["points"]]
            if len(corners) < 3:
                raise ToolError("A polygon needs at least three points")
        n = len(corners)
        lines = [
            Part.LineSegment(_point(corners[i]), _point(corners[(i + 1) % n])) for i in range(n)
        ]
        # Relative to the first line; sketch_add shifts them to where the lines land
        constraints = [("Coincident", i, 2, (i + 1) % n, 1) for i in range(n)]
        if kind == "rectangle":
            constraints += [("Horizontal", 0), ("Horizontal", 2), ("Vertical", 1), ("Vertical", 3)]
        return lines, constraints
    raise ToolError(
        f"Unknown geometry type '{item.get('type')}': use line, circle, arc, point, "
        "rectangle or polygon"
    )


def _geo_index(value, new):
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.upper() == "H":
        return -1
    if text.upper() == "V":
        return -2
    if text.lower().startswith("new"):
        i = int(text[3:])
        if not 0 <= i < len(new):
            raise ToolError(f"{text} is not geometry added in this call (new0 to new{len(new) - 1})")
        return new[i]
    try:
        return int(text)
    except ValueError:
        raise ToolError(f"'{value}' is not a geometry index, newN, H or V") from None


def _constraint_args(entry, new):
    args = []
    for ref in entry.get("refs", []):
        if ref == "origin":
            args += [-1, 1]
            continue
        if not isinstance(ref, (list, tuple)):
            ref = [ref]
        args.append(_geo_index(ref[0], new))
        if len(ref) > 1:
            pos = ref[1]
            args.append(POSITIONS[pos.lower()] if isinstance(pos, str) else int(pos))
    if "value" in entry:
        value = float(entry["value"])
        args.append(math.radians(value) if entry.get("type") == "Angle" else value)
    return args


def _sketch(doc, name):
    sketch = _object(doc, name)
    if not sketch.isDerivedFrom("Sketcher::SketchObject"):
        raise ToolError(f"{sketch.Name} is a {sketch.TypeId}, not a sketch")
    return sketch


def _solver(sketch):
    return {
        "dof": sketch.DoF,
        "fully_constrained": sketch.DoF == 0,
        "conflicting": list(sketch.ConflictingConstraints),
        "redundant": list(sketch.RedundantConstraints),
    }


@tool(
    "sketch_add",
    "Add geometry and constraints to a sketch, in the sketch's own plane, in mm and "
    "degrees. Geometry: line {start, end}, circle {center, radius}, arc {center, radius, "
    "start_angle, end_angle} (counter-clockwise), point {at}, rectangle {corner, size} "
    "(four lines, bottom, right, top, left, already joined, horizontal and vertical), "
    "polygon {points} (closed); any of them can be construction: true. Geometry added in "
    "this call is numbered new0, new1, ... in the order made, so constraints can refer to "
    "it. A constraint is {type, refs, value?, name?}: type is Coincident, Horizontal, "
    "Vertical, Parallel, Perpendicular, Tangent, Equal, PointOnObject, Symmetric, Distance, "
    "DistanceX, DistanceY, Radius, Diameter, Angle or Block; refs are [geo] or [geo, pos] "
    "with pos start, end or center, geo an index, newN, H or V (the axes), or 'origin'. "
    "For example a 20 mm wide rectangle is DistanceX {refs: [[new0, start], [new0, end]], "
    "value: 20}. Returns the new indices and the degrees of freedom left.",
    {
        "sketch": {"type": "string"},
        "geometry": {"type": "array", "items": {"type": "object"}},
        "constraints": {"type": "array", "items": {"type": "object"}},
        **DOCUMENT_ARG,
        **KEEP_ARG,
    },
    required=("sketch",),
    readonly=False,
)
def sketch_add(sketch, geometry=None, constraints=None, document=None, keep_on_error=False):
    import Sketcher

    doc = _document(document)
    target = _sketch(doc, sketch)

    def add():
        new, added = [], []
        for item in geometry or []:
            parts, shape_constraints = _geometry(item)
            first = None
            for part in parts:
                index = target.addGeometry(part, bool(item.get("construction", False)))
                first = index if first is None else first
                new.append(index)
            for args in shape_constraints:
                kind, *refs = args
                shifted = [r + first if i % 2 == 0 else r for i, r in enumerate(refs)]
                added.append(target.addConstraint(Sketcher.Constraint(kind, *shifted)))
        for entry in constraints or []:
            kind = entry.get("type")
            try:
                index = target.addConstraint(Sketcher.Constraint(kind, *_constraint_args(entry, new)))
            except (TypeError, ValueError, RuntimeError) as error:
                raise ToolError(f"Constraint {entry} could not be made: {error}") from None
            if entry.get("name"):
                target.renameConstraint(index, entry["name"])
            added.append(index)
        return {"sketch": target.Name, "geometry": new, "constraints": added}

    return change(doc, "Sketch add", add, keep_on_error, summary=lambda: _solver(target))


@tool(
    "sketch_set_value",
    "Change a dimensional constraint's value (mm, or degrees for an angle), found by index "
    "or by name.",
    {
        "sketch": {"type": "string"},
        "constraint": {"anyOf": [{"type": "integer"}, {"type": "string"}]},
        "value": {"type": "number"},
        **DOCUMENT_ARG,
        **KEEP_ARG,
    },
    required=("sketch", "constraint", "value"),
    readonly=False,
)
def sketch_set_value(sketch, constraint, value, document=None, keep_on_error=False):
    doc = _document(document)
    target = _sketch(doc, sketch)
    if isinstance(constraint, str) and not constraint.isdigit():
        names = [c.Name for c in target.Constraints]
        if constraint not in names:
            raise ToolError(f"{target.Name} has no constraint named '{constraint}'")
        index = names.index(constraint)
    else:
        index = int(constraint)
    if not 0 <= index < len(target.Constraints):
        raise ToolError(f"{target.Name} has no constraint {index}")
    unit = "deg" if target.Constraints[index].Type == "Angle" else "mm"

    def set_value():
        target.setDatum(index, FreeCAD.Units.Quantity(f"{float(value)} {unit}"))
        return {"sketch": target.Name, "constraint": index}

    return change(doc, "Sketch value", set_value, keep_on_error, summary=lambda: _solver(target))


@tool(
    "sketch_remove",
    "Remove geometry and constraints from a sketch by index. Removing geometry removes its "
    "constraints too, and the indices after it move down.",
    {
        "sketch": {"type": "string"},
        "geometry": {"type": "array", "items": {"type": "integer"}},
        "constraints": {"type": "array", "items": {"type": "integer"}},
        **DOCUMENT_ARG,
        **KEEP_ARG,
    },
    required=("sketch",),
    readonly=False,
    destructive=True,
)
def sketch_remove(sketch, geometry=None, constraints=None, document=None, keep_on_error=False):
    doc = _document(document)
    target = _sketch(doc, sketch)

    def remove():
        for index in sorted(set(constraints or []), reverse=True):
            target.delConstraint(int(index))
        if geometry:
            target.delGeometries(sorted({int(i) for i in geometry}))
        return {"sketch": target.Name}

    return change(doc, "Sketch remove", remove, keep_on_error, summary=lambda: _solver(target))


# -- features ----------------------------------------------------------------

EXTRUDE_ARGS = {
    "profile": {"type": "string", "description": "The sketch to extrude."},
    "length": {"type": "number", "description": "mm (default 10)."},
    "type": {
        "type": "string",
        "description": "Length (default), ThroughAll, UpToFirst, UpToLast, UpToFace, TwoLengths.",
    },
    "reversed": {"type": "boolean", "description": "Extrude the other way."},
    "symmetric": {"type": "boolean", "description": "Half each side of the sketch plane."},
    "up_to_face": {"type": "string", "description": "Object:FaceN, for type UpToFace."},
    "label": {"type": "string"},
    **DOCUMENT_ARG,
    **KEEP_ARG,
}


def _extrude(kind, profile, length, type, reversed, symmetric, up_to_face, label, document, keep_on_error):
    doc = _document(document)
    sketch = _object(doc, profile)
    body = _body_of(sketch)

    def make():
        feature = body.newObject(f"PartDesign::{kind}", kind)
        feature.Profile = sketch
        if length is not None:
            feature.Length = float(length)
        wanted = type or ("UpToFace" if up_to_face else None)
        if wanted:
            _set_enum(feature, "Type", wanted)
        if up_to_face:
            obj, sub = _element(doc, up_to_face)
            feature.UpToFace = (obj, [sub])
        if reversed:
            feature.Reversed = True
        if symmetric:
            _set_enum(feature, "SideType", "Symmetric")
        if label:
            feature.Label = label
        sketch.Visibility = False
        return {"feature": feature.Name, "body": body.Name}

    return change(doc, kind, make, keep_on_error)


@tool(
    "pad",
    "Extrude a sketch into a solid, adding material (Fusion's Extrude, join). The pad "
    "becomes the body's tip.",
    EXTRUDE_ARGS,
    required=("profile",),
    readonly=False,
)
def pad(profile, length=None, type=None, reversed=False, symmetric=False, up_to_face=None,
        label=None, document=None, keep_on_error=False):
    return _extrude("Pad", profile, length, type, reversed, symmetric, up_to_face, label,
                    document, keep_on_error)


@tool(
    "pocket",
    "Extrude a sketch to cut material away (Fusion's Extrude, cut). It cuts into the solid "
    "from the sketch plane; use reversed if it cuts the wrong way.",
    EXTRUDE_ARGS,
    required=("profile",),
    readonly=False,
)
def pocket(profile, length=None, type=None, reversed=False, symmetric=False, up_to_face=None,
           label=None, document=None, keep_on_error=False):
    return _extrude("Pocket", profile, length, type, reversed, symmetric, up_to_face, label,
                    document, keep_on_error)


def _dress_up(kind, edges, size_prop, size, label, document, keep_on_error):
    doc = _document(document)
    if not edges:
        raise ToolError(f"A {kind.lower()} needs at least one edge")
    base, subs = None, []
    for text in edges:
        name, sub = _split_ref(text)
        if not sub:
            name, sub = None, text
        obj = _object(doc, name) if name else None
        if obj is not None and base is not None and obj != base:
            raise ToolError(f"All the edges of one {kind.lower()} must be on the same feature")
        base = obj or base
        subs.append(sub)
    if base is None:
        raise ToolError("Name the feature the edges are on, e.g. Pad:Edge3")
    body = _body_of(base)
    for sub in subs:
        try:
            base.Shape.getElement(sub)
        except Exception:
            raise ToolError(f"{base.Name} has no {sub}") from None

    def make():
        feature = body.newObject(f"PartDesign::{kind}", kind)
        feature.Base = (base, subs)
        setattr(feature, size_prop, float(size))
        if label:
            feature.Label = label
        return {"feature": feature.Name, "body": body.Name}

    return change(doc, kind, make, keep_on_error)


DRESS_UP_ARGS = {
    "edges": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Edges as Object:EdgeN, all on one feature (find them with describe_edges).",
    },
    "label": {"type": "string"},
    **DOCUMENT_ARG,
    **KEEP_ARG,
}


@tool(
    "fillet",
    "Round edges of a solid.",
    {"radius": {"type": "number", "description": "mm."}, **DRESS_UP_ARGS},
    required=("edges", "radius"),
    readonly=False,
)
def fillet(edges, radius, label=None, document=None, keep_on_error=False):
    return _dress_up("Fillet", edges, "Radius", radius, label, document, keep_on_error)


@tool(
    "chamfer",
    "Bevel edges of a solid by an equal distance.",
    {"size": {"type": "number", "description": "mm."}, **DRESS_UP_ARGS},
    required=("edges", "size"),
    readonly=False,
)
def chamfer(edges, size, label=None, document=None, keep_on_error=False):
    return _dress_up("Chamfer", edges, "Size", size, label, document, keep_on_error)


# -- properties, history and undo --------------------------------------------


def _convert(obj, prop, value):
    doc = obj.Document
    kind = obj.getTypeIdOfProperty(prop)
    if "PropertyLink" in kind and isinstance(value, str):
        return _object(doc, value) if value else None
    if "PropertyVector" in kind and isinstance(value, (list, tuple)):
        return FreeCAD.Vector(*[float(v) for v in value])
    if kind == "App::PropertyPlacement" and isinstance(value, dict):
        return FreeCAD.Placement(
            FreeCAD.Vector(*value.get("position", [0, 0, 0])),
            FreeCAD.Rotation(FreeCAD.Vector(*value.get("axis", [0, 0, 1])), value.get("angle_deg", 0)),
        )
    return value


@tool(
    "set_property",
    "Set an object's property, e.g. a Pad's Length to 15 or '15 mm', a Label, or a "
    "Placement {position, axis, angle_deg}; link properties take an object name. Or bind it "
    "to an expression such as 'Spreadsheet.width * 2' (an empty expression removes it).",
    {
        "name": {"type": "string", "description": "Object name or label."},
        "property": {"type": "string"},
        "value": {"description": "The new value."},
        "expression": {"type": "string"},
        **DOCUMENT_ARG,
        **KEEP_ARG,
    },
    required=("name", "property"),
    readonly=False,
)
def set_property(name, property, value=None, expression=None, document=None, keep_on_error=False):
    doc = _document(document)
    obj = _object(doc, name)
    if property not in obj.PropertiesList:
        close = difflib.get_close_matches(property, obj.PropertiesList, 3)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        raise ToolError(f"{obj.Name} has no property '{property}'.{hint}")
    if value is None and expression is None:
        raise ToolError("Give a value or an expression")

    def set_it():
        if expression is not None:
            obj.setExpression(property, expression or None)
        else:
            setattr(obj, property, _convert(obj, property, value))
        return {"object": obj.Name}

    def summary():
        return {"value": _value(getattr(obj, property))}

    return change(doc, f"Set {property}", set_it, keep_on_error, summary=summary)


@tool(
    "set_tip",
    "Move the body's tip, the timeline marker: features after it are rolled back (still "
    "there, but not built), and new features go in after it. Only a solid feature carries "
    "the tip, so naming a sketch rolls back to the solid feature before it, or to the "
    "start of the history if there is none.",
    {
        "feature": {"type": "string"},
        "body": {"type": "string", "description": "Leave out for the feature's own body."},
        **DOCUMENT_ARG,
    },
    required=("feature",),
    readonly=False,
)
def set_tip(feature, body=None, document=None):
    doc = _document(document)
    obj = _object(doc, feature)
    target = _body(doc, body) if body else _body_of(obj)
    if obj not in target.Group:
        raise ToolError(f"{obj.Name} is not in {target.Name}")

    def move():
        # As the timeline's playhead does: only a solid feature can carry the tip, so a
        # sketch rolls to the solid before it, and nothing before it leaves no tip at all
        group = target.Group
        solids = [o for o in group[: group.index(obj) + 1] if o.isDerivedFrom("PartDesign::Feature")]
        tip = solids[-1] if solids else None
        target.Tip = tip
        if tip is not None:
            tip.Visibility = True
        else:
            for other in group:
                if other.isDerivedFrom("PartDesign::Feature"):
                    other.Visibility = False
        return {"body": target.Name, "tip": tip.Name if tip else None}

    return change(doc, "Set tip", move)


@tool(
    "delete_object",
    "Delete an object. A feature that others depend on is not deleted unless keep_on_error "
    "is set, since they would break.",
    {"name": {"type": "string"}, **DOCUMENT_ARG, **KEEP_ARG},
    required=("name",),
    readonly=False,
    destructive=True,
)
def delete_object(name, document=None, keep_on_error=False):
    doc = _document(document)
    obj = _object(doc, name)

    def delete():
        parent = obj.getParentGeoFeatureGroup()
        target = obj.Name
        if parent is not None and parent.TypeId == "PartDesign::Body":
            parent.removeObject(obj)
        doc.removeObject(target)
        return {"deleted_object": target}

    return change(doc, "Delete", delete, keep_on_error)


def _history(doc):
    return {"undo": list(doc.UndoNames)[:10], "redo": list(doc.RedoNames)[:10]}


@tool(
    "undo",
    "Undo the last change in the document, whoever made it, the user included. Lists what "
    "can be undone and redone next.",
    {"steps": {"type": "integer", "description": "How many changes (default 1)."}, **DOCUMENT_ARG},
    readonly=False,
)
def undo(steps=1, document=None):
    doc = _document(document)
    _check_ready()
    done = []
    for _ in range(max(1, int(steps))):
        if not doc.UndoCount:
            break
        done.append(doc.UndoNames[0])
        doc.undo()
    if not done:
        raise ToolError("There is nothing to undo")
    doc.recompute()
    return {"undone": done, **_history(doc)}


@tool(
    "redo",
    "Redo changes that were undone.",
    {"steps": {"type": "integer", "description": "How many changes (default 1)."}, **DOCUMENT_ARG},
    readonly=False,
)
def redo(steps=1, document=None):
    doc = _document(document)
    _check_ready()
    done = []
    for _ in range(max(1, int(steps))):
        if not doc.RedoCount:
            break
        done.append(doc.RedoNames[0])
        doc.redo()
    if not done:
        raise ToolError("There is nothing to redo")
    doc.recompute()
    return {"redone": done, **_history(doc)}
