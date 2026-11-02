// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <FCConfig.h>

#include <algorithm>
#include <cmath>
#include <numbers>

#include <Base/Tools.h>

#include <Mod/Part/App/Geometry.h>
#include <Mod/Sketcher/App/SnapGeometry.h>

using namespace Sketcher;
using SnapGeometry::SnapCandidate;
using SnapGeometry::SnapKind;

TEST(SnapGeometryPickSnap, ReturnsNothingWhenNoCandidateWithinRadius)
{
    std::vector<SnapCandidate> candidates {
        {SnapKind::Vertex, Base::Vector2d(10.0, 0.0)},
    };

    auto picked = SnapGeometry::pickSnap(candidates, Base::Vector2d(0.0, 0.0), 5.0);

    EXPECT_FALSE(picked.has_value());
}

TEST(SnapGeometryPickSnap, PrefersHigherPriorityKindOverNearerLowerPriorityOne)
{
    std::vector<SnapCandidate> candidates {
        {SnapKind::Midpoint, Base::Vector2d(1.0, 0.0)},
        {SnapKind::Vertex, Base::Vector2d(3.0, 0.0)},
    };

    auto picked = SnapGeometry::pickSnap(candidates, Base::Vector2d(0.0, 0.0), 5.0);

    ASSERT_TRUE(picked.has_value());
    EXPECT_EQ(picked->kind, SnapKind::Vertex);
    EXPECT_DOUBLE_EQ(picked->point.x, 3.0);
}

TEST(SnapGeometryPickSnap, ChoosesNearestAmongSameKind)
{
    std::vector<SnapCandidate> candidates {
        {SnapKind::Vertex, Base::Vector2d(4.0, 0.0)},
        {SnapKind::Vertex, Base::Vector2d(0.0, 2.0)},
    };

    auto picked = SnapGeometry::pickSnap(candidates, Base::Vector2d(0.0, 0.0), 5.0);

    ASSERT_TRUE(picked.has_value());
    EXPECT_DOUBLE_EQ(picked->point.x, 0.0);
    EXPECT_DOUBLE_EQ(picked->point.y, 2.0);
}

TEST(SnapGeometryPickSnap, KeepsTheOtherCurveOfTheCrossingItPicks)
{
    // The sketcher constrains a crossing snap to both curves, so the pick must say which
    // crossing, and with it which other curve, it chose.
    std::vector<SnapCandidate> candidates {
        {SnapKind::Intersection, Base::Vector2d(3.0, 0.0), 7},
        {SnapKind::Intersection, Base::Vector2d(1.0, 0.0), Sketcher::GeoEnum::VAxis},
        {SnapKind::Midpoint, Base::Vector2d(0.5, 0.0)},
    };

    auto picked = SnapGeometry::pickSnap(candidates, Base::Vector2d(0.0, 0.0), 5.0);

    ASSERT_TRUE(picked.has_value());
    EXPECT_EQ(picked->kind, SnapKind::Intersection);
    EXPECT_EQ(picked->otherGeoId, Sketcher::GeoEnum::VAxis);
}

TEST(SnapGeometrySnapToGrid, LandsOnTheIntersectionWhenBothAxesAreWithinTolerance)
{
    auto snapped = SnapGeometry::snapToGrid(Base::Vector2d(3.9, 6.1), 1.0, 0.2);

    ASSERT_TRUE(snapped.has_value());
    EXPECT_DOUBLE_EQ(snapped->x, 4.0);
    EXPECT_DOUBLE_EQ(snapped->y, 6.0);
}

TEST(SnapGeometrySnapToGrid, SlidesAlongAGridLineWhenOnlyOneAxisIsWithinTolerance)
{
    auto snapped = SnapGeometry::snapToGrid(Base::Vector2d(3.9, 6.5), 1.0, 0.2);

    ASSERT_TRUE(snapped.has_value());
    EXPECT_DOUBLE_EQ(snapped->x, 4.0);
    EXPECT_DOUBLE_EQ(snapped->y, 6.5);
}

TEST(SnapGeometrySnapToGrid, LeavesThePointFreeAwayFromGridLines)
{
    EXPECT_FALSE(SnapGeometry::snapToGrid(Base::Vector2d(3.5, 6.5), 1.0, 0.2).has_value());
}

