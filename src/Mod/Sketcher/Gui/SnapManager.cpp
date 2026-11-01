// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2023 Pierre-Louis Boyer <pierrelouis.boyer@gmail.com>   *
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

#include <algorithm>
#include <limits>

#include <QApplication>

#include <Base/Tools.h>
#include <Mod/Part/App/Geometry.h>
#include <Mod/Sketcher/App/SketchObject.h>
#include <Mod/Sketcher/App/SnapGeometry.h>

#include "SnapManager.h"
#include "ViewProviderSketch.h"


using namespace SketcherGui;
using namespace Sketcher;

/************************************ Attorney *******************************************/

inline int ViewProviderSketchSnapAttorney::getPreselectPoint(const ViewProviderSketch& vp)
{
    return vp.getPreselectPoint();
}

inline int ViewProviderSketchSnapAttorney::getPreselectCross(const ViewProviderSketch& vp)
{
    return vp.getPreselectCross();
}

inline int ViewProviderSketchSnapAttorney::getPreselectCurve(const ViewProviderSketch& vp)
{
    return vp.getPreselectCurve();
}

inline float ViewProviderSketchSnapAttorney::getSketchUnitsPerPixel(const ViewProviderSketch& vp)
{
    return vp.getSketchUnitsPerPixel();
}

/**************************** ParameterObserver nested class *****************************/
SnapManager::ParameterObserver::ParameterObserver(SnapManager& client)
    : client(client)
{
    initParameters();
    subscribeToParameters();
}

SnapManager::ParameterObserver::~ParameterObserver()
{
    unsubscribeToParameters();
}

void SnapManager::ParameterObserver::initParameters()
{
    // static map to avoid substantial if/else branching
    //
    // key->first               => String of parameter,
    // key->second              => Update function to be called for the parameter,
    str2updatefunction = {
        {"Snap", [this](const std::string& param) { updateSnapParameter(param); }},
        {"SnapToObjects", [this](const std::string& param) { updateSnapToObjectParameter(param); }},
        {"SnapToGrid", [this](const std::string& param) { updateSnapToGridParameter(param); }},
        {"SnapAngle", [this](const std::string& param) { updateSnapAngleParameter(param); }},
        {"SnapRadius", [this](const std::string& param) { updateSnapRadiusParameter(param); }},
        {"GridSnapTolerance",
         [this](const std::string& param) { updateGridSnapToleranceParameter(param); }},
    };

    for (auto& val : str2updatefunction) {
        auto string = val.first;
        auto function = val.second;

        function(string);
    }
}

void SnapManager::ParameterObserver::updateSnapParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.snapRequested = hGrp->GetBool(parametername.c_str(), true);
}

void SnapManager::ParameterObserver::updateSnapToObjectParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.snapToObjectsRequested = hGrp->GetBool(parametername.c_str(), true);
}

void SnapManager::ParameterObserver::updateSnapToGridParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.snapToGridRequested = hGrp->GetBool(parametername.c_str(), true);
}

void SnapManager::ParameterObserver::updateSnapAngleParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.snapAngle
        = fmod(Base::toRadians(hGrp->GetFloat(parametername.c_str(), 5.)), 2 * std::numbers::pi);
}

void SnapManager::ParameterObserver::updateSnapRadiusParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.snapRadiusPixels = std::max(1.0, hGrp->GetFloat(parametername.c_str(), 8.0));
}

void SnapManager::ParameterObserver::updateGridSnapToleranceParameter(const std::string& parametername)
{
    ParameterGrp::handle hGrp = getParameterGrpHandle();

    client.gridSnapTolerancePixels = std::max(0.0, hGrp->GetFloat(parametername.c_str(), 8.0));
}

void SnapManager::ParameterObserver::subscribeToParameters()
{
    try {
        ParameterGrp::handle hGrp = getParameterGrpHandle();
        hGrp->Attach(this);
    }
    catch (const Base::ValueError& e) {  // ensure that if parameter strings are not well-formed,
                                         // the exception is not propagated
        Base::Console().developerError("SnapManager", "Malformed parameter string: %s\n", e.what());
    }
}

