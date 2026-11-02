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

#include <cmath>
#include <numbers>

#include <QFormLayout>
#include <QLabel>

#include <Inventor/misc/SoChildList.h>
#include <Inventor/nodes/SoSeparator.h>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/GeoFeature.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/PropertyGeo.h>
#include <Base/BoundBox.h>
#include <Base/Rotation.h>
#include <Base/Tools.h>
#include <Base/Unit.h>

#include "TaskMove.h"
#include "Application.h"
#include "BitmapFactory.h"
#include "Document.h"
#include "QuantitySpinBox.h"
#include "View3DInventor.h"
#include "View3DInventorViewer.h"
#include "ViewParams.h"
#include "Inventor/Draggers/Gizmo.h"
#include "Inventor/Draggers/SoLinearDragger.h"
#include "Inventor/Draggers/SoRotationDragger.h"
#include "Inventor/Draggers/SoRotationDraggerGeometry.h"
#include "TaskView/TaskView.h"

using namespace Gui;

namespace
{
const std::array<Base::Vector3d, 3> axes = {
    Base::Vector3d(1.0, 0.0, 0.0),
    Base::Vector3d(0.0, 1.0, 0.0),
    Base::Vector3d(0.0, 0.0, 1.0),
};

/// Where each rotation handle sits on its circle: between the two arrows it turns
/// towards each other, so it never covers one of them.
const std::array<Base::Vector3d, 3> handleDirections = {
    Base::Vector3d(0.0, 1.0, 1.0),
    Base::Vector3d(1.0, 0.0, 1.0),
    Base::Vector3d(1.0, 1.0, 0.0),
};

/// The bound the placement dialog uses for a distance.
constexpr double distanceLimit = 999999999.0;
/// A full turn either way: more says nothing a turn less would not.
constexpr double angleLimit = 360.0;

/// How far the turning handles stand from the middle, in gizmo units.
constexpr float handleRadius = 8.0F;

SbVec3f toSb(const Base::Vector3d& v)
{
    return {static_cast<float>(v.x), static_cast<float>(v.y), static_cast<float>(v.z)};
}

/// A colour packed as 0xRRGGBBAA, the way ViewParams keeps them.
SbColor toSbColor(unsigned long packed)
{
    constexpr float full = 255.0F;
    return {
        static_cast<float>((packed >> 24) & 0xff) / full,
        static_cast<float>((packed >> 16) & 0xff) / full,
        static_cast<float>((packed >> 8) & 0xff) / full,
    };
}

View3DInventorViewer* viewerFor(App::Document* document)
{
    Gui::Document* guiDocument = Application::Instance->getDocument(document);
    if (!guiDocument) {
        return nullptr;
    }
    if (auto* view = dynamic_cast<View3DInventor*>(guiDocument->getActiveView())) {
        return view->getViewer();
    }
    for (MDIView* view : guiDocument->getMDIViewsOfType(View3DInventor::getClassTypeId())) {
        return static_cast<View3DInventor*>(view)->getViewer();
    }
    return nullptr;
}
}  // namespace

TaskMove::TaskMove(App::DocumentObject* object)
    : target(object)
{
    auto* property = object->getPlacementProperty();
    start = property ? property->getValue() : Base::Placement();
    parent = App::GeoFeature::getGlobalPlacement(object) * start.inverse();

    // The handles stand at the middle of what is being moved, as Fusion's do
    Base::Vector3d middle = start.getPosition();
    if (const App::PropertyComplexGeoData* geometry = App::GeoFeature::getPropertyOfGeometry(object)) {
        const Base::BoundBox3d box = geometry->getBoundingBox();
        if (box.IsValid()) {
            middle = box.GetCenter();
        }
    }
    parent.multVec(middle, centre);

    Content.push_back(buildPanel());
    createGizmos();

    transaction = object->getDocument()->setActiveTransaction(
        App::TransactionName {.name = QT_TRANSLATE_NOOP("Command", "Move"), .temporary = false}
    );
}

TaskMove::~TaskMove()
{
    detachGizmos();
}

