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

#include "MeasurePreview.h"

#include <cmath>
#include <numbers>

#include <BRepAdaptor_Curve.hxx>
#include <BRepAdaptor_Surface.hxx>
#include <BRepExtrema_DistShapeShape.hxx>
#include <Standard_Failure.hxx>
#include <TopAbs_ShapeEnum.hxx>
#include <TopoDS.hxx>
#include <TopoDS_Shape.hxx>
#include <gp_Circ.hxx>
#include <gp_Lin.hxx>

#include <Inventor/nodes/SoAnnotation.h>
#include <Inventor/nodes/SoBaseColor.h>
#include <Inventor/nodes/SoCoordinate3.h>
#include <Inventor/nodes/SoDrawStyle.h>
#include <Inventor/nodes/SoLineSet.h>
#include <Inventor/nodes/SoPickStyle.h>
#include <Inventor/nodes/SoSeparator.h>
#include <Inventor/nodes/SoSwitch.h>
#include <Inventor/nodes/SoTranslation.h>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Link.h>
#include <Base/Quantity.h>
#include <Base/UnitsApi.h>
#include <Gui/Application.h>
#include <Gui/MainWindow.h>
#include <Gui/SoLabelNodes.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>
#include <Mod/Measure/App/MeasureAngle.h>
#include <Mod/Measure/App/MeasureArea.h>
#include <Mod/Measure/App/MeasureDistance.h>
#include <Mod/Measure/App/MeasureLength.h>
#include <Mod/Measure/App/MeasureRadius.h>
#include <Mod/Part/App/PartFeature.h>
#include <Mod/Part/App/Tools.h>

using namespace MeasureGui;

namespace
{
/// In the unit the Measure tool shows its results in (see preferredUnitForMeasureType in
/// TaskMeasure), so a preview reads the same as the measurement a click makes
QString format(double value, const Base::Unit& unit)
{
    double factor = 1.0;
    std::string unitString;
    Base::UnitsApi::schemaTranslate(Base::Quantity(1.0, unit), factor, unitString);
    if (factor == 0.0 || unitString.empty()) {
        return QString::fromStdString(
            Base::UnitsApi::toUnicodeSuperscript(Base::Quantity(value, unit).getUserString())
        );
    }

    QString number = QString::number(value / factor, 'f', Base::UnitsApi::getDecimals());
    return number + QLatin1Char(' ')
        + QString::fromStdString(Base::UnitsApi::toUnicodeSuperscript(unitString));
}

Base::Vector3d toVector(const gp_Pnt& point)
{
    return Base::Vector3d(point.X(), point.Y(), point.Z());
}

/// Whether the item's geometry has a measure handler; the same test the Measure tool makes
bool isMeasurable(const App::MeasureSelectionItem& item)
{
    App::DocumentObject* sub = item.object.getSubObject();
    if (!sub) {
        return false;
    }
    if (auto link = freecad_cast<App::Link*>(sub)) {
        sub = link->getLinkedObject(true);
    }
    std::string module = Base::Type::getModuleName(sub->getTypeId().getName());
    return App::MeasureManager::hasMeasureHandler(module.c_str());
}

TopoDS_Shape shapeOf(const App::SubObjectT& item)
{
    return Part::Feature::getShape(
        item.getObject(),
        Part::ShapeOption::NeedSubElement | Part::ShapeOption::ResolveLink
            | Part::ShapeOption::Transform,
        item.getSubName().c_str()
    );
}

/// A cylinder or cone measures by its axis, a line, as MeasureAngle does
bool isAxisBearingFace(const TopoDS_Shape& shape)
{
    if (shape.IsNull() || shape.ShapeType() != TopAbs_FACE) {
        return false;
    }
    GeomAbs_SurfaceType type = BRepAdaptor_Surface(TopoDS::Face(shape)).GetType();
    return type == GeomAbs_Cylinder || type == GeomAbs_Cone;
}

double acute(double angle)
{
    angle = std::fabs(angle);
    return angle > std::numbers::pi / 2.0 ? std::numbers::pi - angle : angle;
}
}  // namespace

