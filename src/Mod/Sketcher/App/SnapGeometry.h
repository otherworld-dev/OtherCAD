// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2026 FuCad contributors                                 *
 *                                                                         *
 *   This file is part of the FreeCAD CAx development system.              *
 *                                                                         *
 *   This library is free software; you can redistribute it and/or         *
 *   modify it under the terms of the GNU Library General Public           *
 *   License as published by the Free Software Foundation; either          *
 *   version 2 of the License, or (at your option) any later version.      *
 *                                                                         *
 *   This library  is distributed in the hope that it will be useful,      *
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
 *   GNU Library General Public License for more details.                  *
 *                                                                         *
 *   You should have received a copy of the GNU Library General Public     *
 *   License along with this library; see the file COPYING.LIB. If not,    *
 *   write to the Free Software Foundation, Inc., 59 Temple Place,         *
 *   Suite 330, Boston, MA  02111-1307, USA                                *
 *                                                                         *
 ***************************************************************************/

#pragma once

#include <optional>
#include <vector>

#include <Base/Tools2D.h>
#include <Mod/Sketcher/App/GeoEnum.h>
#include <Mod/Sketcher/SketcherGlobal.h>

namespace Part
{
class Geometry;
}

/**
 * Pure geometry behind cursor snapping in the sketch editor: which points a
 * curve offers (midpoint, quadrants, crossings with another curve), where the
 * nearest grid intersection is, and which of several reachable candidates the
 * cursor should land on. Nothing here touches the view, so it can be unit
 * tested; SketcherGui::SnapManager feeds it the hovered geometry and applies
 * the result.
 */
namespace Sketcher::SnapGeometry
{

/// What a snapped position stands for, in descending order of priority.
enum class SnapKind
{
    None,
    Origin,
    Vertex,
    Intersection,
    Midpoint,
    Quadrant,
    Axis,
    OnCurve,
    Grid,
};

struct SnapCandidate
{
    SnapKind kind = SnapKind::None;
    Base::Vector2d point;
    /// For a crossing, the GeoId of the other curve, so the snap can be constrained to both.
    int otherGeoId = GeoEnum::GeoUndef;
};

/// Rank of a kind; a higher rank wins whenever several kinds are within reach.
SketcherExport int priority(SnapKind kind);

/**
 * Chooses the candidate the cursor should snap to: among the candidates within
 * @a radius of @a cursor, the highest-priority kind, and the nearest of that
 * kind. Returns nothing when no candidate is within reach.
 */
SketcherExport std::optional<SnapCandidate> pickSnap(
    const std::vector<SnapCandidate>& candidates,
    const Base::Vector2d& cursor,
    double radius
);

/// Middle of a line segment or the angular middle of an arc of circle.
SketcherExport std::optional<Base::Vector2d> midpoint(const Part::Geometry* geo);

/// The 0°, 90°, 180° and 270° points of a circle, or those of an arc that lie inside its range.
SketcherExport std::vector<Base::Vector2d> quadrantPoints(const Part::Geometry* geo);

/// Points where two bounded curves cross, without duplicates.
SketcherExport std::vector<Base::Vector2d> intersections(
    const Part::Geometry* a,
    const Part::Geometry* b
);

/**
 * Snaps @a point to the grid lines of a square grid of @a spacing that lie
 * within @a tolerance of it, each axis on its own: near a grid line the point
 * slides along it, near an intersection it lands on it, and away from both it
 * is left alone (nothing is returned). A locked coordinate is never moved, so an
 * axis lock and the grid can combine.
 */
SketcherExport std::optional<Base::Vector2d> snapToGrid(
    const Base::Vector2d& point,
    double spacing,
    double tolerance,
    bool lockX = false,
    bool lockY = false
);

}  // namespace Sketcher::SnapGeometry