App::DocumentObject* TaskMove::movableFor(App::DocumentObject* selected)
{
    for (App::DocumentObject* object = selected; object;
         object = App::GeoFeatureGroupExtension::getGroupOfObject(object)) {
        auto* property = object->getPlacementProperty();
        if (property && !property->isReadOnly() && !object->isFreezed()) {
            return object;
        }
    }
    return nullptr;
}

QWidget* TaskMove::buildPanel()
{
    auto* box
        = new TaskView::TaskBox(BitmapFactory().pixmap("Std_Placement"), tr("Move"), true, nullptr);

    auto* body = new QWidget(box);
    auto* layout = new QFormLayout(body);

    const std::array<QString, 3> distanceLabels
        = {tr("X distance"), tr("Y distance"), tr("Z distance")};
    const std::array<QString, 3> angleLabels = {tr("X angle"), tr("Y angle"), tr("Z angle")};
    const std::array<const char*, 3> letters = {"X", "Y", "Z"};

    for (std::size_t axis = 0; axis < 3; ++axis) {
        auto* field = new QuantitySpinBox(body);
        field->setObjectName(QStringLiteral("moveDistance") + QLatin1String(letters.at(axis)));
        field->setUnit(Base::Unit::Length);
        field->setKeyboardTracking(false);
        field->setMinimum(-distanceLimit);
        field->setMaximum(distanceLimit);
        field->setValue(0.0);
        layout->addRow(distanceLabels.at(axis), field);
        distances.at(axis) = field;
    }

    for (std::size_t axis = 0; axis < 3; ++axis) {
        auto* field = new QuantitySpinBox(body);
        field->setObjectName(QStringLiteral("moveAngle") + QLatin1String(letters.at(axis)));
        field->setUnit(Base::Unit::Angle);
        field->setKeyboardTracking(false);
        field->setMinimum(-angleLimit);
        field->setMaximum(angleLimit);
        field->setValue(0.0);
        layout->addRow(angleLabels.at(axis), field);
        angles.at(axis) = field;
    }

    for (QuantitySpinBox* field : distances) {
        connect(field, qOverload<double>(&QuantitySpinBox::valueChanged), this, [this](double) {
            apply();
            placeGizmos();
        });
    }
    for (QuantitySpinBox* field : angles) {
        // Turning moves no handle: they all stand at the middle, which a turn keeps put
        connect(field, qOverload<double>(&QuantitySpinBox::valueChanged), this, [this](double) {
            apply();
        });
    }

    box->groupLayout()->addWidget(body);
    return box;
}

void TaskMove::createGizmos()
{
    if (!GizmoContainer::isEnabled()) {
        return;
    }

    for (std::size_t axis = 0; axis < 3; ++axis) {
        arrows.at(axis) = new LinearGizmo(distances.at(axis));
        handles.at(axis) = new RotationGizmo(angles.at(axis));
    }

    gizmos = std::make_unique<GizmoContainer>();
    gizmos->addGizmos({arrows[0], arrows[1], arrows[2], handles[0], handles[1], handles[2]});

    // Each axis in its own colour, as the transform dragger and Fusion's Move show them,
    // and the turning handles just past the arrow tips rather than out at the radius a
    // revolve uses
    const std::array<unsigned long, 3> colours = {
        ViewParams::instance()->getAxisXColor(),
        ViewParams::instance()->getAxisYColor(),
        ViewParams::instance()->getAxisZColor(),
    };
    for (std::size_t axis = 0; axis < 3; ++axis) {
        const SbColor colour = toSbColor(colours.at(axis));
        arrows.at(axis)->getDraggerContainer()->getDragger()->color = colour;
        SoRotationDragger* turn = handles.at(axis)->getDraggerContainer()->getDragger();
        turn->color = colour;
        SO_GET_PART(turn, "rotator", SoRotatorGeometry)->arcRadius = handleRadius;
    }

    placeGizmos();
}

void TaskMove::open()
{
    TaskDialog::open();
    attachGizmos();
}

