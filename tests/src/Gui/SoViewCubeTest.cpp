// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <numbers>

#include <Inventor/SbMatrix.h>
#include <Inventor/SbRotation.h>
#include <Inventor/SbVec2s.h>
#include <Inventor/SoDB.h>
#include <Inventor/SoType.h>

#include <Gui/Inventor/SoViewCube.h>

using Gui::SoViewCube;
using PickId = Gui::SoNaviCube::PickId;

namespace
{
constexpr short viewportSize = 200;
constexpr float pi = std::numbers::pi_v<float>;

SbRotation frontView()
{
    return SbRotation(SbVec3f(1.0F, 0.0F, 0.0F), pi / 2.0F);
}

SbRotation isoView()
{
    return SbRotation(SbVec3f(0.0F, 0.0F, 1.0F), SbVec3f(1.0F, -1.0F, 1.0F));
}

/// The viewer pixel under an overlay point given as 0..1 with y down.
SbVec2s at(float x, float yDown)
{
    return SbVec2s(
        static_cast<short>(x * viewportSize),
        static_cast<short>((1.0F - yDown) * viewportSize)
    );
}

class SoViewCubeTest: public ::testing::Test
{
protected:
    static void SetUpTestSuite()
    {
        if (!SoDB::isInitialized()) {
            SoDB::init();
        }
        if (SoViewCube::getClassTypeId() == SoType::badType()) {
            SoViewCube::initClass();
        }
    }

    void SetUp() override
    {
        cube = new SoViewCube;
        cube->ref();
        cube->viewportRect.setValue(0.0F, 0.0F, viewportSize, viewportSize);
        cube->cameraIsOrthographic = TRUE;
    }

    void TearDown() override
    {
        cube->unref();
    }

    SoViewCube* cube {nullptr};
};
}  // namespace

TEST_F(SoViewCubeTest, theCentreOfTheFacingFaceIsThatFace)
{
    cube->cameraOrientation = SbRotation();
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.5F)), PickId::Top);
    cube->cameraOrientation = frontView();
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.5F)), PickId::Front);
}

TEST_F(SoViewCubeTest, theBandsOfTheFacingFaceAreItsEdgesAndCorners)
{
    // Face-on the face spans 0.262..0.738 of the overlay; its bands are the outer 0.105.
    cube->cameraOrientation = frontView();
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.31F)), PickId::FrontTop);
    EXPECT_EQ(cube->pickAt(at(0.69F, 0.5F)), PickId::FrontRight);
    EXPECT_EQ(cube->pickAt(at(0.69F, 0.31F)), PickId::FrontTopRight);
    EXPECT_EQ(cube->pickAt(at(0.31F, 0.69F)), PickId::FrontBottomLeft);
}

TEST_F(SoViewCubeTest, outsideTheCubeIsNothing)
{
    cube->cameraOrientation = frontView();
    EXPECT_EQ(cube->pickAt(at(0.2F, 0.5F)), PickId::None);
    EXPECT_EQ(cube->pickAt(SbVec2s(viewportSize + 10, 10)), PickId::None);
}

TEST_F(SoViewCubeTest, controlsAnswerOnlyWhileLive)
{
    cube->cameraOrientation = frontView();
    cube->controlsLive = FALSE;
    EXPECT_EQ(cube->pickAt(at(0.09F, 0.09F)), PickId::None);
    cube->controlsLive = TRUE;
    EXPECT_EQ(cube->pickAt(at(0.09F, 0.09F)), PickId::Home);
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.15F)), PickId::ArrowNorth);
}

TEST_F(SoViewCubeTest, trianglesAreNotThereWhenTheViewIsNotFaceOn)
{
    cube->cameraOrientation = isoView();
    cube->controlsLive = TRUE;
    EXPECT_NE(cube->pickAt(at(0.5F, 0.15F)), PickId::ArrowNorth);
}

TEST_F(SoViewCubeTest, theHighlightLightsTheTilesOfAnEdge)
{
    cube->cameraOrientation = frontView();
    cube->hiliteId = static_cast<int>(PickId::FrontTop);
    EXPECT_EQ(cube->hilitedTileCount(), 2);
    cube->hiliteId = static_cast<int>(PickId::FrontTopRight);
    EXPECT_EQ(cube->hilitedTileCount(), 3);
    cube->hiliteId = static_cast<int>(PickId::Home);
    EXPECT_EQ(cube->hilitedTileCount(), 0);
}

TEST_F(SoViewCubeTest, controlsShowOnlyOnceTheyHaveFadedIn)
{
    cube->cameraOrientation = isoView();
    cube->controlsOpacity = 0.0F;
    EXPECT_EQ(cube->visibleControlCount(), 0);
    cube->controlsOpacity = 0.4F;
    EXPECT_EQ(cube->visibleControlCount(), 4);
}

TEST_F(SoViewCubeTest, theTrianglesJoinTheControlsWhenFaceOn)
{
    cube->cameraOrientation = frontView();
    cube->controlsOpacity = 1.0F;
    EXPECT_EQ(cube->visibleControlCount(), 8);
}

TEST_F(SoViewCubeTest, pickIgnoresControlsThatAreNotLive)
{
    // Fading out: still drawn, no longer clickable; the click falls through to the cube or nothing.
    cube->cameraOrientation = frontView();
    cube->controlsOpacity = 0.6F;
    cube->controlsLive = FALSE;
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.15F)), PickId::None);
    EXPECT_EQ(cube->pickAt(at(0.92F, 0.92F)), PickId::None);
}

