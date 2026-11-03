// SPDX-License-Identifier: LGPL-2.1-or-later

#include <gtest/gtest.h>

#include <algorithm>
#include <functional>
#include <numeric>
#include <random>

#include "Mod/Sketcher/App/planegcs/GCS.h"

class SystemTest: public GCS::System
{
public:
    size_t getNumberOfConstraints(int tagID = -1)
    {
        return _getNumberOfConstraints(tagID);
    }
};

class GCSTest: public ::testing::Test
{
protected:
    void SetUp() override
    {
        _system = std::make_unique<SystemTest>();
    }

    void TearDown() override
    {
        _system.reset();
    }

    SystemTest* System()
    {
        return _system.get();
    }

private:
    std::unique_ptr<SystemTest> _system;
};

TEST_F(GCSTest, clearConstraints)  // NOLINT
{
    // Arrange
    const size_t numConstraints {100};
    for (size_t i = 0; i < numConstraints; ++i) {
        System()->addConstraint(new GCS::Constraint());
    }
    ASSERT_EQ(numConstraints, System()->getNumberOfConstraints());

    // Act
    System()->clear();

    // Assert
    EXPECT_EQ(0, System()->getNumberOfConstraints());
}

namespace
{

// Rectangles in the style of a sketch: four points, four lines, horizontal/vertical, width,
// height and a fixed corner, so each rectangle is fully constrained on its own. Constraints and
// parameters are added in a shuffled order, the way a sketch edited over time hands them over.
class RectangleSystem
{
public:
    RectangleSystem(int count, unsigned seed, int redundant, int conflicting, int freeCorners = 0)
        : params(count * 8)
        , values(count * 4)
        , points(count * 4)
        , lines(count * 4)
    {
        std::mt19937 rng(seed);
        std::vector<std::function<void(int)>> adders;
        for (int r = 0; r < count; ++r) {
            const double x = 15.0 * (r % 12), y = 15.0 * (r / 12), w = 10.0, h = 6.0;
            const double corners[4][2] = {{x, y}, {x + w, y}, {x + w, y + h}, {x, y + h}};
            for (int i = 0; i < 4; ++i) {
                params[r * 8 + i * 2] = corners[i][0];
                params[r * 8 + i * 2 + 1] = corners[i][1];
                points[r * 4 + i] = GCS::Point(&params[r * 8 + i * 2], &params[r * 8 + i * 2 + 1]);
            }
            for (int i = 0; i < 4; ++i) {
                lines[r * 4 + i].p1 = points[r * 4 + i];
                lines[r * 4 + i].p2 = points[r * 4 + (i + 1) % 4];
            }
            values[r * 4] = w;
            values[r * 4 + 1] = h;
            values[r * 4 + 2] = x;
            values[r * 4 + 3] = y;
            GCS::Point* p = &points[r * 4];
            GCS::Line* l = &lines[r * 4];
            double* v = &values[r * 4];
            adders.emplace_back([this, l](int tag) { sys.addConstraintHorizontal(l[0], tag); });
            adders.emplace_back([this, l](int tag) { sys.addConstraintHorizontal(l[2], tag); });
            adders.emplace_back([this, l](int tag) { sys.addConstraintVertical(l[1], tag); });
            adders.emplace_back([this, l](int tag) { sys.addConstraintVertical(l[3], tag); });
            adders.emplace_back([this, p, v](int tag) {
                sys.addConstraintDifference(p[0].x, p[1].x, &v[0], tag);
            });
            adders.emplace_back([this, p, v](int tag) {
                sys.addConstraintDifference(p[1].y, p[2].y, &v[1], tag);
            });
            if (r < freeCorners) {
                continue;  // this rectangle can slide: two degrees of freedom
            }
            adders.emplace_back([this, p, v](int tag) {
                sys.addConstraintCoordinateX(p[0], &v[2], tag);
            });
            adders.emplace_back([this, p, v](int tag) {
                sys.addConstraintCoordinateY(p[0], &v[3], tag);
            });
        }
        // a redundant constraint repeats a satisfied one, a conflicting one asks for another width
        conflictWidths.resize(conflicting, 99.0);
        for (int k = 0; k < redundant; ++k) {
            GCS::Line* l = &lines[(k * 7 % count) * 4];
            adders.emplace_back([this, l](int tag) { sys.addConstraintHorizontal(l[0], tag); });
        }
        for (int k = 0; k < conflicting; ++k) {
            GCS::Point* p = &points[(k * 5 % count) * 4 + 0];
            double* width = &conflictWidths[k];
            adders.emplace_back([this, p, width](int tag) {
                sys.addConstraintDifference(p[0].x, p[1].x, width, tag);
            });
        }
        std::shuffle(adders.begin(), adders.end(), rng);
        for (std::size_t i = 0; i < adders.size(); ++i) {
            adders[i](static_cast<int>(i) + 1);
        }
        for (auto& param : params) {
            unknowns.push_back(&param);
        }
        std::shuffle(unknowns.begin(), unknowns.end(), rng);
    }

    void diagnose(GCS::QRAlgorithm algorithm)
    {
        sys.autoChooseAlgorithm = false;
        sys.qrAlgorithm = algorithm;
        sys.declareUnknowns(unknowns);
        sys.initSolution();
    }