TEST(SnapGeometrySnapToGrid, HalfwayRoundsAwayFromZeroLikeTheGrid)
{
    auto snapped = SnapGeometry::snapToGrid(Base::Vector2d(2.5, -2.5), 1.0, 0.6);

    ASSERT_TRUE(snapped.has_value());
    EXPECT_DOUBLE_EQ(snapped->x, 3.0);
    EXPECT_DOUBLE_EQ(snapped->y, -3.0);
}

TEST(SnapGeometrySnapToGrid, UsesTheGivenSpacing)
{
    auto snapped = SnapGeometry::snapToGrid(Base::Vector2d(4.6, 10.3), 5.0, 0.5);

    ASSERT_TRUE(snapped.has_value());
    EXPECT_DOUBLE_EQ(snapped->x, 5.0);
    EXPECT_DOUBLE_EQ(snapped->y, 10.0);
}

TEST(SnapGeometrySnapToGrid, NeverMovesALockedCoordinate)
{
    auto snapped = SnapGeometry::snapToGrid(Base::Vector2d(3.9, 0.1), 1.0, 0.2, false, true);

    ASSERT_TRUE(snapped.has_value());
    EXPECT_DOUBLE_EQ(snapped->x, 4.0);
    EXPECT_DOUBLE_EQ(snapped->y, 0.1);
}

TEST(SnapGeometrySnapToGrid, DoesNothingForNonPositiveSpacingOrTolerance)
{
    EXPECT_FALSE(SnapGeometry::snapToGrid(Base::Vector2d(3.9, 6.1), 0.0, 0.2).has_value());
    EXPECT_FALSE(SnapGeometry::snapToGrid(Base::Vector2d(3.9, 6.1), 1.0, 0.0).has_value());
}

TEST(SnapGeometryMidpoint, LineSegmentMidpointIsHalfwayBetweenItsEnds)
{
    Part::GeomLineSegment line;
    line.setPoints(Base::Vector3d(0.0, 0.0, 0.0), Base::Vector3d(4.0, 2.0, 0.0));

    auto mid = SnapGeometry::midpoint(&line);

    ASSERT_TRUE(mid.has_value());
    EXPECT_DOUBLE_EQ(mid->x, 2.0);
    EXPECT_DOUBLE_EQ(mid->y, 1.0);
}

TEST(SnapGeometryMidpoint, ArcMidpointIsAtItsMiddleAngle)
{
    Part::GeomArcOfCircle arc;
    arc.setCenter(Base::Vector3d(1.0, 1.0, 0.0));
    arc.setRadius(2.0);
    arc.setRange(0.0, std::numbers::pi / 2.0, true);

    auto mid = SnapGeometry::midpoint(&arc);

    ASSERT_TRUE(mid.has_value());
    EXPECT_NEAR(mid->x, 1.0 + std::sqrt(2.0), 1e-9);
    EXPECT_NEAR(mid->y, 1.0 + std::sqrt(2.0), 1e-9);
}

TEST(SnapGeometryMidpoint, FullCircleHasNoMidpoint)
{
    Part::GeomCircle circle;
    circle.setCenter(Base::Vector3d(0.0, 0.0, 0.0));
    circle.setRadius(3.0);

    EXPECT_FALSE(SnapGeometry::midpoint(&circle).has_value());
}

namespace
{

bool containsPoint(const std::vector<Base::Vector2d>& points, double x, double y)
{
    return std::any_of(points.begin(), points.end(), [x, y](const Base::Vector2d& p) {
        return std::abs(p.x - x) < 1e-9 && std::abs(p.y - y) < 1e-9;
    });
}

}  // namespace

TEST(SnapGeometryQuadrantPoints, FullCircleOffersAllFourQuadrants)
{
    Part::GeomCircle circle;
    circle.setCenter(Base::Vector3d(1.0, 2.0, 0.0));
    circle.setRadius(3.0);

    auto quadrants = SnapGeometry::quadrantPoints(&circle);

    ASSERT_EQ(quadrants.size(), 4U);
    EXPECT_TRUE(containsPoint(quadrants, 4.0, 2.0));
    EXPECT_TRUE(containsPoint(quadrants, 1.0, 5.0));
    EXPECT_TRUE(containsPoint(quadrants, -2.0, 2.0));
    EXPECT_TRUE(containsPoint(quadrants, 1.0, -1.0));
}

