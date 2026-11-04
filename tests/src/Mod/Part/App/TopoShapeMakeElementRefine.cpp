// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <BRepGProp.hxx>
#include <GProp_GProps.hxx>

#include <src/App/InitApplication.h>

#include "PartTestHelpers.h"

class FeaturePartMakeElementRefineTest: public ::testing::Test,
                                        public PartTestHelpers::PartTestHelperClass
{
protected:
    static void SetUpTestSuite()
    {
        tests::initApplication();
    }


    void SetUp() override
    {
        createTestDoc();
    }

    void TearDown() override
    {}
};

TEST_F(FeaturePartMakeElementRefineTest, makeElementRefineBoxes)
{
    // Arrange
    auto _doc = App::GetApplication().getActiveDocument();
    auto _fuse = _doc->addObject<Part::Fuse>();
    _fuse->Base.setValue(_boxes[0]);
    _fuse->Tool.setValue(_boxes[3]);
    _fuse->Refine.setValue(false);
    // Act
    _fuse->execute();
    Part::TopoShape ts = _fuse->Shape.getShape();
    Part::TopoShape refined = ts.makeElementRefine();
    double volume = PartTestHelpers::getVolume(ts.getShape());
    double refinedVolume = PartTestHelpers::getVolume(refined.getShape());
    Base::BoundBox3d bb = ts.getBoundBox();
    // Assert
    EXPECT_TRUE(bb.IsValid());
    EXPECT_DOUBLE_EQ(volume, 12.0);
    EXPECT_DOUBLE_EQ(refinedVolume, 12.0);            // Refine shouldn't change the volume
    EXPECT_EQ(ts.countSubElements("Face"), 10);       // Two boxes touching each loose one face
    EXPECT_EQ(ts.countSubElements("Edge"), 20);       // Two boxes touching loose 4 edges
    EXPECT_EQ(refined.countSubElements("Face"), 6);   // After refining it is one box
    EXPECT_EQ(refined.countSubElements("Edge"), 12);  // 12 edges in a box
    // Make sure that the number of elements in the elementMaps is correct.
    EXPECT_EQ(ts.getElementMapSize(), 42);
    EXPECT_EQ(refined.getElementMapSize(), 26);
    // TODO: Refine doesn't work on compounds, so we're going to need a binary operation or the
    // like, and those don't exist yet.  Once they do, this test can be expanded
}

namespace
{
// Negative for a solid that is inside out, unlike PartTestHelpers::getVolume
double signedVolume(const TopoDS_Shape& shape)
{
    GProp_GProps prop;
    BRepGProp::VolumeProperties(shape, prop);
    return prop.Mass();
}
}  // namespace

TEST_F(FeaturePartMakeElementRefineTest, makeElementRefineWithNothingToMerge)
{
    // Arrange: a box has no coplanar neighbours to merge, so refine leaves every shell as it
    // was and skips checking the orientation of the solid
    Part::TopoShape box = _boxes[0]->Shape.getShape();
    double volume = PartTestHelpers::getVolume(box.getShape());
    // Act
    Part::TopoShape refined = Part::TopoShape(0, nullptr).makeElementRefine(box);
    // Assert: still the same closed solid, the right way out
    EXPECT_FALSE(refined.isNull());
    EXPECT_TRUE(refined.isClosed());
    EXPECT_EQ(refined.shapeType(), TopAbs_SOLID);
    EXPECT_DOUBLE_EQ(PartTestHelpers::getVolume(refined.getShape()), volume);
    EXPECT_GT(signedVolume(refined.getShape()), 0.0);
    EXPECT_EQ(refined.countSubElements("Face"), 6);
    EXPECT_EQ(refined.countSubElements("Edge"), 12);
}

TEST_F(FeaturePartMakeElementRefineTest, makeElementRefineThatMergesFacesKeepsTheSolidTheRightWayOut)
{
    // Arrange: two touching boxes fused without refine, then refined; merging rebuilds the
    // shell, so the orientation is checked and the solid must come out the right way
    auto _doc = App::GetApplication().getActiveDocument();
    auto _fuse = _doc->addObject<Part::Fuse>();
    _fuse->Base.setValue(_boxes[0]);
    _fuse->Tool.setValue(_boxes[3]);
    _fuse->Refine.setValue(false);
    _fuse->execute();
    Part::TopoShape fused = _fuse->Shape.getShape();
    // Act
    Part::TopoShape refined = Part::TopoShape(0, nullptr).makeElementRefine(fused);
    // Assert
    EXPECT_TRUE(refined.isClosed());
    EXPECT_GT(signedVolume(refined.getShape()), 0.0);
    EXPECT_DOUBLE_EQ(PartTestHelpers::getVolume(refined.getShape()), 12.0);
    EXPECT_EQ(refined.countSubElements("Face"), 6);
}