    std::vector<int> sorted(void (GCS::System::*get)(GCS::VEC_I&) const) const
    {
        GCS::VEC_I tags;
        (sys.*get)(tags);
        std::sort(tags.begin(), tags.end());
        return tags;
    }

    std::vector<std::size_t> dependentParams() const
    {
        GCS::VEC_pD dependent;
        sys.getDependentParams(dependent);
        std::vector<std::size_t> indices;
        for (double* param : dependent) {
            indices.push_back(static_cast<std::size_t>(param - params.data()));
        }
        std::sort(indices.begin(), indices.end());
        return indices;
    }

    GCS::System sys;
    std::vector<double> params;
    std::vector<double> values;
    std::vector<double> conflictWidths;
    std::vector<GCS::Point> points;
    std::vector<GCS::Line> lines;
    GCS::VEC_pD unknowns;
};

void expectSameDiagnosis(int count, unsigned seed, int redundant, int conflicting, int freeCorners = 0)
{
    RectangleSystem dense(count, seed, redundant, conflicting, freeCorners);
    RectangleSystem sparse(count, seed, redundant, conflicting, freeCorners);
    dense.diagnose(GCS::EigenDenseQR);
    sparse.diagnose(GCS::EigenSparseQR);

    // the dense result is the reference; make sure it found what was planted
    EXPECT_EQ(dense.sys.hasRedundant(), redundant > 0);
    EXPECT_EQ(dense.sys.hasConflicting(), conflicting > 0);
    if (redundant == 0 && conflicting == 0) {
        EXPECT_EQ(dense.sys.dofsNumber(), 2 * freeCorners);
    }
    EXPECT_EQ(dense.sys.dofsNumber(), sparse.sys.dofsNumber());
    EXPECT_EQ(dense.sorted(&GCS::System::getConflicting), sparse.sorted(&GCS::System::getConflicting));
    EXPECT_EQ(dense.sorted(&GCS::System::getRedundant), sparse.sorted(&GCS::System::getRedundant));
    EXPECT_EQ(
        dense.sorted(&GCS::System::getPartiallyRedundant),
        sparse.sorted(&GCS::System::getPartiallyRedundant)
    );
    EXPECT_EQ(dense.dependentParams(), sparse.dependentParams());
}

}  // namespace

TEST_F(GCSTest, sparseDiagnosisMatchesDenseWhenFullyConstrained)  // NOLINT
{
    for (unsigned seed : {1U, 2U, 3U}) {
        expectSameDiagnosis(20, seed, 0, 0);
    }
}

TEST_F(GCSTest, sparseDiagnosisMatchesDenseWithRedundantConstraints)  // NOLINT
{
    for (unsigned seed : {1U, 2U, 3U}) {
        expectSameDiagnosis(20, seed, 4, 0);
    }
}

TEST_F(GCSTest, sparseDiagnosisMatchesDenseWithConflictingConstraints)  // NOLINT
{
    for (unsigned seed : {1U, 2U, 3U}) {
        expectSameDiagnosis(20, seed, 0, 3);
    }
}

TEST_F(GCSTest, sparseDiagnosisMatchesDenseWithFreeGeometry)  // NOLINT
{
    for (unsigned seed : {1U, 2U, 3U}) {
        expectSameDiagnosis(20, seed, 0, 0, 5);
        expectSameDiagnosis(20, seed, 3, 2, 5);
    }
}

TEST_F(GCSTest, reorderedSparseQRKeepsRSparseForShuffledSketchJacobian)  // NOLINT
{
    // Arrange: 144 independent 16x16 blocks, the Jacobian of a 576-line sketch of rectangles,
    // with rows and columns shuffled. Stock SparseQR with COLAMD fills R to over a million entries.
    const int blocks = 144, size = 16, n = blocks * size;
    std::mt19937 rng(42);
    std::uniform_real_distribution<double> value(0.5, 2.0);
    std::vector<int> rowOf(n), colOf(n);
    std::iota(rowOf.begin(), rowOf.end(), 0);
    std::iota(colOf.begin(), colOf.end(), 0);
    std::shuffle(rowOf.begin(), rowOf.end(), rng);
    std::shuffle(colOf.begin(), colOf.end(), rng);
    std::vector<Eigen::Triplet<double>> triplets;
    for (int b = 0; b < blocks; ++b) {
        for (int i = 0; i < size; ++i) {
            // a banded block: each constraint touches two or three parameters, like the sketch
            for (int j = std::max(0, i - 1); j <= std::min(size - 1, i + 1); ++j) {
                triplets.emplace_back(rowOf[b * size + i], colOf[b * size + j], value(rng));
            }
        }
    }
    GCS::ReorderedSparseQR::SparseMatrix A(n, n);
    A.setFromTriplets(triplets.begin(), triplets.end());
    A.makeCompressed();

    // Act
    GCS::ReorderedSparseQR qr;
    qr.compute(A);

    // Assert: full rank, R stays within a small multiple of A, and the permutation is complete
    EXPECT_EQ(qr.rank(), n);
    EXPECT_LT(qr.matrixR().nonZeros(), 4 * A.nonZeros());
    std::vector<int> seen(n, 0);
    for (int k = 0; k < n; ++k) {
        ++seen[qr.colsPermutation().indices()[k]];
    }
    EXPECT_EQ(std::count(seen.begin(), seen.end(), 1), n);
}