void TaskMove::attachGizmos()
{
    if (!gizmos || attached || target.expired()) {
        return;
    }

    viewer = viewerFor(target->getDocument());
    if (!viewer) {
        return;
    }

    // Nothing is in edit, so the gizmos go straight into the scene in global
    // coordinates rather than under an edit root
    Base::Placement global;
    gizmos->attachViewer(viewer, global);

    // Its top part goes in, as an edit root takes it for the feature gizmos: Coin's
    // getPart() hands out only leaf parts, and the kit itself would hide the handles
    // from a search of the scene
    attached = (*gizmos->getChildren())[0];
    static_cast<SoSeparator*>(viewer->getSceneGraph())->addChild(attached);
}

void TaskMove::detachGizmos()
{
    if (attached && viewer) {
        auto* root = static_cast<SoSeparator*>(viewer->getSceneGraph());
        const int index = root->findChild(attached);
        if (index >= 0) {
            root->removeChild(index);
        }
    }
    attached = nullptr;

    gizmos.reset();
}

void TaskMove::hideGizmos()
{
    // Enter in a value box closes the dialog from inside that box's own signal, so the
    // gizmos and their boxes only go out of sight here and are deleted with the dialog
    if (gizmos) {
        gizmos->visible = false;
    }
}

Base::Vector3d TaskMove::travel() const
{
    return Base::Vector3d(
        distances[0]->value().getValue(),
        distances[1]->value().getValue(),
        distances[2]->value().getValue()
    );
}

void TaskMove::placeGizmos()
{
    if (!gizmos) {
        return;
    }

    const Base::Vector3d moved = travel();
    const Base::Vector3d middle = centre + moved;

    // A handle being dragged must not be stood anywhere else, even where it already is:
    // resetting its frame mid-drag makes Coin report a bogus jump. Only handles whose
    // spot changed are moved, and a drag never changes its own handle's spot
    const auto moves = [this](Gizmo* gizmo, const Base::Vector3d& spot) {
        return !gizmosPlaced || !gizmo->getDraggerPlacement().pos.equals(toSb(spot), 1e-6F);
    };

    for (std::size_t axis = 0; axis < 3; ++axis) {
        // An arrow's tip shows its own distance, so its foot takes the other two
        const auto index = static_cast<unsigned short>(axis);
        const Base::Vector3d foot = middle - axes.at(axis) * moved[index];
        if (moves(arrows.at(axis), foot)) {
            arrows.at(axis)->Gizmo::setDraggerPlacement(foot, axes.at(axis));
        }

        RotationGizmo* handle = handles.at(axis);
        if (moves(handle, middle)) {
            handle->Gizmo::setDraggerPlacement(middle, handleDirections.at(axis));
            handle->getDraggerContainer()->setArcNormalDirection(toSb(axes.at(axis)));
        }
    }
    gizmosPlaced = true;
}

void TaskMove::apply()
{
    App::DocumentObject* object = target.get<App::DocumentObject>();
    if (!object) {
        return;
    }
    auto* property = object->getPlacementProperty();
    if (!property) {
        return;
    }

    const auto turn = [this](std::size_t axis) {
        return Base::Rotation(axes.at(axis), Base::toRadians(angles.at(axis)->value().getValue()));
    };
    // Turned about X first, then Y, then Z, about the middle of the object
    const Base::Rotation rotation = turn(2) * turn(1) * turn(0);
    const Base::Placement change = Base::Placement(centre + travel(), rotation)
        * Base::Placement(-centre, Base::Rotation());

    property->setValue(parent.inverse() * change * parent * start);
}

bool TaskMove::accept()
{
    if (App::DocumentObject* object = target.get<App::DocumentObject>()) {
        object->getDocument()->recompute();
    }
    App::GetApplication().commitTransaction(transaction);
    transaction = 0;
    hideGizmos();
    return true;
}

bool TaskMove::reject()
{
    if (App::DocumentObject* object = target.get<App::DocumentObject>()) {
        if (auto* property = object->getPlacementProperty()) {
            property->setValue(start);
        }
    }
    App::GetApplication().abortTransaction(transaction);
    transaction = 0;
    hideGizmos();
    return true;
}

#include "moc_TaskMove.cpp"
