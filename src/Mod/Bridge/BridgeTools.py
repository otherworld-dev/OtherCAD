# SPDX-License-Identifier: LGPL-2.1-or-later

"""The tools the LLM bridge offers, as plain functions with a JSON schema each.

They take and return JSON-friendly values, so they can be called and tested without
the HTTP server. A tool reports a problem the caller can act on by raising ToolError.
"""

import math
import os
import tempfile

import FreeCAD

TOOLS = {}

VIEWS = {
    "iso": "viewIsometric",
    "front": "viewFront",
    "rear": "viewRear",
    "top": "viewTop",
    "bottom": "viewBottom",
    "left": "viewLeft",
    "right": "viewRight",
}

# Properties that are big, binary or have their own tool
SKIPPED_PROPERTIES = {"Shape", "Proxy", "Geometry", "Constraints", "ExternalGeo", "_Body"}


class ToolError(Exception):
    """A problem with the request that the caller can fix, such as an unknown object."""


class Image:
    """A tool result that is a picture rather than JSON."""

    def __init__(self, data, mime_type="image/png"):
        self.data = data
        self.mime_type = mime_type


class Tool:
    def __init__(self, name, description, func, properties, required):
        self.name = name
        self.description = description
        self.func = func
        self.schema = {"type": "object", "properties": properties, "required": list(required)}

    def spec(self):
        return {"name": self.name, "description": self.description, "inputSchema": self.schema}


def tool(name, description, properties=None, required=()):
    def register(func):
        TOOLS[name] = Tool(name, description, func, properties or {}, required)
        return func

    return register


def call(name, arguments=None):
    if name not in TOOLS:
        raise KeyError(name)
    tool = TOOLS[name]
    arguments = arguments or {}
    unknown = sorted(set(arguments) - set(tool.schema["properties"]))
    if unknown:
        raise ToolError(f"{name} does not take {', '.join(unknown)}")
    missing = [a for a in tool.schema["required"] if a not in arguments]
    if missing:
        raise ToolError(f"{name} needs {', '.join(missing)}")
    return tool.func(**arguments)


# -- helpers -----------------------------------------------------------------

DOCUMENT_ARG = {
    "document": {
        "type": "string",
        "description": "Document name. Leave out for the active document.",
    }
}


def _document(name=None):
    if name:
        try:
            return FreeCAD.getDocument(name)
        except NameError:
            raise ToolError(f"No document named '{name}'") from None
    if FreeCAD.ActiveDocument is None:
        raise ToolError("No document is open")
    return FreeCAD.ActiveDocument


def _object(doc, name):
    obj = doc.getObject(name)
    if obj is None:
        found = doc.getObjectsByLabel(name)
        obj = found[0] if found else None
    if obj is None:
        raise ToolError(f"No object named or labelled '{name}' in {doc.Name}")
    return obj


def _round(value):
    return round(value, 6) if isinstance(value, float) else value


def _vector(v):
    return [_round(v.x), _round(v.y), _round(v.z)]


def _value(value, depth=0):
    """A property value as something json can write, or a short string when it is not."""

    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return _round(value) if math.isfinite(value) else str(value)
    if isinstance(value, FreeCAD.Vector):
        return _vector(value)
    if isinstance(value, FreeCAD.Placement):
        axis = value.Rotation.Axis
        return {
            "position": _vector(value.Base),
            "axis": _vector(axis),
            "angle_deg": _round(math.degrees(value.Rotation.Angle)),
        }
    if isinstance(value, FreeCAD.Units.Quantity):
        # Not UserString, which follows the user's decimals and locale
        return str(value)
    if isinstance(value, FreeCAD.DocumentObject):
        return value.Name
    if isinstance(value, (list, tuple)) and depth < 2:
        if len(value) > 50:
            return [_value(v, depth + 1) for v in value[:50]] + [f"... {len(value) - 50} more"]
        return [_value(v, depth + 1) for v in value]
    text = str(value)
    return text if len(text) <= 200 else text[:200] + "..."


def _state(obj):
    state = [s for s in obj.State if s != "Restore"]
    entry = {"state": state}
    if "Invalid" in state or "Error" in state:
        try:
            entry["error"] = obj.getStatusString()
        except Exception:
            pass
    return entry


def _active_body(doc):
    try:
        import FreeCADGui

        view = FreeCADGui.ActiveDocument.ActiveView if FreeCADGui.ActiveDocument else None
        body = view.getActiveObject("pdbody") if view and hasattr(view, "getActiveObject") else None
        if body is not None and body.Document == doc:
            return body
    except Exception:
        pass
    return None


def _shape(obj):
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        raise ToolError(f"{obj.Name} has no shape")
    return shape


