# SPDX-License-Identifier: LGPL-2.1-or-later

# ***************************************************************************
# *   Copyright (c) 2026 FuCadUp contributors                               *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

"""Give a feature made with the New body operation a body of its own.

A PartDesign feature always sits in a body, and the New body operation asks for the
solid to start another one. While it is still in the body it was made in, the feature
passes that body's solid straight through, so nothing there changes. moveToNewBody()
then puts it in a body of its own next to that one.

What the feature was built from comes along when nothing else uses it and it does not
itself reach back into the old body; a sketch drawn on an origin plane for this feature
alone is the usual case. Anything else stays where it is, and the new body gets a
SubShapeBinder of the part the feature uses instead, so it keeps following the original.
"""

import FreeCAD

# The links a feature is built from. Each is local to the body, so it cannot simply
# point back into the old one once the feature has moved.
INPUT_PROPERTIES = (
    "Profile",
    "Sections",
    "Spine",
    "AuxiliarySpine",
    "ReferenceAxis",
    "UpToFace",
    "UpToFace2",
    "UpToShape",
    "UpToShape2",
)

# Inputs that name one element, which a binder of that element alone calls Edge1 or Face1
SINGLE_ELEMENT_PROPERTIES = ("ReferenceAxis", "UpToFace", "UpToFace2")


def needsOwnBody(feature):
    """True for a New body feature that still sits after another solid in its body."""
    if getattr(feature, "Operation", None) != "NewBody":
        return False
    return _bodyOf(feature) is not None and feature.BaseFeature is not None


def moveToNewBody(feature):
    """Move a New body feature into a body of its own and return that body.

    Returns None, and changes nothing, when the feature does not need one.
    """
    if not needsOwnBody(feature):
        return None

    doc = feature.Document
    oldBody = _bodyOf(feature)

    inputs = _inputsOf(feature, oldBody)
    moving = [obj for obj in inputs if _canMove(obj, feature, oldBody)]

    newBody = doc.addObject("PartDesign::Body", "Body")
    container = oldBody.getParentGeoFeatureGroup()
    if container is not None:
        container.addObject(newBody)
    newBody.Placement = oldBody.Placement

    binders = []
    for name in INPUT_PROPERTIES:
        binders += _bindStaying(feature, name, oldBody, moving, doc)

    # Keep the order the objects had in the old body, with the feature itself last
    ordered = [obj for obj in oldBody.Group if obj in moving]
    for obj in ordered + [feature]:
        # One at a time: only the Body's own removeObject() moves Tip and BaseFeature on,
        # removeObjects() is the plain group's
        oldBody.removeObject(obj)
    newBody.addObjects(binders + ordered + [feature])

    for obj in binders + ordered:
        obj.Visibility = False
    if oldBody.Tip is not None:
        oldBody.Tip.Visibility = True
    feature.Visibility = True

    doc.recompute()
    return newBody


def _bodyOf(obj):
    parent = obj.getParentGeoFeatureGroup()
    if parent is not None and parent.isDerivedFrom("PartDesign::Body"):
        return parent
    return None


def _isOrigin(obj):
    return obj.isDerivedFrom("App::DatumElement") and obj.isOriginFeature()


def _isDatum(obj):
    return any(
        obj.isDerivedFrom(kind)
        for kind in (
            "PartDesign::Plane",
            "PartDesign::Line",
            "PartDesign::Point",
            "PartDesign::CoordinateSystem",
        )
    )


def _pairs(value):
    """The (object, subnames) pairs of a link property's value, whatever its type."""
    if value is None:
        return []
    if isinstance(value, FreeCAD.DocumentObject):
        return [(value, [])]
    if isinstance(value, tuple):
        if value and isinstance(value[0], FreeCAD.DocumentObject):
            subs = value[1] if len(value) > 1 else []
            return [(value[0], [subs] if isinstance(subs, str) else list(subs))]
        return []
    pairs = []
    for item in value:
        pairs += _pairs(item)
    return pairs


def _links(obj, name):
    if not hasattr(obj, name):
        return []
    return [(target, [sub for sub in subs if sub]) for target, subs in _pairs(getattr(obj, name))]


def _inputsOf(feature, body):
    """Objects of the old body that the feature is built from, in the order it names them."""
    found = []
    for name in INPUT_PROPERTIES:
        for obj, _subs in _links(feature, name):
            if obj in found or obj is feature or _isOrigin(obj):
                continue
            if _bodyOf(obj) is body:
                found.append(obj)
    return found


def _canMove(obj, feature, body):
    """Whether obj can leave the old body along with the feature."""
    if obj.isDerivedFrom("PartDesign::Feature") and not _isDatum(obj):
        # A solid of the old body, such as the face an extrusion runs up to
        return False
    if any(user is not body and user is not feature for user in obj.InList):
        return False
    # Projected geometry is a local link too, so a sketch that projects edges of the
    # old body has to stay with it.
    return all(_isOrigin(target) for target, _subs in _links(obj, "ExternalGeometry"))


def _bindStaying(feature, name, body, moving, doc):
    """Point one input property at binders for what stays in the old body.

    Returns the binders it made.
    """
    links = _links(feature, name)
    staying = [
        (obj, subs)
        for obj, subs in links
        if obj not in moving and obj is not feature and not _isOrigin(obj) and _bodyOf(obj) is body
    ]
    if not staying:
        return []

    if name == "ReferenceAxis" and all(
        any(sub.endswith("N_Axis") for sub in subs) for _obj, subs in staying
    ):
        # The sketch's normal, which Extrude points at by default. It is not part of the
        # sketch's shape, so a binder of it would be empty; with no reference the feature
        # takes the normal of the profile it is given, which is the same direction.
        setattr(feature, name, None)
        return []

    binders = []
    relinked = []
    for obj, subs in links:
        if (obj, subs) not in staying:
            relinked.append((obj, subs))
            continue
        binder = doc.addObject("PartDesign::SubShapeBinder", "Binder")
        binder.Label = "Binder " + obj.Label
        binder.Support = [(obj, subs or [""])]
        binders.append(binder)
        if name in SINGLE_ELEMENT_PROPERTIES and len(subs) == 1:
            relinked.append((binder, [_firstElementLike(subs[0])]))
        else:
            relinked.append((binder, []))

    typeId = feature.getTypeIdOfProperty(name)
    if typeId.startswith("App::PropertyLinkList"):
        setattr(feature, name, [obj for obj, _subs in relinked])
    elif typeId.startswith("App::PropertyLinkSubList"):
        setattr(feature, name, [(obj, subs or [""]) for obj, subs in relinked])
    elif typeId.startswith("App::PropertyLinkSub"):
        obj, subs = relinked[0]
        setattr(feature, name, (obj, subs or [""]))
    else:
        setattr(feature, name, relinked[0][0])
    return binders


def _firstElementLike(sub):
    """The name the single element sub has in a binder that holds only it."""
    element = sub.split(".")[-1]
    if element.endswith("_Axis") or "Edge" in element:
        return "Edge1"
    if "Face" in element:
        return "Face1"
    if "Vertex" in element or element == "RootPoint":
        return "Vertex1"
    return element
