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

#include "GizmoValueLabel.h"

#include <cmath>

#include <QAction>
#include <QEvent>
#include <QKeyEvent>
#include <QLineEdit>
#include <QPainter>
#include <QPixmap>
#include <QSignalBlocker>
#include <QString>
#include <QToolTip>

#include <Inventor/nodes/SoCamera.h>

#include <Base/Precision.h>
#include <Base/Quantity.h>
#include <Base/Rotation.h>
#include "Base/ServiceProvider.h"
#include <Gui/EditableDatumLabel.h>
#include <Gui/Inventor/Draggers/GizmoStyleParameters.h>
#include <Gui/QuantitySpinBox.h>
#include <Gui/SoDatumLabel.h>
#include <Gui/Utilities.h>
#include <Gui/View3DInventorViewer.h>

using namespace Gui;

namespace
{
/// The "×" drawn at the front of a count box
QIcon timesMark(const QWidget* box)
{
    const int side = box->fontMetrics().height();
    const qreal ratio = box->devicePixelRatioF();
    QPixmap pixmap(QSize(side, side) * ratio);
    pixmap.setDevicePixelRatio(ratio);
    pixmap.fill(Qt::transparent);
    QPainter painter(&pixmap);
    painter.setPen(box->palette().color(QPalette::Text));
    painter.setFont(box->font());
    painter.drawText(QRect(0, 0, side, side), Qt::AlignCenter, QStringLiteral("×"));
    return QIcon(pixmap);
}
}  // namespace

GizmoValueLabel::GizmoValueLabel(
    View3DInventorViewer* viewer,
    const Base::Placement& editPlacement,
    const Base::Unit& unit,
    Kind kind
)
    : viewer(viewer)
    , editPlacement(editPlacement)
    , unit(unit)
    , kind(kind)
    , label(std::make_unique<EditableDatumLabel>(viewer, editPlacement))
{
    label->label->setName(nodeName);

    auto* styleParameterManager = Base::provideService<StyleParameters::ParameterManager>();
    Base::Color color = styleParameterManager->resolve(StyleParameters::DimensionVisualizerColor);
    label->setColor(color.asValue<SbColor>());

    label->setLabelType(SoDatumLabel::DISTANCE, EditableDatumLabel::Function::Dimensioning);
    label->activate();
    // The box stays open for as long as the gizmo lives, and the gizmo container decides
    // which box has the keyboard, so it never takes focus by itself.
    label->startEdit(0.0, this, true, false);
    if (QuantitySpinBox* box = label->getSpinBox()) {
        if (kind == Kind::Count) {
            box->setObjectName(QString::fromLatin1(countBoxName));
            box->setDecimals(0);
            box->setToolTip(tr("Number of copies, the original included"));
            // Reserve room for the leading "x" mark, the same way EditableDatumLabel's own
            // lock icon does: sizeHintForDigits only widens the box for an icon when told to,
            // and the mark would otherwise crop the digits instead of sitting beside them
            box->addIconSpace(true);
            if (auto* edit = box->findChild<QLineEdit*>()) {
                timesMarkAction = edit->addAction(timesMark(box), QLineEdit::LeadingPosition);
            }
            label->updateGeometry();
        }
        else {
            box->setObjectName(QString::fromLatin1(boxName));
        }
    }
    label->setSpinboxValue(0.0, unit);

    connect(label.get(), &EditableDatumLabel::valueChanged, this, &GizmoValueLabel::valueEdited);

    label->setVisible(false);
}

GizmoValueLabel::~GizmoValueLabel()
{
    // The box is only deleted later, when control is back in the event loop; hide it now so
    // a rebuild never shows the old boxes next to the new ones
    if (QuantitySpinBox* box = label->getSpinBox()) {
        box->hide();
    }
}

void GizmoValueLabel::showDistance(const SbVec3f& base, const SbVec3f& dir, float travel)
{
    Base::Vector3d along = toGlobalDirection(dir);
    if (along.Length() < Base::Precision::Confusion()) {
        return;
    }
    along.Normalize();

    // Lay the dimension in the plane through the drag axis that faces the viewer most
    auto across = [&along](Base::Vector3d vec) {
        return vec - along * (vec * along);
    };
    Base::Vector3d facing = across(towardsViewer());
    if (facing.Length() < Base::Precision::Confusion()) {
        // Looking straight down the axis: any plane through it will do
        facing = across(Base::Vector3d(0, 0, 1));
        if (facing.Length() < Base::Precision::Confusion()) {
            facing = across(Base::Vector3d(1, 0, 0));
        }
    }
    facing.Normalize();

    label->setLabelType(SoDatumLabel::DISTANCE, EditableDatumLabel::Function::Dimensioning);
    label->setPlacement(Base::Placement(
        toGlobalPoint(base),
        Base::Rotation::makeRotationByAxes(along, Base::Vector3d(), facing)
    ));
    // On the drag axis itself, so the box sits on the line halfway along it
    label->setLabelDistance(0.0);

    if (std::abs(travel) < Base::Precision::Confusion()) {
        // Nothing to draw yet: the box waits where the gizmo starts. A degenerate pair
        // (rather than no points at all, which SoDatumLabel::GLRender warns about on every
        // redraw for a DISTANCE-type label - "Too few points to render distance label") still
        // reads as zero-length, drawing no line, and keeps the box at this same point: showAngle
        // below has set an identical pair unconditionally for as long as this class has existed.
        label->setPoints(SbVec3f(0, 0, 0), SbVec3f(0, 0, 0));
        return;
    }
    label->setPoints(SbVec3f(0, 0, 0), SbVec3f(travel, 0, 0));
}