# -- documents and objects ---------------------------------------------------


@tool("list_documents", "List the open documents and which one is active.")
def list_documents():
    active = FreeCAD.ActiveDocument.Name if FreeCAD.ActiveDocument else None
    return [
        {
            "name": doc.Name,
            "label": doc.Label,
            "file": doc.FileName or None,
            "active": doc.Name == active,
            "objects": len(doc.Objects),
        }
        for doc in FreeCAD.listDocuments().values()
    ]


@tool(
    "get_document",
    "List a document's objects with their type, label, parent, visibility and state, "
    "and the bodies in it.",
    DOCUMENT_ARG,
)
def get_document(document=None):
    doc = _document(document)
    objects = []
    for obj in doc.Objects:
        parent = obj.getParent() if hasattr(obj, "getParent") else None
        entry = {
            "name": obj.Name,
            "label": obj.Label,
            "type": obj.TypeId,
            "parent": parent.Name if parent else None,
            "visible": bool(getattr(obj, "Visibility", True)),
        }
        entry.update(_state(obj))
        objects.append(entry)
    body = _active_body(doc)
    return {
        "name": doc.Name,
        "label": doc.Label,
        "file": doc.FileName or None,
        "bodies": [o.Name for o in doc.Objects if o.TypeId == "PartDesign::Body"],
        "active_body": body.Name if body else None,
        "objects": objects,
    }


@tool(
    "get_timeline",
    "A PartDesign body's features in history order: the timeline. Shows which feature "
    "is the tip (features after it are rolled back) and any feature in error, with the "
    "message.",
    {
        "body": {
            "type": "string",
            "description": "Body name or label. Leave out for the active body, or the first.",
        },
        **DOCUMENT_ARG,
    },
)
def get_timeline(body=None, document=None):
    doc = _document(document)
    if body:
        target = _object(doc, body)
    else:
        target = _active_body(doc)
        if target is None:
            bodies = [o for o in doc.Objects if o.TypeId == "PartDesign::Body"]
            if not bodies:
                raise ToolError(f"{doc.Name} has no body")
            target = bodies[0]
    if target.TypeId != "PartDesign::Body":
        raise ToolError(f"{target.Name} is a {target.TypeId}, not a body")

    tip = target.Tip
    tip_index = target.Group.index(tip) if tip in target.Group else -1
    features = []
    for index, obj in enumerate(target.Group):
        entry = {
            "index": index,
            "name": obj.Name,
            "label": obj.Label,
            "type": obj.TypeId,
            "rolled_back": index > tip_index,
        }
        if getattr(obj, "Suppressed", False):
            entry["suppressed"] = True
        entry.update(_state(obj))
        features.append(entry)
    return {"body": target.Name, "tip": tip.Name if tip else None, "features": features}


@tool(
    "get_object",
    "An object's properties and their values, and any expressions bound to them. "
    "Shapes, sketch geometry and constraints have their own tools.",
    {"name": {"type": "string", "description": "Object name or label."}, **DOCUMENT_ARG},
    required=("name",),
)
def get_object(name, document=None):
    obj = _object(_document(document), name)
    properties = {}
    for prop in obj.PropertiesList:
        if prop in SKIPPED_PROPERTIES or prop == "ExpressionEngine":
            continue
        try:
            properties[prop] = _value(getattr(obj, prop))
        except Exception as error:
            properties[prop] = f"<unreadable: {error}>"
    expressions = {path: expr for path, expr in getattr(obj, "ExpressionEngine", [])}
    entry = {"name": obj.Name, "label": obj.Label, "type": obj.TypeId}
    entry.update(_state(obj))
    entry["properties"] = properties
    entry["expressions"] = expressions
    return entry


@tool(
    "get_shape",
    "Measure an object's shape: volume, area, bounding box, centre of mass and how many "
    "solids, faces and edges it has. Lengths in mm.",
    {"name": {"type": "string", "description": "Object name or label."}, **DOCUMENT_ARG},
    required=("name",),
)
def get_shape(name, document=None):
    shape = _shape(_object(_document(document), name))
    box = shape.BoundBox
    result = {
        "valid": shape.isValid(),
        "volume": _round(shape.Volume),
        "area": _round(shape.Area),
        "bound_box": {
            "min": [_round(box.XMin), _round(box.YMin), _round(box.ZMin)],
            "max": [_round(box.XMax), _round(box.YMax), _round(box.ZMax)],
            "size": [_round(box.XLength), _round(box.YLength), _round(box.ZLength)],
        },
        "solids": len(shape.Solids),
        "faces": len(shape.Faces),
        "edges": len(shape.Edges),
        "vertices": len(shape.Vertexes),
    }
    total = sum(s.Volume for s in shape.Solids)
    if total > 0:
        center = FreeCAD.Vector()
        for solid in shape.Solids:
            center += solid.CenterOfMass * (solid.Volume / total)
        result["center_of_mass"] = _vector(center)
    return result


