/***************************************************************************
 *   Copyright (c) 2026 OtherCAD contributors                               *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/


#pragma once

#include <array>
#include <vector>

#include <Inventor/SbRotation.h>
#include <Inventor/SbVec3f.h>

#include <FCGlobal.h>

#include "Inventor/SoNaviCube.h"

/**
 * The geometry of OtherCAD's view cube (SoViewCube), worked out without a scene
 * graph or GL so that it can be checked on its own.
 *
 * The cube spans -1..1 on each axis, with the faces as SoNaviCube has them: Top
 * +z, Front -y, Left -x, Rear +y, Right +x, Bottom -z. A pick id's direction is
 * the sum of the normals of the faces it touches, so FrontTop is (0, -1, 1).
 */
namespace Gui::ViewCubeLayout
{

using PickId = SoNaviCube::PickId;

/// The edge and corner bands, as a fraction of a face's side.
constexpr float bandFraction = 0.22F;
constexpr int tilesPerFace = 9;
constexpr int tileCount = 54;
/// How far off an axis the camera may look and still count as looking straight at a face.
constexpr float faceOnToleranceDeg = 1.0F;

/// One of the 3x3 tiles a face is split into. Clicking it picks pickId.
struct Tile
{
    PickId face {PickId::None};
    PickId pickId {PickId::None};
    /// Counter-clockwise seen from outside.
    std::array<SbVec3f, 4> corners {};
};

/// Where a control sits in the cube's overlay square: 0..1 on both axes, y down.
struct ControlRect
{
    PickId pickId {PickId::None};
    float left {0.0F};
    float top {0.0F};
    float right {0.0F};
    float bottom {0.0F};

    bool contains(float x, float y) const
    {
        return x >= left && x <= right && y >= top && y <= bottom;
    }
};

/// Top, Front, Left, Rear, Right, Bottom: the order the tiles are stored in.
GuiExport const std::array<PickId, 6>& mainFaces();
GuiExport SbVec3f faceNormal(PickId face);
/// The sum of the normals of the faces a pick id touches, or (0, 0, 0) for a control.
GuiExport SbVec3f pickDirection(PickId id);
GuiExport PickId pickIdForDirection(const SbVec3f& direction);
/// Tile index = face index * 9 + row * 3 + column.
GuiExport const std::array<Tile, tileCount>& tiles();
/// The tiles that light up for a face (1), an edge (2) or a corner (3).
GuiExport std::vector<int> tilesFor(PickId id);
/// The unit vector from the cube towards the viewer, in cube coordinates.
GuiExport SbVec3f towardViewer(const SbRotation& cameraOrientation);
/// The main face the camera looks straight at, or None.
GuiExport PickId faceOn(const SbRotation& cameraOrientation, float toleranceDeg = faceOnToleranceDeg);
/// Face-on with the face square on screen, not rolled into a diamond: when the triangles show.
GuiExport bool squareOn(const SbRotation& cameraOrientation, float toleranceDeg = faceOnToleranceDeg);
/// 1.0 for a face turned to the viewer, down to 0.85 for one side-on or turned away.
GuiExport float faceShade(PickId face, const SbRotation& cameraOrientation);
/// The controls on show; the four triangles only when looking straight at a face.
GuiExport std::vector<ControlRect> controlRects(bool faceOnView);
GuiExport PickId controlAt(float x, float y, bool faceOnView);

}  // namespace Gui::ViewCubeLayout