void GizmoValueLabel::showAngle(
    const SbVec3f& centre,
    const SbVec3f& axis,
    const SbVec3f& zeroRay,
    float sweep,
    float radius
)
{
    Base::Vector3d normal = toGlobalDirection(axis);
    Base::Vector3d start = toGlobalDirection(zeroRay);
    if (normal.Length() < Base::Precision::Confusion()
        || start.Length() < Base::Precision::Confusion()) {
        return;
    }

    label->setLabelType(SoDatumLabel::ANGLE, EditableDatumLabel::Function::Dimensioning);
    label->setPlacement(Base::Placement(
        toGlobalPoint(centre),
        Base::Rotation::makeRotationByAxes(start, Base::Vector3d(), normal)
    ));
    // SoDatumLabel draws an angle's arc at twice its distance parameter
    label->setLabelDistance(radius / 2.0F);
    label->setLabelStartAngle(0.0);
    label->setLabelRange(sweep);
    label->setPoints(SbVec3f(0, 0, 0), SbVec3f(0, 0, 0));
}

void GizmoValueLabel::showBoxAt(const SbVec3f& point, const SbVec3f& dir)
{
    // A distance of nothing draws no line and leaves the box where it starts
    showDistance(point, dir, 0.0F);
}

void GizmoValueLabel::setValue(double value)
{
    QuantitySpinBox* box = label->getSpinBox();
    const bool wasExpression = !expression.isEmpty();
    expression.clear();
    if (wasExpression && box) {
        box->setToolTip(QString());
    }
    if (wasExpression && isBeingTyped()) {
        // The formula went because a number is being typed over it: leave the number be
        return;
    }
    // A box that was showing a formula always needs its value back
    if (!wasExpression && box && box->hasValidInput()
        && std::abs(box->rawValue() - value) < Base::Precision::Confusion()) {
        return;
    }
    label->setSpinboxValue(value, unit);
    // setSpinboxValue replaces the box's whole Base::Quantity, format and all, so a count
    // box's whole-number precision has to be put back every time the value changes
    if (kind == Kind::Count && box) {
        box->setDecimals(0);
    }
}

void GizmoValueLabel::showExpression(const QString& text, double value)
{
    QuantitySpinBox* box = label->getSpinBox();
    auto* edit = box ? box->findChild<QLineEdit*>() : nullptr;
    if (!edit) {
        return;
    }
    expression = text;
    const QString valueText = QString::fromStdString(Base::Quantity(value, unit).getUserString());
    box->setToolTip(tr("%1 = %2").arg(text, valueText));
    if (isBeingTyped()) {
        // Never rewrite what is being typed
        return;
    }
    // The value goes in first, so the box falls back to it rather than to an older one when
    // it is left with the formula still in it, which it cannot read
    label->setSpinboxValue(value, unit);
    putExpressionText();
}

void GizmoValueLabel::putExpressionText()
{
    QuantitySpinBox* box = label->getSpinBox();
    auto* edit = box ? box->findChild<QLineEdit*>() : nullptr;
    if (!edit) {
        return;
    }
    {
        QSignalBlocker block(edit);
        edit->setText(expression);
    }
    label->updateGeometry();
    if (box->hasFocus()) {
        edit->selectAll();
    }
}

bool GizmoValueLabel::isBeingTyped() const
{
    QuantitySpinBox* box = label->getSpinBox();
    auto* edit = box ? box->findChild<QLineEdit*>() : nullptr;
    // Focus alone is not enough: the box falls back to a plain number whenever it loses
    // the keyboard, and the formula has to come back even if it has the keyboard again.
    // The line edit counts as modified only after a keystroke, until its text is next set.
    return edit && box->hasFocus() && edit->isModified() && !committing;
}

QString GizmoValueLabel::shownExpression() const
{
    return expression;
}

void GizmoValueLabel::setTextCommitter(TextCommitter committer)
{
    this->committer = std::move(committer);
}