def _parse_direction(text):
    if isinstance(text, (list, tuple)):
        v = FreeCAD.Vector(*[float(c) for c in text])
    else:
        text = text.strip().upper()
        sign = -1.0 if text.startswith("-") else 1.0
        axis = text.lstrip("+-")
        if axis not in ("X", "Y", "Z"):
            raise ToolError(f"Direction '{text}' is not +X, -X, +Y, -Y, +Z, -Z or [x, y, z]")
        v = FreeCAD.Vector(*[sign if axis == a else 0.0 for a in "XYZ"])
    if v.Length == 0:
        raise ToolError("A direction cannot be zero")
    return v.normalize()


def _face_entry(index, face):
    surface = face.Surface
    entry = {
        "face": f"Face{index}",
        "surface": surface.__class__.__name__,
        "area": _round(face.Area),
        "center": _vector(face.CenterOfMass),
    }
    u0, u1, v0, v1 = face.ParameterRange
    if entry["surface"] == "Plane":
        entry["normal"] = _vector(face.normalAt((u0 + u1) / 2, (v0 + v1) / 2))
    elif hasattr(surface, "Radius"):
        entry["radius"] = _round(surface.Radius)
        if hasattr(surface, "Axis"):
            entry["axis"] = _vector(surface.Axis)
    return entry


@tool(
    "describe_faces",
    "Describe an object's faces so one can be picked by what it is rather than by number: "
    "surface type, area, centre, and the outward normal of planar faces. Filter and sort to "
    "find a face, e.g. the top face is surface=Plane, normal=+Z, sort_by=z, descending, "
    "limit=1. Face names (Face7) are what sketches and features attach to.",
    {
        "name": {"type": "string", "description": "Object name or label."},
        "surface": {
            "type": "string",
            "description": "Only faces of this surface type: Plane, Cylinder, Cone, Sphere, "
            "Toroid, BSplineSurface, ...",
        },
        "normal": {
            "description": "Only planar faces facing this way: +X, -Z, ... or [x, y, z].",
            "anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "number"}}],
        },
        "sort_by": {"type": "string", "enum": ["area", "x", "y", "z"]},
        "descending": {"type": "boolean"},
        "limit": {"type": "integer", "description": "At most this many faces (default 50)."},
        **DOCUMENT_ARG,
    },
    required=("name",),
)
def describe_faces(
    name, surface=None, normal=None, sort_by=None, descending=False, limit=50, document=None
):
    shape = _shape(_object(_document(document), name))
    faces = [_face_entry(i, f) for i, f in enumerate(shape.Faces, 1)]
    if surface:
        faces = [f for f in faces if f["surface"].lower() == surface.lower()]
    if normal is not None:
        wanted = _parse_direction(normal)
        faces = [
            f
            for f in faces
            if "normal" in f and FreeCAD.Vector(*f["normal"]).dot(wanted) > 1 - 1e-6
        ]
    if sort_by:
        key = (
            (lambda f: f["area"])
            if sort_by == "area"
            else (lambda f, i="xyz".index(sort_by): f["center"][i])
        )
        faces.sort(key=key, reverse=bool(descending))
    total = len(faces)
    faces = faces[: max(1, int(limit))]
    return {"object": name, "matched": total, "faces": faces}


# -- sketches ----------------------------------------------------------------


def _geometry_entry(sketch, index, geo):
    kind = geo.__class__.__name__
    entry = {"index": index, "type": kind, "construction": bool(sketch.getConstruction(index))}
    if kind == "LineSegment":
        entry["start"] = _vector(geo.StartPoint)
        entry["end"] = _vector(geo.EndPoint)
    elif kind == "Point":
        entry["at"] = [_round(geo.X), _round(geo.Y), _round(geo.Z)]
    elif kind in ("Circle", "ArcOfCircle"):
        entry["center"] = _vector(geo.Center)
        entry["radius"] = _round(geo.Radius)
        if kind == "ArcOfCircle":
            entry["start"] = _vector(geo.StartPoint)
            entry["end"] = _vector(geo.EndPoint)
    elif hasattr(geo, "Center"):
        entry["center"] = _vector(geo.Center)
    return entry


