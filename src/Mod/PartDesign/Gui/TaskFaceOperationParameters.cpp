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

#include <string>
#include <vector>

#include <QAbstractItemView>
#include <QAction>
#include <QFormLayout>
#include <QListWidget>
#include <QToolButton>
#include <QVBoxLayout>

#include <BRepGProp.hxx>
#include <BRepGProp_Face.hxx>
#include <GProp_GProps.hxx>

#include <Base/Console.h>
#include <Gui/Inventor/Draggers/Gizmo.h>
#include <Gui/QuantitySpinBox.h>
#include <Gui/Selection/Selection.h>
#include <Mod/Part/App/TopoShape.h>
#include <Mod/PartDesign/App/FeatureFaceOperation.h>

#include "TaskFaceOperationParameters.h"
#include "ViewProviderDressUp.h"

using namespace PartDesignGui;

namespace
{
constexpr int referenceListHeight = 96;

/// Where an arrow on \a face stands: the middle of a flat face, and the middle of a
/// curved face's parameter range, where FaceOperation measures its normal.
gp_Pnt arrowFoot(const TopoDS_Face& face)
{
    if (Part::TopoShape(face).isPlanar()) {
        GProp_GProps props;
        BRepGProp::SurfaceProperties(face, props);
        return props.CentreOfMass();
    }

    BRepGProp_Face prop(face);
    Standard_Real uMin = 0.0;
    Standard_Real uMax = 0.0;
    Standard_Real vMin = 0.0;
    Standard_Real vMax = 0.0;
    prop.Bounds(uMin, uMax, vMin, vMax);

    gp_Pnt point;
    gp_Vec normal;
    prop.Normal((uMin + uMax) / 2.0, (vMin + vMax) / 2.0, point, normal);
    return point;
}

/// The first face \a feature names, or nothing while it names none that exists.
std::optional<TopoDS_Face> firstFace(PartDesign::FaceOperation* feature)
{
    if (!feature) {
        return std::nullopt;
    }

    try {
        std::vector<TopoDS_Face> faces = feature->selectedFaces(feature->getBaseTopoShape());
        if (!faces.empty()) {
            return faces.front();
        }
    }
    catch (const Base::Exception&) {
    }
    catch (const Standard_Failure&) {
    }
    return std::nullopt;
}
}  // namespace

TaskFaceOperationParameters::TaskFaceOperationParameters(ViewProviderDressUp* view, QWidget* parent)
    : TaskDressUpParameters(view, false, true, parent)
    , selectButton(nullptr)
    , references(nullptr)
{}

TaskFaceOperationParameters::~TaskFaceOperationParameters()
{
    try {
        Gui::Selection().clearSelection();
        Gui::Selection().rmvSelectionGate();
    }
    catch (const Py::Exception&) {
        Base::PyException e;
        e.reportException();
    }
}

void TaskFaceOperationParameters::build()
{
    proxy = new QWidget(this);
    auto* layout = new QVBoxLayout(proxy);
    layout->setContentsMargins(0, 0, 0, 0);

    selectButton = new QToolButton(proxy);
    selectButton->setCheckable(true);
    selectButton->setText(startSelectionLabel());
    selectButton->setToolTip(tr("Toggles between selection and preview mode"));
    layout->addWidget(selectButton);

    references = new QListWidget(proxy);
    references->setSelectionMode(QAbstractItemView::MultiSelection);
    references->setToolTip(
        tr("- select an item to highlight it\n"
           "- double-click on an item to see the features")
    );
    references->setMinimumHeight(referenceListHeight);
    layout->addWidget(references);

    auto* parameters = new QFormLayout();
    layout->addLayout(parameters);
    addParameters(parameters);

    this->groupLayout()->addWidget(proxy);

    connect(selectButton, &QToolButton::toggled, this, &TaskFaceOperationParameters::onButtonRefSel);
    connect(references, &QListWidget::currentItemChanged, this, &TaskFaceOperationParameters::setSelection);
    connect(references, &QListWidget::itemClicked, this, &TaskFaceOperationParameters::setSelection);
    connect(references, &QListWidget::itemDoubleClicked, this, &TaskFaceOperationParameters::doubleClicked);

    createDeleteAction(references);
    connect(deleteAction, &QAction::triggered, this, &TaskFaceOperationParameters::onRefDeleted);

    const std::vector<std::string> picked
        = getDressUpView()->getObject<PartDesign::DressUp>()->Base.getSubValues();
    for (const std::string& name : picked) {
        references->addItem(QString::fromStdString(name));
    }

    if (picked.empty()) {
        setSelectionMode(refSel);
    }
    else {
        hideOnError();
    }
}

void TaskFaceOperationParameters::addParameters(QFormLayout*)
{}

PartDesign::DressUp* TaskFaceOperationParameters::beforeChange()
{
    setButtons(none);
    setupTransaction();
    return getObject<PartDesign::DressUp>();
}

void TaskFaceOperationParameters::afterChange(PartDesign::DressUp* feature)
{
    feature->recomputeFeature();
    hideOnError();
}

void TaskFaceOperationParameters::addArrow(Gui::QuantitySpinBox* field)
{
    if (!Gui::GizmoContainer::isEnabled()) {
        return;
    }

    arrow = new Gui::LinearGizmo(field);
    gizmoContainer = Gui::GizmoContainer::create({arrow}, getDressUpView());

    placeArrow();
    showDraggerHints();
}

std::optional<Base::Vector3d> TaskFaceOperationParameters::firstFaceNormal() const
{
    const std::optional<TopoDS_Face> face = firstFace(getObject<PartDesign::FaceOperation>());
    if (!face) {
        return std::nullopt;
    }

    try {
        const gp_Vec normal = PartDesign::FaceOperation::outwardNormal(*face);
        return Base::Vector3d(normal.X(), normal.Y(), normal.Z());
    }
    catch (const Base::Exception&) {
        return std::nullopt;
    }
}

void TaskFaceOperationParameters::placeArrow()
{
    if (!gizmoContainer) {
        return;
    }

    const std::optional<TopoDS_Face> face = firstFace(getObject<PartDesign::FaceOperation>());
    const std::optional<Base::Vector3d> normal = firstFaceNormal();
    if (!face || !normal) {
        // Nothing to stand on yet, which is how the panel opens when nothing was picked
        gizmoContainer->visible = false;
        return;
    }

    const gp_Pnt foot = arrowFoot(*face);
    const Base::Vector3d position = Base::Vector3d(foot.X(), foot.Y(), foot.Z()) + arrowOffset();

    arrow->Gizmo::setDraggerPlacement(position, *normal);
    gizmoContainer->visible = true;
}

void TaskFaceOperationParameters::setButtons(selectionModes mode)
{
    selectButton->setChecked(mode == refSel);
    selectButton->setText(mode == refSel ? stopSelectionLabel() : startSelectionLabel());
}

void TaskFaceOperationParameters::onSelectionChanged(const Gui::SelectionChanges& msg)
{
    if (msg.Type == Gui::SelectionChanges::AddSelection && selectionMode == refSel) {
        referenceSelected(msg, references);
        facesChanged();
        placeArrow();
    }
}

void TaskFaceOperationParameters::onRefDeleted()
{
    TaskDressUpParameters::deleteRef(references);
    facesChanged();
    placeArrow();
}

void TaskFaceOperationParameters::apply()
{
    if (references->count() == 0) {
        Base::Console().warning("No face was chosen, so the feature changes nothing.\n");
    }
}

#include "moc_TaskFaceOperationParameters.cpp"