bool GizmoValueLabel::commitTypedText(bool reportError)
{
    QuantitySpinBox* box = label->getSpinBox();
    auto* edit = box ? box->findChild<QLineEdit*>() : nullptr;
    if (!committer || !edit) {
        return true;
    }
    const QString text = edit->text().trimmed();
    if (!expression.isEmpty() && text == expression) {
        return true;
    }
    const bool number = box->hasValidInput() && !text.startsWith(QLatin1Char('='));
    if (number && expression.isEmpty()) {
        // Passed on as it was typed
        return true;
    }

    committing = true;
    QString error = committer(text, number ? std::optional<double>(box->rawValue()) : std::nullopt);
    committing = false;
    if (!error.isEmpty()) {
        if (reportError) {
            showError(error);
        }
        return false;
    }
    return true;
}

void GizmoValueLabel::showError(const QString& message)
{
    QuantitySpinBox* box = label->getSpinBox();
    if (!box) {
        return;
    }
    box->setToolTip(message);
    QToolTip::showText(box->mapToGlobal(QPoint(0, box->height())), message, box);
}

void GizmoValueLabel::setRange(double minimum, double maximum)
{
    if (QuantitySpinBox* box = label->getSpinBox()) {
        box->setRange(minimum, maximum);
    }
}

void GizmoValueLabel::setShown(bool shown)
{
    if (this->shown == shown) {
        return;
    }
    this->shown = shown;
    label->setVisible(shown);
    if (shown && !expression.isEmpty()) {
        // QuantitySpinBox writes its value over the text whenever it is shown
        putExpressionText();
    }
}

bool GizmoValueLabel::isShown() const
{
    return shown;
}

void GizmoValueLabel::focus()
{
    if (shown) {
        label->setFocusToSpinbox();
    }
}

bool GizmoValueLabel::hasFocus() const
{
    QuantitySpinBox* box = label->getSpinBox();
    return box && box->hasFocus();
}

bool GizmoValueLabel::eventFilter(QObject* watched, QEvent* event)
{
    if (watched != label->getSpinBox()) {
        return QObject::eventFilter(watched, event);
    }

    if (event->type() == QEvent::FocusOut) {
        // Clicking away takes a formula as Enter does; one that cannot be used is dropped
        commitTypedText(false);
        Q_EMIT focusLeft();
    }
    else if (
        event->type() == QEvent::PaletteChange || event->type() == QEvent::StyleChange
        || event->type() == QEvent::ScreenChangeInternal
        || event->type() == QEvent::DevicePixelRatioChange
    ) {
        // The pixmap was drawn once, from the box's palette and device pixel ratio at
        // construction; a theme switch or a move to a screen with a different scale
        // leaves it stale otherwise (a fixed dark-on-light glyph on a dark theme, or a
        // blurry one after a DPI change) until redrawn here.
        updateTimesMark();
    }
    else if (event->type() == QEvent::KeyPress) {
        // Seen before EditableDatumLabel's own handling, which is the sketcher's
        switch (static_cast<QKeyEvent*>(event)->key()) {
            case Qt::Key_Return:
            case Qt::Key_Enter:
                if (commitTypedText(true)) {
                    Q_EMIT accepted();
                }
                return true;
            case Qt::Key_Escape:
                Q_EMIT cancelled();
                return true;
            case Qt::Key_Tab:
                if (commitTypedText(true)) {
                    Q_EMIT tabbed(false);
                }
                return true;
            case Qt::Key_Backtab:
                if (commitTypedText(true)) {
                    Q_EMIT tabbed(true);
                }
                return true;
            default:
                break;
        }
    }

    return QObject::eventFilter(watched, event);
}

Base::Vector3d GizmoValueLabel::toGlobalPoint(const SbVec3f& point) const
{
    Base::Vector3d global;
    editPlacement.multVec(Base::Vector3d(point[0], point[1], point[2]), global);
    return global;
}

Base::Vector3d GizmoValueLabel::toGlobalDirection(const SbVec3f& direction) const
{
    return editPlacement.getRotation().multVec(
        Base::Vector3d(direction[0], direction[1], direction[2])
    );
}

Base::Vector3d GizmoValueLabel::towardsViewer() const
{
    SbVec3f towards(0.0F, 0.0F, 1.0F);
    if (viewer && viewer->getCamera()) {
        viewer->getCamera()->orientation.getValue().multVec(towards, towards);
    }
    return Base::Vector3d(towards[0], towards[1], towards[2]);
}

void GizmoValueLabel::updateTimesMark()
{
    if (!timesMarkAction) {
        return;
    }
    QuantitySpinBox* box = label->getSpinBox();
    if (!box) {
        return;
    }
    timesMarkAction->setIcon(timesMark(box));
}

#include "moc_GizmoValueLabel.cpp"  // NOLINT
