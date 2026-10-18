// SPDX-License-Identifier: LGPL-2.1-or-later
// SPDX-FileCopyrightText: 2026 OtherCAD contributors
// SPDX-FileNotice: Part of the FreeCAD project.

/******************************************************************************
 *                                                                            *
 *   FreeCAD is free software: you can redistribute it and/or modify          *
 *   it under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the     *
 *   License, or (at your option) any later version.                          *
 *                                                                            *
 *   FreeCAD is distributed in the hope that it will be useful, but           *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of               *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            *
 *   GNU Lesser General Public License for more details.                      *
 *                                                                            *
 *   You should have received a copy of the GNU Lesser General Public         *
 *   License along with FreeCAD.  If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                         *
 *                                                                            *
 ******************************************************************************/

#pragma once

#include <array>

#include <Inventor/SbVec2s.h>
#include <Inventor/fields/SoSFBool.h>
#include <Inventor/fields/SoSFColor.h>
#include <Inventor/fields/SoSFFloat.h>
#include <Inventor/fields/SoSFInt32.h>
#include <Inventor/fields/SoSFRotation.h>
#include <Inventor/fields/SoSFVec4f.h>
#include <Inventor/nodes/SoShape.h>

#include <FCGlobal.h>

#include "SoNaviCube.h"

class SoDrawStyle;
class SoIndexedFaceSet;
class SoMaterial;
class SoSeparator;
class SoSwitch;
class SoTexture2;
class SoTransform;

namespace Gui
{

/**
 * OtherCAD's navigation cube: flat, see-through faces, each split into 3x3 tiles
 * (centre = the face, sides = edges, corners = corners), with faint guide lines on
 * the tile borders and small line controls that show while the pointer is over it.
 *
 * It mirrors SoNaviCube's fields and pickAt() so that NaviCubeImplementation can
 * drive either; it answers with SoNaviCube::PickId.
 */
class GuiExport SoViewCube: public SoShape
{
    using inherited = SoShape;

    SO_NODE_HEADER(SoViewCube);

public:
    using PickId = SoNaviCube::PickId;

    static void initClass();
    SoViewCube();

    SoSFFloat size;
    SoSFFloat opacity;
    SoSFFloat borderWidth;
    SoSFColor baseColor;
    SoSFFloat baseAlpha;
    SoSFColor emphaseColor;
    SoSFFloat emphaseAlpha;
    SoSFColor hiliteColor;
    SoSFFloat hiliteAlpha;
    SoSFInt32 hiliteId;
    SoSFRotation cameraOrientation;
    SoSFBool cameraIsOrthographic;
    SoSFVec4f viewportRect;
    //! 0..1: how far the hover controls have faded in.
    SoSFFloat controlsOpacity;
    //! Whether the hover controls answer clicks; false as soon as they start fading out.
    SoSFBool controlsLive;
    //! Keep the step triangles up after one was clicked, until the pointer leaves the cube.
    SoSFBool trianglesLatched;

    void setLabelImage(PickId id, const SbVec2s& size, int numComponents, const unsigned char* pixels);
    void clearLabelTextures();
    [[nodiscard]] PickId pickAt(const SbVec2s& point) const;
    //! Test hook: how many tiles currently wear the highlight.
    [[nodiscard]] int hilitedTileCount() const;
    //! Test hook: how many controls are switched on (4, or 8 with the face-on triangles).
    [[nodiscard]] int visibleControlCount() const;

protected:
    ~SoViewCube() override;

    void GLRender(SoGLRenderAction* action) override;
    void generatePrimitives(SoAction* action) override;
    void computeBBox(SoAction* action, SbBox3f& box, SbVec3f& center) override;

private:
    struct LabelNodes
    {
        SoSwitch* visible {nullptr};
        SoMaterial* material {nullptr};
        SoTexture2* texture {nullptr};
    };

    struct ControlNodes
    {
        PickId pickId {PickId::None};
        SoMaterial* material {nullptr};
    };

    void ensureSceneGraph() const;
    void buildCube(SoSeparator* cube) const;
    void buildControls(SoSeparator* parent) const;
    void updateSceneGraph() const;
    void beginOverlayPass(SoGLRenderAction* action, int x, int y, int width, int height);
    [[nodiscard]] int labelSlot(PickId face) const;
    //! Square on to a face, or latched by the controller after a triangle click.
    [[nodiscard]] bool trianglesShown() const;

    mutable SoSeparator* sceneRoot {nullptr};
    mutable SoSeparator* pickRoot {nullptr};
    mutable SoSwitch* cameraSwitch {nullptr};
    mutable SoTransform* rootTransform {nullptr};
    mutable SoMaterial* tileMaterial {nullptr};
    mutable SoIndexedFaceSet* tileFaces {nullptr};
    mutable SoMaterial* guideMaterial {nullptr};
    mutable SoMaterial* edgeMaterial {nullptr};
    mutable SoDrawStyle* edgeStyle {nullptr};
    mutable std::array<LabelNodes, 6> labels {};
    mutable SoSwitch* controlsSwitch {nullptr};
    mutable SoSwitch* trianglesSwitch {nullptr};
    mutable std::array<ControlNodes, 8> controls {};
};

}  // namespace Gui