MeasurePreview::MeasurePreview()
    : Gui::SelectionObserver(true, Gui::ResolveMode::NoResolve)
{
    root = new SoSwitch;
    root->ref();
    root->setName("MeasurePreview");

    auto annotation = new SoAnnotation;
    annotation->renderCaching = SoSeparator::OFF;
    root->addChild(annotation);

    // Never under the cursor itself, or hovering it would change what is measured
    auto pickStyle = new SoPickStyle;
    pickStyle->style = SoPickStyle::UNPICKABLE;
    annotation->addChild(pickStyle);

    auto color = new SoBaseColor;
    color->rgb.setValue(0.12F, 0.53F, 0.90F);
    annotation->addChild(color);

    lineSwitch = new SoSwitch;
    auto lineGroup = new SoSeparator;
    auto lineStyle = new SoDrawStyle;
    lineStyle->lineWidth = 2.0F;
    lineStyle->linePattern = 0xF0F0;
    lineCoords = new SoCoordinate3;
    lineGroup->addChild(lineStyle);
    lineGroup->addChild(lineCoords);
    lineGroup->addChild(new SoLineSet);
    lineSwitch->addChild(lineGroup);
    annotation->addChild(lineSwitch);

    auto labelGroup = new SoSeparator;
    labelPlace = new SoTranslation;
    label = new Gui::SoFrameLabel;
    label->setName(labelName);
    label->textColor.setValue(1.0F, 1.0F, 1.0F);
    label->justification = Gui::SoFrameLabel::CENTER;
    label->horAlignment = SoImage::CENTER;
    label->vertAlignment = SoImage::HALF;
    label->border = false;
    label->backgroundUseBaseColor = true;
    labelGroup->addChild(labelPlace);
    labelGroup->addChild(label);
    annotation->addChild(labelGroup);

    clear();

    // One computation once the cursor settles, not one per element crossed on the way
    timer.setSingleShot(true);
    timer.setInterval(50);
    connect(&timer, &QTimer::timeout, this, &MeasurePreview::refresh);
}

MeasurePreview::~MeasurePreview()
{
    detachSelection();
    detach();
    root->unref();
}

void MeasurePreview::onSelectionChanged(const Gui::SelectionChanges& msg)
{
    switch (msg.Type) {
        case Gui::SelectionChanges::SetPreselect:
        case Gui::SelectionChanges::RmvPreselect:
            // Moving to a new element removes the old preselection first; waiting for the
            // cursor to settle keeps the value from blinking out in between
            timer.start();
            break;
        case Gui::SelectionChanges::AddSelection:
        case Gui::SelectionChanges::RmvSelection:
        case Gui::SelectionChanges::SetSelection:
        case Gui::SelectionChanges::ClrSelection:
            // A pick makes the real measurement; the preview waits for the next hover
            timer.stop();
            clear();
            break;
        default:
            break;
    }
}

void MeasurePreview::refresh()
{
    const Gui::SelectionChanges& hovered = Gui::Selection().getPreselection();
    App::Document* doc = hovered.Object.getDocument();
    if (!doc || hovered.Object.getObjectName().empty()) {
        clear();
        return;
    }

    App::MeasureSelection selection;
    for (const auto& picked :
         Gui::Selection().getSelection(doc->getName(), Gui::ResolveMode::NoResolve)) {
        App::SubObjectT sub(picked.pObject, picked.SubName);
        if (sub == hovered.Object) {
            // Its real measurement is already on screen
            clear();
            return;
        }
        selection.push_back({sub, Base::Vector3d(picked.x, picked.y, picked.z)});
    }
    selection.push_back({hovered.Object, Base::Vector3d(hovered.x, hovered.y, hovered.z)});

    if (selection.size() > 2) {
        clear();
        return;
    }
    for (const auto& item : selection) {
        if (!isMeasurable(item)) {
            clear();
            return;
        }
    }

    std::optional<Preview> preview;
    try {
        preview = compute(selection);
    }
    catch (const Base::Exception&) {
    }
    catch (const Standard_Failure&) {
    }

    if (preview) {
        show(*preview);
    }
    else {
        clear();
    }
}

