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

#pragma once

#include <functional>
#include <memory>
#include <optional>

#include <QObject>
#include <QPointer>
#include <QString>

#include <Inventor/SbVec3f.h>

#include <Base/Placement.h>
#include <Base/Unit.h>

#include <FCGlobal.h>

class QAction;

namespace Gui
{
class EditableDatumLabel;
class View3DInventorViewer;

/// A gizmo's value shown in the 3D view: a dimension with an editable box on it.
///
/// Geometry is given in the gizmos' own frame (the editing transform they are attached
/// under) and converted to the global frame the label is drawn in.
class GuiExport GizmoValueLabel: public QObject
{
    Q_OBJECT

public:
    /// A value on a dimension, or a number of copies in a box of its own
    enum class Kind
    {
        Value,
        Count
    };
    /// The object name every count box carries
    static constexpr const char* countBoxName = "GizmoCountBox";

    /// The Coin node name every gizmo value label carries
    static constexpr const char* nodeName = "GizmoValueLabel";
    /// The object name every gizmo value box carries
    static constexpr const char* boxName = "GizmoValueBox";

    GizmoValueLabel(
        View3DInventorViewer* viewer,
        const Base::Placement& editPlacement,
        const Base::Unit& unit,
        Kind kind = Kind::Value
    );
    ~GizmoValueLabel() override;

    /// A distance of travel from base along dir (a negative travel points back along dir)
    void showDistance(const SbVec3f& base, const SbVec3f& dir, float travel);
    /// An arc of sweep radians about axis through centre, at radius, starting at zeroRay
    void showAngle(
        const SbVec3f& centre,
        const SbVec3f& axis,
        const SbVec3f& zeroRay,
        float sweep,
        float radius
    );
    /// Just the box, at point, with no dimension line
    void showBoxAt(const SbVec3f& point, const SbVec3f& dir);

    /// Puts value in the box, unless the box already holds it, so typed text is left alone
    void setValue(double value);
    /// Shows a formula in the box in place of its value, which goes in the tooltip; typing
    /// over it replaces it, as in Fusion
    void showExpression(const QString& expression, double value);
    /// The formula the box shows, or an empty string when it shows a value
    QString shownExpression() const;

    /// Takes typed text that the box cannot pass on as a number as it is typed: a formula,
    /// or a number typed over a formula (given as number). Returns why the text cannot be
    /// used, or an empty string once it has been.
    using TextCommitter = std::function<QString(const QString& text, std::optional<double> number)>;
    /// Without one, as for a count, the box takes numbers only
    void setTextCommitter(TextCommitter committer);
    /// The values the box takes; one typed outside them is turned away
    void setRange(double minimum, double maximum);
    void setShown(bool shown);
    bool isShown() const;
    void focus();
    bool hasFocus() const;

Q_SIGNALS:
    void valueEdited(double value);
    void accepted();
    void cancelled();
    void tabbed(bool backwards);
    void focusLeft();

protected:
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    Base::Vector3d toGlobalPoint(const SbVec3f& point) const;
    Base::Vector3d toGlobalDirection(const SbVec3f& direction) const;
    Base::Vector3d towardsViewer() const;
    /// Hands typed text to the committer when it needs one; false when it was refused
    bool commitTypedText(bool reportError);
    /// Whether the user has typed in the box since its text was last set
    bool isBeingTyped() const;
    /// Writes the formula into the box, which is left holding its value underneath
    void putExpressionText();
    void showError(const QString& message);
    /// Redraws the "x" mark for the box's current palette, font and device pixel ratio
    void updateTimesMark();

    QPointer<View3DInventorViewer> viewer;
    Base::Placement editPlacement;
    Base::Unit unit;
    Kind kind;
    std::unique_ptr<EditableDatumLabel> label;
    bool shown = false;
    TextCommitter committer;
    QString expression;
    /// Set while the committer runs, so the box shows what was just committed
    bool committing = false;
    /// The count box's leading "x" mark action, so it can be redrawn in place rather than
    /// added again; null for a Kind::Value box, which has none
    QPointer<QAction> timesMarkAction;
};

}  // namespace Gui
