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
 *   SnapManager initially funded by the Open Toolchain Foundation         *
 ***************************************************************************/

#pragma once

#include <optional>

#include <App/Application.h>

#include <Base/Tools2D.h>
#include <Base/Vector3D.h>
#include <Mod/Sketcher/App/SnapGeometry.h>

namespace SketcherGui
{

class ViewProviderSketch;


class ViewProviderSketchSnapAttorney
{
private:
    static inline int getPreselectPoint(const ViewProviderSketch& vp);
    static inline int getPreselectCross(const ViewProviderSketch& vp);
    static inline int getPreselectCurve(const ViewProviderSketch& vp);
    static inline float getSketchUnitsPerPixel(const ViewProviderSketch& vp);

    friend class SnapManager;
};

enum class SnapType
{
    None = 0x0,
    Angle = 0x1,
    Point = 0x2,
    Edge = 0x4,
    Grid = 0x8,

    All = Angle | Point | Edge | Grid
};

/// The kinds of either mask.
constexpr SnapType operator|(SnapType lhs, SnapType rhs)
{
    return static_cast<SnapType>(static_cast<int>(lhs) | static_cast<int>(rhs));
}

/// The kinds both masks have.
constexpr SnapType operator&(SnapType lhs, SnapType rhs)
{
    return static_cast<SnapType>(static_cast<int>(lhs) & static_cast<int>(rhs));
}

/// The kinds @a type leaves out, so a caller can ask for everything but one of them.
constexpr SnapType operator~(SnapType type)
{
    return static_cast<SnapType>(~static_cast<int>(type) & static_cast<int>(SnapType::All));
}

/* This class is used to manage the overriding of mouse pointer coordinates in Sketcher
 *  (in Edit-Mode) depending on the situation. Those situations are in priority order :
 *  1 - Snap at angle: For tools like Slot, Arc, Line, Ellipse, this enables to constrain the angle
 * at steps of 5° (or customized angle). This is useful to make features at a certain angle (45° for
 * example).
 *  2 - Snap to object: This snaps the mouse pointer onto the preselected object: the origin, a
 * vertex, an axis, or a curve. On a curve the pointer prefers, within the snap radius, the curve's
 * crossings with other geometry, its midpoint and its quadrant points, and otherwise lands on the
 * closest point of the curve.
 *  3 - Snap to grid: While the grid is displayed and nothing else caught the pointer, it snaps
 * to a grid line or intersection that comes within a few pixels, and is otherwise left free.
 *
 * The snap radius (in pixels) is shared with preselection in edit mode, so whatever the pointer
 * snaps to is also what is preselected, and autoconstraints follow.
 */
class SnapManager
{

    /** @brief      Class for monitoring changes in parameters affecting Snapping
     *  @details
     *
     * This nested class is a helper responsible for attaching to the parameters relevant for
     * SnapManager, initialising the SnapManager to the current configuration
     * and handle in real time any change to their values.
     */
    class ParameterObserver: public ParameterGrp::ObserverType
    {
    public:
        explicit ParameterObserver(SnapManager& client);
        ~ParameterObserver() override;

        void subscribeToParameters();

        void unsubscribeToParameters();

        /** Observer for parameter group. */
        void OnChange(Base::Subject<const char*>& rCaller, const char* sReason) override;

    private:
        void initParameters();
        void updateSnapParameter(const std::string& parametername);
        void updateSnapToObjectParameter(const std::string& parametername);
        void updateSnapToGridParameter(const std::string& parametername);
        void updateSnapAngleParameter(const std::string& parametername);
        void updateSnapRadiusParameter(const std::string& parametername);
        void updateGridSnapToleranceParameter(const std::string& parametername);

        static ParameterGrp::handle getParameterGrpHandle();

    private:
        std::map<std::string, std::function<void(const std::string&)>> str2updatefunction;
        SnapManager& client;
    };

public:
    explicit SnapManager(ViewProviderSketch& vp);
    ~SnapManager();

    Base::Vector2d snap(Base::Vector2d inputPos, SnapType mask);
    bool snapAtAngle(Base::Vector2d inputPos, Base::Vector2d& snapPos);
    bool snapToObject(Base::Vector2d inputPos, Base::Vector2d& snapPos, SnapType mask);
    bool snapToGrid(Base::Vector2d inputPos, Base::Vector2d& snapPos);

    void setAngleSnapping(bool enable, Base::Vector2d referencepoint);

    /// What the last call to snap() landed on.
    struct SnapResult
    {
        Sketcher::SnapGeometry::SnapKind kind = Sketcher::SnapGeometry::SnapKind::None;
        Base::Vector2d position;
        /// The curve a midpoint, quadrant, crossing or on-curve snap was taken from.
        int geoId = Sketcher::GeoEnum::GeoUndef;
        /// The other curve of a crossing.
        int otherGeoId = Sketcher::GeoEnum::GeoUndef;
    };

    /// The snap the most recent snap() produced, if it snapped at all.
    std::optional<SnapResult> lastSnap() const
    {
        return lastSnapResult;
    }

    /// Forgets the last snap, so a mouse move that never asked to snap shows no marker.
    void resetLastSnap()
    {
        lastSnapResult.reset();
    }

    /// Screen distance, in pixels, within which points attract the pointer.
    double getSnapRadiusPixels() const
    {
        return snapRadiusPixels;
    }

    struct SnapHandle
    {
        SnapManager* mgr = nullptr;
        Base::Vector2d cursorPos;

        SnapHandle(SnapManager* m, const Base::Vector2d& cursorPos)
            : mgr(m)
            , cursorPos(cursorPos)
        {}

        Base::Vector2d compute(SnapType mask = SnapType::All);
    };

private:
    /// Reference to ViewProviderSketch in order to access the public and the Attorney Interface
    ViewProviderSketch& viewProvider;

    bool angleSnapRequested;
    bool snapRequested;
    bool snapToObjectsRequested;
    bool snapToGridRequested;

    Base::Vector2d referencePoint;
    double lastMouseAngle;

    double snapAngle;
    double snapRadiusPixels = 8.0;
    double gridSnapTolerancePixels = 8.0;

    std::optional<SnapResult> lastSnapResult;

    /// Points on the preselected curve worth snapping to, within the snap radius.
    std::vector<Sketcher::SnapGeometry::SnapCandidate> curveSnapCandidates(
        int curveGeoId,
        const Base::Vector2d& cursor,
        double radius
    ) const;

    /// Observer to track all the needed parameters.
    std::unique_ptr<SnapManager::ParameterObserver> pObserver;
};


}  // namespace SketcherGui