std::optional<MeasurePreview::Preview> MeasurePreview::compute(App::MeasureSelection selection)
{
    auto types = App::MeasureManager::getValidMeasureTypes(selection, "");
    if (types.empty()) {
        return {};
    }
    const std::string& kind = types.front()->identifier;

    if (selection.size() == 1) {
        return single(selection.front().object, kind);
    }
    if (kind == "ANGLE") {
        return angle(selection);
    }
    if (kind == "DISTANCE" || kind == "DISTANCEFREE") {
        return distance(selection, kind);
    }
    return {};
}

std::optional<MeasurePreview::Preview> MeasurePreview::single(
    App::SubObjectT item,
    const std::string& kind
)
{
    if (kind == "LENGTH") {
        auto info = Measure::lengthInfo(item);
        if (info && info->valid) {
            return Preview {format(info->length, Base::Unit::Length), info->placement.getPosition(), {}};
        }
    }
    else if (kind == "RADIUS" || kind == "DIAMETER") {
        auto info = Measure::radiusInfo(item);
        if (info && info->valid) {
            return Preview {
                QStringLiteral("R ") + format(info->radius, Base::Unit::Length),
                info->pointOnCurve,
                {}
            };
        }
    }
    else if (kind == "AREA") {
        auto info = Measure::areaInfo(item);
        if (info && info->valid) {
            return Preview {format(info->area, Base::Unit::Area), info->placement.getPosition(), {}};
        }
    }
    return {};
}

std::optional<MeasurePreview::Preview> MeasurePreview::distance(
    App::MeasureSelection selection,
    const std::string& kind
)
{
    Base::Vector3d from;
    Base::Vector3d to;

    if (kind == "DISTANCEFREE") {
        // Between the points picked on the two items
        from = selection[0].pickedPoint;
        to = selection[1].pickedPoint;
    }
    else {
        auto info1 = Measure::distanceInfo(selection[0].object);
        auto info2 = Measure::distanceInfo(selection[1].object);
        if (!info1 || !info1->valid || !info2 || !info2->valid) {
            return {};
        }
        const TopoDS_Shape& shape1 = info1->getShape();
        const TopoDS_Shape& shape2 = info2->getShape();

        // Two circles measure between their centres, as MeasureDistance does
        auto isCircle = [](const TopoDS_Shape& shape) {
            return !shape.IsNull() && shape.ShapeType() == TopAbs_EDGE
                && BRepAdaptor_Curve(TopoDS::Edge(shape)).GetType() == GeomAbs_Circle;
        };
        if (isCircle(shape1) && isCircle(shape2)) {
            from = toVector(BRepAdaptor_Curve(TopoDS::Edge(shape1)).Circle().Location());
            to = toVector(BRepAdaptor_Curve(TopoDS::Edge(shape2)).Circle().Location());
        }
        else {
            BRepExtrema_DistShapeShape measure(shape1, shape2);
            if (!measure.IsDone() || measure.NbSolution() < 1) {
                return {};
            }
            from = toVector(measure.PointOnShape1(1));
            to = toVector(measure.PointOnShape2(1));
        }
    }

    return Preview {
        format(Base::Distance(from, to), Base::Unit::Length),
        (from + to) / 2.0,
        std::make_pair(from, to)
    };
}