void SnapManager::ParameterObserver::unsubscribeToParameters()
{
    try {
        ParameterGrp::handle hGrp = getParameterGrpHandle();
        hGrp->Detach(this);
    }
    catch (const Base::ValueError& e) {  // ensure that if parameter strings are not well-formed,
                                         // the program is not terminated when calling the noexcept
                                         // destructor.
        Base::Console().developerError("SnapManager", "Malformed parameter string: %s\n", e.what());
    }
}

void SnapManager::ParameterObserver::OnChange(Base::Subject<const char*>& rCaller, const char* sReason)
{
    (void)rCaller;

    auto key = str2updatefunction.find(sReason);
    if (key != str2updatefunction.end()) {
        auto string = key->first;
        auto function = key->second;

        function(string);
    }
}

ParameterGrp::handle SnapManager::ParameterObserver::getParameterGrpHandle()
{
    return App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Sketcher/Snap"
    );
}

//**************************** SnapManager class ******************************

SnapManager::SnapManager(ViewProviderSketch& vp)
    : viewProvider(vp)
    , angleSnapRequested(false)
    , referencePoint(Base::Vector2d(0., 0.))
    , lastMouseAngle(0.0)
{
    // Create parameter observer and initialise watched parameters
    pObserver = std::make_unique<SnapManager::ParameterObserver>(*this);
}

SnapManager::~SnapManager()
{}

Base::Vector2d SnapManager::snap(Base::Vector2d inputPos, SnapType mask)
{
    using Sketcher::SnapGeometry::SnapKind;

    lastSnapResult.reset();

    if (!snapRequested) {
        return inputPos;
    }

    Base::Vector2d snapPos = inputPos;

    // In order of priority:

    // 1 - Snap at an angle
    if ((static_cast<int>(mask) & static_cast<int>(SnapType::Angle)) && angleSnapRequested
        && QApplication::keyboardModifiers() == Qt::ControlModifier
        && snapAtAngle(inputPos, snapPos)) {
        return snapPos;
    }
    else {
        lastMouseAngle = 0.0;
    }

    // 2 - Snap to objects (may partially snap to axis, leaving other coordinate for grid)
    if ((static_cast<int>(mask)
         & (static_cast<int>(SnapType::Point) | static_cast<int>(SnapType::Edge)))
        && snapToObjectsRequested) {
        if (snapToObject(inputPos, snapPos, mask)) {
            return snapPos;  // Full snap (point or curve) - done
        }
        // if false was returned but snapPos was modified (axis case), continue to grid snap
    }

    // 3 - Snap to grid: a grid line or intersection within tolerance, while the grid is on
    // screen. An axis lock survives this because the axes run through grid points.
    if ((static_cast<int>(mask) & static_cast<int>(SnapType::Grid)) && snapToGridRequested
        && viewProvider.ShowGrid.getValue()) {
        Base::Vector2d gridSnapResult = snapPos;
        if (snapToGrid(snapPos, gridSnapResult)) {
            if (lastSnapResult) {
                // An axis lock the grid then finished off: the axis is what caught the
                // pointer, but the point it lands on is the grid's, and that is where
                // the marker belongs.
                lastSnapResult->position = gridSnapResult;
            }
            else {
                lastSnapResult = SnapResult {SnapKind::Grid, gridSnapResult};
            }
            return gridSnapResult;
        }
    }

    return snapPos;
}

bool SnapManager::snapAtAngle(Base::Vector2d inputPos, Base::Vector2d& snapPos)
{
    double length = (inputPos - referencePoint).Length();

    double angle1 = (inputPos - referencePoint).Angle();
    double angle2 = angle1 + (angle1 < 0. ? 2 : -2) * std::numbers::pi;
    lastMouseAngle = abs(angle1 - lastMouseAngle) < abs(angle2 - lastMouseAngle) ? angle1 : angle2;

    double angle = round(lastMouseAngle / snapAngle) * snapAngle;
    snapPos = referencePoint + length * Base::Vector2d(cos(angle), sin(angle));

    return true;
}

