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


#include <algorithm>
#include <cmath>
#include <numbers>

#include "ViewCubeLayout.h"

namespace Gui::ViewCubeLayout
{

namespace
{

struct FaceFrame
{
    PickId face;
    SbVec3f u;  // tile columns run along u
    SbVec3f v;  // tile rows run along v; u x v is the outward normal
};

// The frames SoNaviCube::addCubeFace builds (y = x.cross(-z)), so labels read the same way.
const std::array<FaceFrame, 6>& frames()
{
    static const std::array<FaceFrame, 6> table {{
        {PickId::Top, SbVec3f(1, 0, 0), SbVec3f(0, 1, 0)},
        {PickId::Front, SbVec3f(1, 0, 0), SbVec3f(0, 0, 1)},
        {PickId::Left, SbVec3f(0, -1, 0), SbVec3f(0, 0, 1)},
        {PickId::Rear, SbVec3f(-1, 0, 0), SbVec3f(0, 0, 1)},
        {PickId::Right, SbVec3f(0, 1, 0), SbVec3f(0, 0, 1)},
        {PickId::Bottom, SbVec3f(1, 0, 0), SbVec3f(0, -1, 0)},
    }};
    return table;
}

struct Direction
{
    PickId id;
    int x;
    int y;
    int z;
};

const std::array<Direction, 26>& directions()
{
    static const std::array<Direction, 26> table {{
        {PickId::Front, 0, -1, 0},
        {PickId::Top, 0, 0, 1},
        {PickId::Right, 1, 0, 0},
        {PickId::Rear, 0, 1, 0},
        {PickId::Bottom, 0, 0, -1},
        {PickId::Left, -1, 0, 0},
        {PickId::FrontTop, 0, -1, 1},
        {PickId::FrontBottom, 0, -1, -1},
        {PickId::FrontRight, 1, -1, 0},
        {PickId::FrontLeft, -1, -1, 0},
        {PickId::RearTop, 0, 1, 1},
        {PickId::RearBottom, 0, 1, -1},
        {PickId::RearRight, 1, 1, 0},
        {PickId::RearLeft, -1, 1, 0},
        {PickId::TopRight, 1, 0, 1},
        {PickId::TopLeft, -1, 0, 1},
        {PickId::BottomRight, 1, 0, -1},
        {PickId::BottomLeft, -1, 0, -1},
        {PickId::FrontTopRight, 1, -1, 1},
        {PickId::FrontTopLeft, -1, -1, 1},
        {PickId::FrontBottomRight, 1, -1, -1},
        {PickId::FrontBottomLeft, -1, -1, -1},
        {PickId::RearTopRight, 1, 1, 1},
        {PickId::RearTopLeft, -1, 1, 1},
        {PickId::RearBottomRight, 1, 1, -1},
        {PickId::RearBottomLeft, -1, 1, -1},
    }};
    return table;
}

int roundAxis(float value)
{
    return value > 0.5F ? 1 : (value < -0.5F ? -1 : 0);
}

}  // namespace

const std::array<PickId, 6>& mainFaces()
{
    static const std::array<PickId, 6>
        faces {PickId::Top, PickId::Front, PickId::Left, PickId::Rear, PickId::Right, PickId::Bottom};
    return faces;
}

SbVec3f faceNormal(PickId face)
{
    for (const auto& f : frames()) {
        if (f.face == face) {
            return f.u.cross(f.v);
        }
    }
    return SbVec3f(0, 0, 0);
}

SbVec3f pickDirection(PickId id)
{
    for (const auto& d : directions()) {
        if (d.id == id) {
            return SbVec3f(static_cast<float>(d.x), static_cast<float>(d.y), static_cast<float>(d.z));
        }
    }
    return SbVec3f(0, 0, 0);
}

PickId pickIdForDirection(const SbVec3f& direction)
{
    const int x = roundAxis(direction[0]);
    const int y = roundAxis(direction[1]);
    const int z = roundAxis(direction[2]);
    for (const auto& d : directions()) {
        if (d.x == x && d.y == y && d.z == z) {
            return d.id;
        }
    }
    return PickId::None;
}

const std::array<Tile, tileCount>& tiles()
{
    static const std::array<Tile, tileCount> all = [] {
        std::array<Tile, tileCount> result {};
        const float inner = 1.0F - 2.0F * bandFraction;
        const std::array<float, 4> bounds {-1.0F, -inner, inner, 1.0F};
        for (size_t f = 0; f < frames().size(); ++f) {
            const FaceFrame& frame = frames()[f];
            const SbVec3f n = frame.u.cross(frame.v);
            const auto at = [&](int col, int row) {
                return n + frame.u * bounds[static_cast<size_t>(col)]
                    + frame.v * bounds[static_cast<size_t>(row)];
            };
            for (int row = 0; row < 3; ++row) {
                for (int col = 0; col < 3; ++col) {
                    Tile& t = result[f * tilesPerFace + static_cast<size_t>(row * 3 + col)];
                    t.face = frame.face;
                    t.pickId = pickIdForDirection(
                        n + frame.u * static_cast<float>(col - 1)
                        + frame.v * static_cast<float>(row - 1)
                    );
                    t.corners
                        = {at(col, row), at(col + 1, row), at(col + 1, row + 1), at(col, row + 1)};
                }
            }
        }
        return result;
    }();
    return all;
}

std::vector<int> tilesFor(PickId id)
{
    std::vector<int> result;
    if (id == PickId::None) {
        return result;
    }
    for (int i = 0; i < tileCount; ++i) {
        if (tiles()[static_cast<size_t>(i)].pickId == id) {
            result.push_back(i);
        }
    }
    return result;
}

SbVec3f towardViewer(const SbRotation& cameraOrientation)
{
    SbVec3f toViewer;
    cameraOrientation.multVec(SbVec3f(0.0F, 0.0F, 1.0F), toViewer);
    toViewer.normalize();
    return toViewer;
}

PickId faceOn(const SbRotation& cameraOrientation, float toleranceDeg)
{
    const SbVec3f toViewer = towardViewer(cameraOrientation);
    const float threshold = std::cos(toleranceDeg * std::numbers::pi_v<float> / 180.0F);
    for (PickId face : mainFaces()) {
        if (faceNormal(face).dot(toViewer) >= threshold) {
            return face;
        }
    }
    return PickId::None;
}

bool squareOn(const SbRotation& cameraOrientation, float toleranceDeg)
{
    if (faceOn(cameraOrientation, toleranceDeg) == PickId::None) {
        return false;
    }
    // Rolled off a right angle, the face is a diamond whose tips reach under the triangles.
    SbVec3f up;
    cameraOrientation.multVec(SbVec3f(0.0F, 1.0F, 0.0F), up);
    const float threshold = std::cos(toleranceDeg * std::numbers::pi_v<float> / 180.0F);
    return std::max({std::abs(up[0]), std::abs(up[1]), std::abs(up[2])}) >= threshold;
}

float faceShade(PickId face, const SbRotation& cameraOrientation)
{
    const float facing = std::max(0.0F, faceNormal(face).dot(towardViewer(cameraOrientation)));
    return 0.85F + 0.15F * facing;
}

std::vector<ControlRect> controlRects(bool faceOnView)
{
    std::vector<ControlRect> rects {
        {PickId::Home, 0.03F, 0.03F, 0.15F, 0.15F},
        {PickId::ArrowLeft, 0.74F, 0.03F, 0.86F, 0.13F},
        {PickId::ArrowRight, 0.86F, 0.03F, 0.98F, 0.13F},
        {PickId::ViewMenu, 0.86F, 0.86F, 0.98F, 0.98F},
    };
    if (faceOnView) {
        // Clear of the face-on square, which perspective draws at 0.232..0.768.
        rects.push_back({PickId::ArrowNorth, 0.455F, 0.105F, 0.545F, 0.195F});
        rects.push_back({PickId::ArrowSouth, 0.455F, 0.805F, 0.545F, 0.895F});
        rects.push_back({PickId::ArrowWest, 0.105F, 0.455F, 0.195F, 0.545F});
        rects.push_back({PickId::ArrowEast, 0.805F, 0.455F, 0.895F, 0.545F});
    }
    return rects;
}

PickId controlAt(float x, float y, bool faceOnView)
{
    for (const auto& rect : controlRects(faceOnView)) {
        if (rect.contains(x, y)) {
            return rect.pickId;
        }
    }
    return PickId::None;
}

}  // namespace Gui::ViewCubeLayout
