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

#include <array>

#include <QFormLayout>

#include <Base/Quantity.h>
#include <Base/Vector3D.h>
#include <Gui/QuantitySpinBox.h>
#include <Mod/PartDesign/App/FeatureDeleteFace.h>
#include <Mod/PartDesign/App/FeatureMoveFace.h>
#include <Mod/PartDesign/App/FeatureOffsetFace.h>

#include "TaskFaceToolParameters.h"
#include "ViewProviderFaceTools.h"

using namespace PartDesignGui;

namespace
{
/// The bound the other PartDesign length fields use, in both directions because
/// these tools take material away for a negative distance.
constexpr double lengthLimit = 999999999.0;

/// A length field of the kind these panels use, already bound to \a property.
Gui::QuantitySpinBox* lengthField(QWidget* parent, App::PropertyQuantity& property)
{
    auto* field = new Gui::QuantitySpinBox(parent);
    field->setUnit(Base::Unit::Length);
    field->setKeyboardTracking(false);
    field->setMinimum(-lengthLimit);
    field->setMaximum(lengthLimit);
    field->setSingleStep(1.0);
    field->setValue(property.getValue());
    field->bind(property);
    return field;
}
}  // namespace


TaskOffsetFaceParameters::TaskOffsetFaceParameters(ViewProviderDressUp* view, QWidget* parent)
    : TaskFaceOperationParameters(view, parent)
    , offset(nullptr)
{
    build();
}

void TaskOffsetFaceParameters::addParameters(QFormLayout* layout)
{
    auto* feature = getObject<PartDesign::OffsetFace>();

    offset = lengthField(proxy, feature->Offset);
    offset->setObjectName(QStringLiteral("offsetFaceDistance"));
    layout->addRow(tr("Offset"), offset);
    addArrow(offset);

    connect(offset, qOverload<double>(&Gui::QuantitySpinBox::valueChanged), this, [this](double value) {
        if (auto* changing = beforeChange()) {
            static_cast<PartDesign::OffsetFace*>(changing)->Offset.setValue(value);
            afterChange(changing);
        }
    });
}


TaskMoveFaceParameters::TaskMoveFaceParameters(ViewProviderDressUp* view, QWidget* parent)
    : TaskFaceOperationParameters(view, parent)
{
    build();
}

void TaskMoveFaceParameters::addParameters(QFormLayout* layout)
{
    auto* feature = getObject<PartDesign::MoveFace>();
    const Base::Vector3d travel = feature->Direction.getValue();
    const std::array<double, 3> components = {travel.x, travel.y, travel.z};
    const std::array<QString, 3> labels = {tr("Along X"), tr("Along Y"), tr("Along Z")};
    const std::array<QString, 3> names = {
        QStringLiteral("moveFaceAlongX"),
        QStringLiteral("moveFaceAlongY"),
        QStringLiteral("moveFaceAlongZ"),
    };

    const auto makeField = [this]() {
        auto* field = new Gui::QuantitySpinBox(proxy);
        field->setUnit(Base::Unit::Length);
        field->setKeyboardTracking(false);
        field->setMinimum(-lengthLimit);
        field->setMaximum(lengthLimit);
        field->setSingleStep(1.0);
        return field;
    };

    for (int axis = 0; axis < 3; ++axis) {
        auto* field = makeField();
        field->setObjectName(names.at(axis));
        field->setValue(components.at(axis));

        layout->addRow(labels.at(axis), field);
        along[axis] = field;

        connect(field, qOverload<double>(&Gui::QuantitySpinBox::valueChanged), this, [this](double) {
            onComponentChanged();
        });
    }

    // Fusion pushes a face along its normal with the arrow on it; the X, Y and Z fields
    // stay for travel in any other direction
    alongNormal = makeField();
    alongNormal->setObjectName(QStringLiteral("moveFaceAlongNormal"));
    alongNormal->setToolTip(tr("How far the faces travel along the normal of the first face"));
    layout->addRow(tr("Along normal"), alongNormal);
    showAlongNormal();

    connect(
        alongNormal,
        qOverload<double>(&Gui::QuantitySpinBox::valueChanged),
        this,
        &TaskMoveFaceParameters::onAlongNormalChanged
    );

    addArrow(alongNormal);
}

Base::Vector3d TaskMoveFaceParameters::travel() const
{
    return Base::Vector3d(
        along[0]->value().getValue(),
        along[1]->value().getValue(),
        along[2]->value().getValue()
    );
}

void TaskMoveFaceParameters::showAlongNormal()
{
    const std::optional<Base::Vector3d> normal = firstFaceNormal();
    alongNormal->setEnabled(normal.has_value());

    syncing = true;
    alongNormal->setValue(normal ? travel() * *normal : 0.0);
    syncing = false;
}

Base::Vector3d TaskMoveFaceParameters::arrowOffset() const
{
    // The arrow's tip shows the travel along the normal, so its foot takes the rest
    const std::optional<Base::Vector3d> normal = firstFaceNormal();
    const Base::Vector3d moved = travel();
    return normal ? moved - *normal * (moved * *normal) : moved;
}

void TaskMoveFaceParameters::facesChanged()
{
    showAlongNormal();
}

void TaskMoveFaceParameters::onComponentChanged()
{
    if (syncing) {
        return;
    }

    auto* changing = beforeChange();
    if (!changing) {
        return;
    }

    static_cast<PartDesign::MoveFace*>(changing)->Direction.setValue(travel());
    afterChange(changing);

    showAlongNormal();
    placeArrow();
}

void TaskMoveFaceParameters::onAlongNormalChanged(double value)
{
    const std::optional<Base::Vector3d> normal = firstFaceNormal();
    if (syncing || !normal) {
        return;
    }

    // Only the part along the normal changes; the sideways travel stays as it was,
    // and so does the arrow's foot, which matters while the arrow is being dragged
    const Base::Vector3d moved = travel();
    const Base::Vector3d result = moved + *normal * (value - moved * *normal);

    syncing = true;
    for (int axis = 0; axis < 3; ++axis) {
        along[axis]->setValue(result[axis]);
    }
    syncing = false;

    if (auto* changing = beforeChange()) {
        static_cast<PartDesign::MoveFace*>(changing)->Direction.setValue(result);
        afterChange(changing);
    }
}


TaskDeleteFaceParameters::TaskDeleteFaceParameters(ViewProviderDressUp* view, QWidget* parent)
    : TaskFaceOperationParameters(view, parent)
{
    build();
}


TaskDlgOffsetFaceParameters::TaskDlgOffsetFaceParameters(ViewProviderOffsetFace* view)
    : TaskDlgDressUpParameters(view)
{
    parameter = new TaskOffsetFaceParameters(view);
    Content.push_back(parameter);
    Content.push_back(preview);
}

TaskDlgMoveFaceParameters::TaskDlgMoveFaceParameters(ViewProviderMoveFace* view)
    : TaskDlgDressUpParameters(view)
{
    parameter = new TaskMoveFaceParameters(view);
    Content.push_back(parameter);
    Content.push_back(preview);
}

TaskDlgDeleteFaceParameters::TaskDlgDeleteFaceParameters(ViewProviderDeleteFace* view)
    : TaskDlgDressUpParameters(view)
{
    parameter = new TaskDeleteFaceParameters(view);
    Content.push_back(parameter);
    Content.push_back(preview);
}

#include "moc_TaskFaceToolParameters.cpp"