TEST(SnapGeometryQuadrantPoints, ArcOffersOnlyTheQuadrantsInsideItsRange)
{
    Part::GeomArcOfCircle arc;
    arc.setCenter(Base::Vector3d(0.0, 0.0, 0.0));
    arc.setRadius(2.0);
    arc.setRange(Base::toRadians(30.0), Base::toRadians(200.0), true);

    auto quadrants = SnapGeometry::quadrantPoints(&arc);

    ASSERT_EQ(quadrants.size(), 2U);
    EXPECT_TRUE(containsPoint(quadrants, 0.0, 2.0));
    EXPECT_TRUE(containsPoint(quadrants, -2.0, 0.0));
}

TEST(SnapGeometryQuadrantPoints, ArcCrossingZeroDegreesOffersThatQuadrant)
{
    Part::GeomArcOfCircle arc;
    arc.setCenter(Base::Vector3d(0.0, 0.0, 0.0));
    arc.setRadius(2.0);
    arc.setRange(Base::toRadians(300.0), Base::toRadians(60.0), true);

    auto quadrants = SnapGeometry::quadrantPoints(&arc);

    ASSERT_EQ(quadrants.size(), 1U);
    EXPECT_TRUE(containsPoint(quadrants, 2.0, 0.0));
}

TEST(SnapGeometryQuadrantPoints, LineSegmentHasNoQuadrants)
{
    Part::GeomLineSegment line;
    line.setPoints(Base::Vector3d(0.0, 0.0, 0.0), Base::Vector3d(4.0, 2.0, 0.0));

    EXPECT_TRUE(SnapGeometry::quadrantPoints(&line).empty());
}

TEST(SnapGeometryQuadrantPoints, ArcBelowTheXAxisOffersTheBottomQuadrant)
{
    Part::GeomArcOfCircle arc;
    arc.setCenter(Base::Vector3d(0.0, 0.0, 0.0));
    arc.setRadius(2.0);
    arc.setRange(Base::toRadians(250.0), Base::toRadians(290.0), true);

    auto quadrants = SnapGeometry::quadrantPoints(&arc);

    ASSERT_EQ(quadrants.size(), 1U);
    EXPECT_TRUE(containsPoint(quadrants, 0.0, -2.0));
}

TEST(SnapGeometryIntersections, CrossingSegmentsMeetOnce)
{
    Part::GeomLineSegment a;
    a.setPoints(Base::Vector3d(0.0, 0.0, 0.0), Base::Vector3d(4.0, 4.0, 0.0));
    Part::GeomLineSegment b;
    b.setPoints(Base::Vector3d(0.0, 4.0, 0.0), Base::Vector3d(4.0, 0.0, 0.0));

    auto points = SnapGeometry::intersections(&a, &b);

    ASSERT_EQ(points.size(), 1U);
    EXPECT_TRUE(containsPoint(points, 2.0, 2.0));
}

TEST(SnapGeometryIntersections, SegmentsWhoseExtensionsCrossDoNotMeet)
{
    Part::GeomLineSegment a;
    a.setPoints(Base::Vector3d(0.0, 0.0, 0.0), Base::Vector3d(1.0, 1.0, 0.0));
    Part::GeomLineSegment b;
    b.setPoints(Base::Vector3d(0.0, 4.0, 0.0), Base::Vector3d(1.0, 3.0, 0.0));

    EXPECT_TRUE(SnapGeometry::intersections(&a, &b).empty());
}

TEST(SnapGeometryIntersections, SegmentThroughCircleMeetsItTwice)
{
    Part::GeomCircle circle;
    circle.setCenter(Base::Vector3d(0.0, 0.0, 0.0));
    circle.setRadius(2.0);
    Part::GeomLineSegment line;
    line.setPoints(Base::Vector3d(-5.0, 0.0, 0.0), Base::Vector3d(5.0, 0.0, 0.0));

    auto points = SnapGeometry::intersections(&line, &circle);

    ASSERT_EQ(points.size(), 2U);
    EXPECT_TRUE(containsPoint(points, -2.0, 0.0));
    EXPECT_TRUE(containsPoint(points, 2.0, 0.0));
}

TEST(SnapGeometryIntersections, SharedEndpointIsReportedOnce)
{
    Part::GeomLineSegment a;
    a.setPoints(Base::Vector3d(0.0, 0.0, 0.0), Base::Vector3d(2.0, 0.0, 0.0));
    Part::GeomLineSegment b;
    b.setPoints(Base::Vector3d(2.0, 0.0, 0.0), Base::Vector3d(2.0, 3.0, 0.0));

    auto points = SnapGeometry::intersections(&a, &b);

    ASSERT_EQ(points.size(), 1U);
    EXPECT_TRUE(containsPoint(points, 2.0, 0.0));
}