def _constraint_entry(index, c):
    entry = {"index": index, "type": c.Type}
    if c.Name:
        entry["name"] = c.Name
    refs = []
    for geo, pos in ((c.First, c.FirstPos), (c.Second, c.SecondPos), (c.Third, c.ThirdPos)):
        if geo != -2000:  # GeoUndef
            refs.append([geo, pos])
    entry["refs"] = refs
    if c.Type in ("Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle", "Weight"):
        entry["value"] = (
            _round(math.degrees(c.Value)) if c.Type == "Angle" else _round(c.Value)
        )
        entry["driving"] = bool(c.Driving)
    return entry


@tool(
    "get_sketch",
    "A sketch's geometry, constraints and solver state: degrees of freedom left, and "
    "constraints that conflict, are redundant or malformed. Coordinates are in the "
    "sketch's own plane, in mm; angles in degrees. In refs, [geo, pos] uses pos 1 start, "
    "2 end, 3 centre; geo -1 is the H axis, -2 the V axis.",
    {"name": {"type": "string", "description": "Sketch name or label."}, **DOCUMENT_ARG},
    required=("name",),
)
def get_sketch(name, document=None):
    sketch = _object(_document(document), name)
    if not sketch.isDerivedFrom("Sketcher::SketchObject"):
        raise ToolError(f"{sketch.Name} is a {sketch.TypeId}, not a sketch")
    support = getattr(sketch, "AttachmentSupport", None) or []
    result = {
        "name": sketch.Name,
        "label": sketch.Label,
        "placement": _value(sketch.Placement),
        "attached_to": [[o.Name, list(subs)] for o, subs in support],
        "map_mode": getattr(sketch, "MapMode", None),
        "dof": sketch.DoF,
        "fully_constrained": sketch.DoF == 0,
        "conflicting": list(sketch.ConflictingConstraints),
        "redundant": list(sketch.RedundantConstraints),
        "partially_redundant": list(sketch.PartiallyRedundantConstraints),
        "malformed": list(sketch.MalformedConstraints),
        "geometry": [_geometry_entry(sketch, i, g) for i, g in enumerate(sketch.Geometry)],
        "constraints": [_constraint_entry(i, c) for i, c in enumerate(sketch.Constraints)],
    }
    result.update(_state(sketch))
    return result


# -- the GUI -----------------------------------------------------------------


@tool(
    "get_selection",
    "What the user has selected in the 3D view or tree, with sub-elements (Face3, Edge1) "
    "and the picked points. Ask the user to select something to point at it.",
)
def get_selection():
    import FreeCADGui

    result = []
    for sel in FreeCADGui.Selection.getSelectionEx("", 0):
        result.append(
            {
                "document": sel.DocumentName,
                "object": sel.ObjectName,
                "sub_elements": list(sel.SubElementNames),
                "picked_points": [_vector(p) for p in sel.PickedPoints],
            }
        )
    return result


def _view(document=None):
    import FreeCADGui

    gui_doc = FreeCADGui.getDocument(_document(document).Name)
    view = gui_doc.ActiveView if gui_doc else None
    if view is None or not hasattr(view, "saveImage"):
        raise ToolError("The document has no 3D view to render")
    return view


@tool(
    "screenshot",
    "Render the 3D view to a PNG. view picks a standard direction (the user's own camera "
    "is put back afterwards); 'current' keeps the camera as it is. fit zooms to show "
    "everything.",
    {
        "view": {"type": "string", "enum": ["current"] + list(VIEWS)},
        "fit": {"type": "boolean", "description": "Zoom to fit everything first."},
        "width": {"type": "integer", "description": "Pixels, 64 to 2048 (default 1024)."},
        "height": {"type": "integer", "description": "Pixels, 64 to 2048 (default 768)."},
        **DOCUMENT_ARG,
    },
)
def screenshot(view="current", fit=False, width=1024, height=768, document=None):
    if view != "current" and view not in VIEWS:
        raise ToolError(f"Unknown view '{view}'")
    width = min(max(int(width), 64), 2048)
    height = min(max(int(height), 64), 2048)
    view3d = _view(document)
    camera = view3d.getCamera()
    animated = view3d.isAnimationEnabled()
    handle, path = tempfile.mkstemp(suffix=".png", prefix="othercad-bridge-")
    os.close(handle)
    try:
        # An animated turn would still be under way when the image is taken
        view3d.setAnimationEnabled(False)
        if view != "current":
            getattr(view3d, VIEWS[view])()
        if fit:
            view3d.fitAll()
        view3d.saveImage(path, width, height, "Current")
        with open(path, "rb") as image:
            data = image.read()
    finally:
        view3d.setCamera(camera)
        view3d.setAnimationEnabled(animated)
        try:
            os.remove(path)
        except OSError:
            pass
    if not data:
        raise ToolError("The view rendered an empty image")
    return Image(data)
