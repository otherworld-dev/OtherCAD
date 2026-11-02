// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2026 FuCad contributors                                 *
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

#include <memory>
#include <optional>

#include <Base/Vector3D.h>

#include "TaskDressUpParameters.h"

class QFormLayout;
class QListWidget;
class QToolButton;

namespace Gui
{
class GizmoContainer;
class LinearGizmo;
class QuantitySpinBox;
}  // namespace Gui

namespace PartDesignGui
{

/**
 * The panel the direct edit tools share: the button that starts picking, the
 * list of faces picked so far, and whatever single control the tool itself needs
 * underneath.
 *
 * Built in code rather than from a .ui file because each of these panels is a
 * list and at most one field, and three files of markup would say less than the
 * dozen lines here.
 * @author FuCad contributors
 */
class TaskFaceOperationParameters: public TaskDressUpParameters
{
    Q_OBJECT

public:
    explicit TaskFaceOperationParameters(ViewProviderDressUp* view, QWidget* parent = nullptr);
    ~TaskFaceOperationParameters() override;

    void apply() override;

protected:
    /**
     * Adds the controls of the tool to \a layout, which sits under the list of
     * faces. The default adds nothing, which is right for a tool that only needs
     * to know which faces to work on.
     */
    virtual void addParameters(QFormLayout* layout);

    /// Opens a transaction and hands back the feature, ready to be changed.
    PartDesign::DressUp* beforeChange();
    /// Recomputes and hides the feature again if that failed.
    void afterChange(PartDesign::DressUp* feature);

    /**
     * Puts an arrow in the view on the first picked face, along its outward normal,
     * that drives \a field: Fusion's handle for pushing a face about. Nothing happens
     * when gizmos are turned off in the preferences.
     */
    void addArrow(Gui::QuantitySpinBox* field);
    /// Stands the arrow on the first picked face again, or hides it with none picked.
    void placeArrow();
    /// The outward normal of the first picked face, or nothing while none is picked.
    std::optional<Base::Vector3d> firstFaceNormal() const;
    /// Where the arrow's foot sits relative to the face, for a tool whose face also
    /// travels sideways; the default is on the face itself.
    virtual Base::Vector3d arrowOffset() const
    {
        return Base::Vector3d(0.0, 0.0, 0.0);
    }
    /// Called once the picked faces changed, for a tool whose fields depend on them.
    virtual void facesChanged()
    {}

    void setButtons(selectionModes mode) override;
    void onSelectionChanged(const Gui::SelectionChanges& msg) override;

protected Q_SLOTS:
    void onRefDeleted() override;

protected:
    /**
     * Builds the panel. Every subclass calls this from its own constructor: called from
     * this class's constructor, addParameters() would reach this class's version and
     * the tool's own fields would never appear.
     */
    void build();

private:
    QToolButton* selectButton;
    QListWidget* references;
    std::unique_ptr<Gui::GizmoContainer> gizmoContainer;
    Gui::LinearGizmo* arrow = nullptr;
};

}  // namespace PartDesignGui