std::optional<MeasurePreview::Preview> MeasurePreview::angle(App::MeasureSelection selection)
{
    auto info1 = Measure::angleInfo(selection[0].object);
    auto info2 = Measure::angleInfo(selection[1].object);
    if (!info1 || !info1->valid || !info2 || !info2->valid) {
        return {};
    }

    gp_Vec d1(info1->orientation.x, info1->orientation.y, info1->orientation.z);
    gp_Vec d2(info2->orientation.x, info2->orientation.y, info2->orientation.z);
    if (d1.Magnitude() < Precision::Confusion() || d2.Magnitude() < Precision::Confusion()) {
        return {};
    }

    TopoDS_Shape s1 = shapeOf(selection[0].object);
    TopoDS_Shape s2 = shapeOf(selection[1].object);
    if (s1.IsNull() || s2.IsNull()) {
        return {};
    }
    bool line1 = isAxisBearingFace(s1) || s1.ShapeType() == TopAbs_EDGE;
    bool line2 = isAxisBearingFace(s2) || s2.ShapeType() == TopAbs_EDGE;

    Base::Vector3d at = (info1->position + info2->position) / 2.0;
    double radians {};
    if (line1 && line2) {
        // Aim each direction away from where the lines meet, as MeasureAngle does for edges
        gp_Lin lin1(gp_Pnt(info1->position.x, info1->position.y, info1->position.z), gp_Dir(d1));
        gp_Lin lin2(gp_Pnt(info2->position.x, info2->position.y, info2->position.z), gp_Dir(d2));
        gp_Pnt onA;
        gp_Pnt onB;
        Part::closestPointsOnLines(lin1, lin2, onA, onB);
        Base::Vector3d origin = (toVector(onA) + toVector(onB)) / 2.0;
        auto away = [&origin](gp_Vec dir, const Base::Vector3d& position) {
            Base::Vector3d toward = position - origin;
            if (toward.Length() > Precision::Confusion()
                && dir.Dot(gp_Vec(toward.x, toward.y, toward.z)) < 0) {
                dir.Reverse();
            }
            return dir;
        };
        bool axisCase = isAxisBearingFace(s1) || isAxisBearingFace(s2);
        radians = axisCase ? acute(d1.Angle(d2))
                           : away(d1, info1->position).Angle(away(d2, info2->position));
        at = origin;
    }
    else if (!line1 && !line2) {
        // Face normals stand at right angles to their faces
        radians = std::numbers::pi - d1.Angle(d2);
    }
    else {
        const gp_Vec& lineDir = line1 ? d1 : d2;
        const gp_Vec& normal = line1 ? d2 : d1;
        radians = std::numbers::pi / 2.0 - acute(lineDir.Angle(normal));
    }

    return Preview {format(radians * 180.0 / std::numbers::pi, Base::Unit::Angle), at, {}};
}

void MeasurePreview::show(const Preview& preview)
{
    auto view = qobject_cast<Gui::View3DInventor*>(Gui::getMainWindow()->activeWindow());
    if (!view || !attachTo(view->getViewer())) {
        clear();
        return;
    }

    label->string.setValue(preview.text.toUtf8().constData());
    labelPlace->translation.setValue(
        static_cast<float>(preview.at.x),
        static_cast<float>(preview.at.y),
        static_cast<float>(preview.at.z)
    );
    if (preview.line) {
        const auto& [from, to] = *preview.line;
        lineCoords->point.set1Value(
            0,
            static_cast<float>(from.x),
            static_cast<float>(from.y),
            static_cast<float>(from.z)
        );
        lineCoords->point.set1Value(
            1,
            static_cast<float>(to.x),
            static_cast<float>(to.y),
            static_cast<float>(to.z)
        );
        lineSwitch->whichChild = 0;
    }
    else {
        lineSwitch->whichChild = SO_SWITCH_NONE;
    }
    root->whichChild = 0;
}

void MeasurePreview::clear()
{
    root->whichChild = SO_SWITCH_NONE;
    label->string.setValue("");
}

bool MeasurePreview::attachTo(Gui::View3DInventorViewer* active)
{
    if (!active) {
        return false;
    }
    if (viewer == active) {
        return true;
    }

    detach();
    auto group = dynamic_cast<SoGroup*>(active->getSceneGraph());
    if (!group) {
        return false;
    }
    group->addChild(root);
    viewer = active;
    return true;
}

void MeasurePreview::detach()
{
    if (!viewer) {
        return;
    }
    if (auto group = dynamic_cast<SoGroup*>(viewer->getSceneGraph())) {
        int index = group->findChild(root);
        if (index >= 0) {
            group->removeChild(index);
        }
    }
    viewer = nullptr;
}

#include "moc_MeasurePreview.cpp"  // NOLINT
