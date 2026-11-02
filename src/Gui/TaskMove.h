// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   This file is part of FreeCAD.                                          *
 *                                                                          *
 *   FreeCAD is free software: you can redistribute it and/or modify it     *
 *   under the terms of the GNU Lesser General Public License as            *
 *   published by the Free Software Foundation, either version 2.1 of the   *
 *   License, or (at your option) any later version.                        *
 *                                                                          *
 *   FreeCAD is distributed in the hope that it will be useful, but         *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of             *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU       *
 *   Lesser General Public License for more details.                        *
 *                                                                          *
 *   You should have received a copy of the GNU Lesser General Public       *
 *   License along with FreeCAD. If not, see                                *
 *   <https://www.gnu.org/licenses/>.                                       *
 *                                                                          *
 ***************************************************************************/

#pragma once

#include <array>
#include <memory>

#include <QPointer>

#include <App/DocumentObserver.h>
#include <Base/Placement.h>
#include <Base/Vector3D.h>

#include "TaskView/TaskDialog.h"

class SoNode;

namespace Gui
{

class GizmoContainer;
class LinearGizmo;
class QuantitySpinBox;
class RotationGizmo;
class View3DInventorViewer;

/**
 * Fusion's Move: three arrows and three rotation handles on the object in the view,
 * each with its value in a box beside it and in the panel. The object follows as the
 * values change, about the middle of its bounding box, and OK keeps the whole move
 * as one undo step. The arrows and handles stay lined up with the global axes.
 */
class GuiExport TaskMove: public TaskView::TaskDialog
{
    Q_OBJECT

public:
    explicit TaskMove(App::DocumentObject* object);
    ~TaskMove() override;

    /**
     * What Move acts on when \a selected is picked: the object itself if its placement
     * can be changed, otherwise the nearest group holding it whose placement can. A
     * feature inside a body moves the body, as in Fusion. Null if nothing can move.
     */
    static App::DocumentObject* movableFor(App::DocumentObject* selected);

    void open() override;
    bool accept() override;
    bool reject() override;

    QDialogButtonBox::StandardButtons getStandardButtons() const override
    {
        return QDialogButtonBox::Ok | QDialogButtonBox::Cancel;
    }

private:
    QWidget* buildPanel();
    void createGizmos();
    void attachGizmos();
    void detachGizmos();
    void hideGizmos();
    /// Stands the arrows and handles where the moved object now is.
    void placeGizmos();
    /// Moves the object by what the fields hold.
    void apply();
    Base::Vector3d travel() const;

    App::DocumentObjectWeakPtrT target;
    /// The object's own placement when Move opened.
    Base::Placement start;
    /// The global placement of the frame that placement is in.
    Base::Placement parent;
    /// The global middle of the object's bounding box when Move opened.
    Base::Vector3d centre;

    std::array<QuantitySpinBox*, 3> distances {};
    std::array<QuantitySpinBox*, 3> angles {};

    std::unique_ptr<GizmoContainer> gizmos;
    std::array<LinearGizmo*, 3> arrows {};
    std::array<RotationGizmo*, 3> handles {};
    QPointer<View3DInventorViewer> viewer;
    SoNode* attached = nullptr;
    bool gizmosPlaced = false;

    int transaction = 0;
};

}  // namespace Gui