namespace
{

/// Distance from a point to the closest point of a curve, or infinity when it cannot be found.
double distanceToCurve(const Part::GeomCurve& curve, const Base::Vector3d& point)
{
    try {
        double parameter = 0.0;
        if (curve.closestParameter(point, parameter)) {
            return (curve.pointAtParameter(parameter) - point).Length();
        }
    }
    catch (const Base::Exception&) {
        // fall through
    }
    return std::numeric_limits<double>::infinity();
}

}  // namespace

std::vector<Sketcher::SnapGeometry::SnapCandidate> SnapManager::curveSnapCandidates(
    int curveGeoId,
    const Base::Vector2d& cursor,
    double radius
) const
{
    using namespace Sketcher::SnapGeometry;

    std::vector<SnapCandidate> candidates;

    Sketcher::SketchObject* obj = viewProvider.getSketchObject();
    const Part::Geometry* geo = obj->getGeometry(curveGeoId);
    if (!geo) {
        return candidates;
    }

    if (auto mid = midpoint(geo)) {
        candidates.push_back({SnapKind::Midpoint, *mid});
    }
    for (const Base::Vector2d& quadrant : quadrantPoints(geo)) {
        candidates.push_back({SnapKind::Quadrant, quadrant});
    }

    // Crossings with every other curve that passes near the cursor. The sketch stores its axes as
    // unit segments, so they are stood in for by infinite lines.
    const Base::Vector3d cursor3d(cursor.x, cursor.y, 0.0);
    auto addCrossingsWith = [&](const Part::Geometry* other, int otherGeoId) {
        const auto* otherCurve = dynamic_cast<const Part::GeomCurve*>(other);
        if (!otherCurve || other == geo || distanceToCurve(*otherCurve, cursor3d) > radius) {
            return;
        }
        for (const Base::Vector2d& crossing : intersections(geo, other)) {
            candidates.push_back({SnapKind::Intersection, crossing, otherGeoId});
        }
    };

    static const Part::GeomLine horizontalAxis(Base::Vector3d(0, 0, 0), Base::Vector3d(1, 0, 0));
    static const Part::GeomLine verticalAxis(Base::Vector3d(0, 0, 0), Base::Vector3d(0, 1, 0));
    addCrossingsWith(&horizontalAxis, Sketcher::GeoEnum::HAxis);
    addCrossingsWith(&verticalAxis, Sketcher::GeoEnum::VAxis);

    const auto& internals = obj->getInternalGeometry();
    for (std::size_t i = 0; i < internals.size(); ++i) {
        addCrossingsWith(internals[i], static_cast<int>(i));
    }
    const auto& externals = obj->getExternalGeometry();
    for (std::size_t i = 2; i < externals.size(); ++i) {  // 0 and 1 are the axes
        addCrossingsWith(externals[i], -static_cast<int>(i) - 1);
    }

    return candidates;
}