TEST_F(SoViewCubeTest, everyPointInsideTheCubePicksATile)
{
    // The guide lines and edges cross the faces; a click on one must still pick the tile
    // under it. An isometric cube's outline keeps 0.357 of the overlay around its centre
    // (0.4124 * cos 30) in orthographic, about 0.27 in perspective, where the far corners
    // draw closer in; face-on, the face reaches 0.238 either way.
    for (SbBool ortho : {TRUE, FALSE}) {
        cube->cameraIsOrthographic = ortho;
        for (const SbRotation& view : {isoView(), frontView()}) {
            cube->cameraOrientation = view;
            const float reach = view == frontView() ? 0.2F : (ortho ? 0.3F : 0.25F);
            for (int i = -10; i <= 10; ++i) {
                for (int j = -10; j <= 10; ++j) {
                    const float dx = reach * static_cast<float>(i) / 10.0F;
                    const float dy = reach * static_cast<float>(j) / 10.0F;
                    if (dx * dx + dy * dy > reach * reach) {
                        continue;
                    }
                    EXPECT_NE(cube->pickAt(at(0.5F + dx, 0.5F + dy)), PickId::None)
                        << "ortho " << ortho << " at " << 0.5F + dx << ", " << 0.5F + dy;
                }
            }
        }
    }
}

TEST_F(SoViewCubeTest, noPixelInsideTheCubeFallsThroughASeam)
{
    // Each tile is two triangles and no two tiles share vertices, so a ray can land exactly
    // on a seam. Whether it then hits either side depends on the floating-point rounding of
    // the Coin build (macOS arm64 missed where Linux and Windows hit), so the click must not.
    for (SbBool ortho : {TRUE, FALSE}) {
        cube->cameraIsOrthographic = ortho;
        for (const SbRotation& view : {isoView(), frontView()}) {
            cube->cameraOrientation = view;
            const float reach = view == frontView() ? 0.2F : (ortho ? 0.3F : 0.25F);
            const auto radius = static_cast<int>(reach * viewportSize);
            int misses = 0;
            for (int dx = -radius; dx <= radius; ++dx) {
                for (int dy = -radius; dy <= radius; ++dy) {
                    if (dx * dx + dy * dy > radius * radius) {
                        continue;
                    }
                    const SbVec2s pixel(
                        static_cast<short>(viewportSize / 2 + dx),
                        static_cast<short>(viewportSize / 2 + dy)
                    );
                    if (cube->pickAt(pixel) == PickId::None && misses++ < 5) {
                        ADD_FAILURE() << "ortho " << ortho << " front " << (view == frontView())
                                      << " pixel " << pixel[0] << ", " << pixel[1];
                    }
                }
            }
            EXPECT_EQ(misses, 0) << "ortho " << ortho << " front " << (view == frontView());
        }
    }
}

TEST_F(SoViewCubeTest, anIsometricViewPicksTheCornerItLooksAt)
{
    // Looking down from front-right-top, the corner shared by FRONT, TOP and RIGHT is
    // the cube's centre on screen.
    for (SbBool ortho : {TRUE, FALSE}) {
        cube->cameraIsOrthographic = ortho;
        cube->cameraOrientation = isoView();
        EXPECT_EQ(cube->pickAt(at(0.5F, 0.5F)), PickId::FrontTopRight) << "ortho " << ortho;
    }
}

namespace
{
// A camera looking at the cube from towardsViewer with the given up direction on screen.
SbRotation camera(const SbVec3f& towardsViewer, const SbVec3f& up)
{
    SbVec3f back = towardsViewer;
    back.normalize();
    SbVec3f upOnScreen = up - back * up.dot(back);
    upOnScreen.normalize();
    const SbVec3f right = upOnScreen.cross(back);
    const SbMatrix m(
        right[0],
        right[1],
        right[2],
        0.0F,
        upOnScreen[0],
        upOnScreen[1],
        upOnScreen[2],
        0.0F,
        back[0],
        back[1],
        back[2],
        0.0F,
        0.0F,
        0.0F,
        0.0F,
        1.0F
    );
    return SbRotation(m);
}
}  // namespace

TEST_F(SoViewCubeTest, aRolledFaceKeepsItsCornerTilesFromTheTriangles)
{
    // Rolled 45 degrees about the view axis, FRONT is a diamond whose top tip reaches up to
    // 0.163 of the overlay: under where the North triangle sits when the face is square on.
    cube->cameraOrientation = camera(SbVec3f(0, -1, 0), SbVec3f(1, 0, 1));
    cube->controlsLive = TRUE;
    cube->controlsOpacity = 1.0F;
    const PickId tip = cube->pickAt(at(0.5F, 0.18F));
    EXPECT_NE(tip, PickId::ArrowNorth);
    EXPECT_NE(tip, PickId::None);
    EXPECT_EQ(cube->visibleControlCount(), 4);
}

TEST_F(SoViewCubeTest, latchedTrianglesStayAfterAStepTurnsTheViewAway)
{
    // One 45-degree step up from FRONT: no longer face-on, but the triangles the user was
    // clicking stay put, so a second click steps again instead of snapping to a tile.
    cube->cameraOrientation = camera(SbVec3f(0, -1, 1), SbVec3f(0, 1, 1));
    cube->controlsLive = TRUE;
    cube->controlsOpacity = 1.0F;
    cube->trianglesLatched = FALSE;
    EXPECT_NE(cube->pickAt(at(0.5F, 0.15F)), PickId::ArrowNorth);
    EXPECT_EQ(cube->visibleControlCount(), 4);
    cube->trianglesLatched = TRUE;
    EXPECT_EQ(cube->pickAt(at(0.5F, 0.15F)), PickId::ArrowNorth);
    EXPECT_EQ(cube->visibleControlCount(), 8);
}