bool SnapManager::snapToObject(Base::Vector2d inputPos, Base::Vector2d& snapPos, SnapType mask)
{
    using Sketcher::SnapGeometry::SnapKind;

    Sketcher::SketchObject* Obj = viewProvider.getSketchObject();
    int geoId = GeoEnum::GeoUndef;
    Sketcher::PointPos posId = Sketcher::PointPos::none;

    int VtId = ViewProviderSketchSnapAttorney::getPreselectPoint(viewProvider);
    int CrsId = ViewProviderSketchSnapAttorney::getPreselectCross(viewProvider);
    int CrvId = ViewProviderSketchSnapAttorney::getPreselectCurve(viewProvider);

    if ((static_cast<int>(mask) & static_cast<int>(SnapType::Point)) && (CrsId == 0 || VtId >= 0)) {
        if (CrsId == 0) {
            geoId = Sketcher::GeoEnum::RtPnt;
            posId = Sketcher::PointPos::start;
        }
        else if (VtId >= 0) {
            Obj->getGeoVertexIndex(VtId, geoId, posId);
        }

        snapPos.x = Obj->getPoint(geoId, posId).x;
        snapPos.y = Obj->getPoint(geoId, posId).y;
        lastSnapResult = SnapResult {CrsId == 0 ? SnapKind::Origin : SnapKind::Vertex, snapPos};
        return true;
    }
    else if (static_cast<int>(mask) & static_cast<int>(SnapType::Edge)) {
        if (CrsId == 1) {  // H_Axis
            snapPos.y = 0;
            lastSnapResult = SnapResult {SnapKind::Axis, snapPos};
            // dont return true, allow grid snap to handle X coordinate
            return false;
        }
        else if (CrsId == 2) {  // V_Axis
            snapPos.x = 0;
            lastSnapResult = SnapResult {SnapKind::Axis, snapPos};
            // dont return true, allow grid snap to handle Y coordinate
            return false;
        }
        else if (CrvId >= 0 || CrvId <= Sketcher::GeoEnum::RefExt) {  // Curves

            const Part::Geometry* geo = Obj->getGeometry(CrvId);
            auto curve = dynamic_cast<const Part::GeomCurve*>(geo);
            if (!curve) {
                return false;
            }

            // Special points of the curve first: crossings, midpoint, quadrants.
            const double radius = snapRadiusPixels
                * ViewProviderSketchSnapAttorney::getSketchUnitsPerPixel(viewProvider);
            const auto picked = Sketcher::SnapGeometry::pickSnap(
                curveSnapCandidates(CrvId, inputPos, radius),
                inputPos,
                radius
            );
            if (picked) {
                snapPos = picked->point;
                lastSnapResult = SnapResult {picked->kind, snapPos, CrvId, picked->otherGeoId};
                return true;
            }

            // Otherwise the closest point of the curve.
            Base::Vector3d pointToOverride(inputPos.x, inputPos.y, 0.);
            double pointParam = 0.0;
            try {
                curve->closestParameter(pointToOverride, pointParam);
                pointToOverride = curve->pointAtParameter(pointParam);
            }
            catch (Base::CADKernelError& e) {
                e.reportException();
                return false;
            }

            snapPos.x = pointToOverride.x;
            snapPos.y = pointToOverride.y;
            lastSnapResult = SnapResult {SnapKind::OnCurve, snapPos, CrvId};

            return true;
        }
    }
    return false;
}

bool SnapManager::snapToGrid(Base::Vector2d inputPos, Base::Vector2d& snapPos)
{
    snapPos = inputPos;

    const double spacing = viewProvider.getGridSize();
    const double unitsPerPixel = ViewProviderSketchSnapAttorney::getSketchUnitsPerPixel(viewProvider);
    if (spacing <= 0.0 || unitsPerPixel <= 0.0) {
        return false;
    }

    // Keep free travel between grid lines even when the grid is dense on screen: the snap
    // band on each side of a line never exceeds a third of the pitch.
    const double pitchPixels = spacing / unitsPerPixel;
    const double tolerance = std::min(gridSnapTolerancePixels, pitchPixels / 3.0) * unitsPerPixel;

    const auto snapped = Sketcher::SnapGeometry::snapToGrid(inputPos, spacing, tolerance);
    if (!snapped) {
        return false;
    }
    snapPos = *snapped;
    return true;
}

void SnapManager::setAngleSnapping(bool enable, Base::Vector2d referencepoint)
{
    angleSnapRequested = enable;
    referencePoint = referencepoint;
}

Base::Vector2d SketcherGui::SnapManager::SnapHandle::compute(SnapType mask)
{
    if (!mgr) {
        return cursorPos;
    }
    return mgr->snap(cursorPos, mask);
}
