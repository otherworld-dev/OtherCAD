// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2025 Sayantan Deb <sayantandebin[at]gmail.com>           *
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

#include "Gizmo.h"

#include <cmath>
#include <iterator>
#include <utility>
#include <numbers>
#include <QAbstractSpinBox>
#include <QApplication>
#include <QCoreApplication>
#include <QLineEdit>
#include <QTimer>

#include <Inventor/nodes/SoOrthographicCamera.h>
#include <Inventor/nodes/SoPerspectiveCamera.h>
#include <Inventor/nodes/SoPickStyle.h>
#include <algorithm>

#include <App/Application.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <Base/Converter.h>
#include <Base/Parameter.h>
#include <Base/Precision.h>
#include "Base/ServiceProvider.h"
#include <Base/Tools.h>
#include <Document.h>
#include <Gui/Control.h>
#include <Gui/Inventor/Draggers/GizmoStyleParameters.h>
#include <Gui/Inventor/So3DAnnotation.h>
#include <Gui/ModelParameters.h>
#include <Gui/Inventor/SoToggleSwitch.h>
#include <Gui/ViewProviderDragger.h>
#include <Gui/QuantitySpinBox.h>
#include <Gui/Utilities.h>
#include <Gui/View3DInventorViewer.h>

#include "GizmoValueLabel.h"
#include "SoLinearDragger.h"
#include "SoLinearDraggerGeometry.h"
#include "SoRotationDragger.h"
#include "SoRotationDraggerGeometry.h"

using namespace Gui;

namespace
{
enum class DefaultDragBehavior
{
    Coarse = 0,
    Fine = 1,
};

Base::Reference<ParameterGrp> getGizmoParameterGroup()
{
    static Base::Reference<ParameterGrp> hGrp = App::GetApplication().GetUserParameter().GetGroup(
        "BaseApp/Preferences/Gui/Gizmos"
    );

    return hGrp;
}

int getCoarseLinearSnapMultiplier()
{
    int multiplier = static_cast<int>(
        getGizmoParameterGroup()->GetInt("CoarseLinearSnapMultiplier", 5)
    );
    return std::max(1, multiplier);
}

int getCoarseRotationSnapMultiplier()
{
    int multiplier = static_cast<int>(
        getGizmoParameterGroup()->GetInt("CoarseRotationSnapMultiplier", 5)
    );
    return std::max(1, multiplier);
}

double snapToStep(double value, double step)
{
    if (step <= 0.0) {
        return value;
    }

    return std::round(value / step) * step;
}

double getRotationPeriod(double multFactor)
{
    const double factor = std::abs(multFactor);
    if (factor <= Base::Precision::Confusion()) {
        return 360.0;
    }

    return 2.0 * std::numbers::pi / factor;
}

double getClosestEquivalentAngle(double angle, double reference, double period)
{
    if (period <= Base::Precision::Confusion()) {
        return angle;
    }

    return angle + std::round((reference - angle) / period) * period;
}

double clampDragAngle(double value, double min, double max, double period)
{
    if (max - min >= period - Base::Precision::Confusion()) {
        return std::clamp(value, min, max);
    }

    return Base::clampAngle(value, min, max, Base::Precision::Confusion());
}

void acceptActiveDialog()
{
    // Queued: accepting closes the task panel, which owns the box whose key press is
    // still being handled
    QMetaObject::invokeMethod(qApp, []() { Gui::Control().accept(); }, Qt::QueuedConnection);
}

void rejectActiveDialog()
{
    QMetaObject::invokeMethod(qApp, []() { Gui::Control().reject(); }, Qt::QueuedConnection);
}
}  // namespace

void Gizmo::setDraggerPlacement(const Base::Vector3d& pos, const Base::Vector3d& dir)
{
    setDraggerPlacement(Base::convertTo<SbVec3f>(pos), Base::convertTo<SbVec3f>(dir));
}

bool Gizmo::isDelayedUpdateEnabled()
{
    return getGizmoParameterGroup()->GetBool("DelayedGizmoUpdate", false);
}

double Gizmo::getMultFactor()
{
    return multFactor;
}

double Gizmo::getAddFactor()
{
    return addFactor;
}

bool Gizmo::getVisibility()
{
    return visible;
}

QuantitySpinBox* Gizmo::getProperty() const
{
    return property;
}

GizmoValueLabel* Gizmo::getValueLabel() const
{
    return valueLabel;
}

void Gizmo::setValueLabel(GizmoValueLabel* label)
{
    QObject::disconnect(valueLabelConnection);
    QObject::disconnect(expressionConnection);
    QObject::disconnect(labelFocusConnection);
    valueLabel = label;
    if (label) {
        // Typing in the box is typing in the task panel field
        valueLabelConnection
            = QObject::connect(label, &GizmoValueLabel::valueEdited, label, [this](double value) {
                  if (property->boundExpression()) {
                      // The box falling back to the formula's own value changes nothing;
                      // another number typed over the formula replaces it
                      if (std::abs(value - property->rawValue()) < Base::Precision::Confusion()) {
                          return;
                      }
                      releaseExpression();
                  }
                  property->setValue(value);
              });
        label->setTextCommitter([this](const QString& text, std::optional<double> number) {
            return commitTypedText(text, number);
        });
        expressionConnection
            = QObject::connect(property, &QuantitySpinBox::boundExpressionChanged, label, [this]() {
                  updateValueLabel();
              });
        // A box left with a formula it could not use shows what the field holds again
        labelFocusConnection
            = QObject::connect(label, &GizmoValueLabel::focusLeft, label, [this, label]() {
                  QTimer::singleShot(0, label, [this]() { updateValueLabel(); });
              });
    }
    showGuideGeometry(!label);
    updateValueLabel();
}

void Gizmo::setCountBinding(
    CountGetter getter,
    CountSetter setter,
    int minimum,
    int maximum,
    CountExpressionGetter hasExpression
)
{
    countGetter = std::move(getter);
    countSetter = std::move(setter);
    countExpressionGetter = std::move(hasExpression);
    countMinimum = minimum;
    countMaximum = std::max(minimum, maximum);
    if (container) {
        container->rebuildValueLabels();
    }
}

bool Gizmo::hasCountBinding() const
{
    return countGetter && countSetter;
}

void Gizmo::setCountRange(int minimum, int maximum)
{
    countMinimum = minimum;
    countMaximum = std::max(minimum, maximum);
    if (countLabel) {
        countLabel->setRange(countMinimum, countMaximum);
    }
}

bool Gizmo::hasCountExpression() const
{
    return countExpressionGetter && countExpressionGetter();
}

GizmoValueLabel* Gizmo::getCountLabel() const
{
    return countLabel;
}

void Gizmo::setCountLabel(GizmoValueLabel* label)
{
    QObject::disconnect(countLabelConnection);
    countLabel = label;
    if (label) {
        // The box turns away a count outside the range, and anything that still gets past
        // it is brought back inside
        label->setRange(countMinimum, countMaximum);
        countLabelConnection
            = QObject::connect(label, &GizmoValueLabel::valueEdited, label, [this](double value) {
                  const double count = std::clamp(
                      std::round(value),
                      static_cast<double>(countMinimum),
                      static_cast<double>(countMaximum)
                  );
                  countSetter(static_cast<int>(count));
              });
    }
    updateCountLabel();
}

bool Gizmo::isShownInView()
{
    return visible && property;
}

void Gizmo::showValueInLabel()
{
    if (!valueLabel) {
        return;
    }
    std::shared_ptr<App::Expression> expression = property->boundExpression();
    if (!expression) {
        valueLabel->setValue(property->rawValue());
        return;
    }
    const std::string text = ModelParameters::displayText(property->boundObject(), *expression);
    valueLabel->showExpression(QString::fromStdString(text), property->rawValue());
}

QString Gizmo::commitTypedText(const QString& text, std::optional<double> number)
{
    try {
        if (number) {
            // A number typed over a formula replaces it
            releaseExpression();
            property->setValue(*number);
            return {};
        }
        App::DocumentObject* object = property->boundObject();
        if (!object) {
            return QCoreApplication::translate("Gui::Gizmo", "This value takes a number only");
        }
        std::shared_ptr<App::Expression> expr(ModelParameters::parse(object, text.toStdString()));
        // Turns away a result in the wrong unit now, which the field would only show as an error
        Base::Quantity value = ModelParameters::evaluate(*expr, property->value().getUnit());
        if (ModelParameters::isConstant(*expr)) {
            releaseExpression();
            property->setValue(value.getValue());
            return {};
        }
        property->setBoundExpression(expr);
    }
    catch (const Base::Exception& error) {
        return QString::fromUtf8(error.what());
    }
    catch (const std::exception& error) {
        return QString::fromUtf8(error.what());
    }
    return {};
}

void Gizmo::releaseExpression()
{
    if (!property->boundExpression()) {
        return;
    }
    try {
        property->setBoundExpression(nullptr);
    }
    catch (const Base::Exception& error) {
        error.reportException();
    }
}

void Gizmo::setContainer(GizmoContainer* container)
{
    this->container = container;
}

LinearGizmo::LinearGizmo(QuantitySpinBox* property)
{
    this->property = property;
}

SoInteractionKit* LinearGizmo::initDragger()
{
    draggerContainer = new SoLinearDraggerContainer;
    draggerContainer->color.setValue(1, 0, 0);
    dragger = draggerContainer->getDragger();

    dragger->addStartCallback(
        [](void* data, SoDragger*) { static_cast<LinearGizmo*>(data)->draggingStarted(); },
        this
    );
    dragger->addFinishCallback(
        [](void* data, SoDragger*) { static_cast<LinearGizmo*>(data)->draggingFinished(); },
        this
    );
    dragger->addMotionCallback(
        [](void* data, SoDragger*) { static_cast<LinearGizmo*>(data)->draggingContinued(); },
        this
    );

    dragger->labelVisible = false;

    if (draggerStyle == LinearDraggerStyle::Sphere) {
        dragger->setPart("arrow", new SoSphereGeometry);
    }
    else {
        dragger->instantiateBaseGeometry();

        auto arrow = SO_GET_PART(dragger, "arrow", SoArrowGeometry);
        arrow->cylinderHeight = 3.5;
        arrow->cylinderRadius = 0.2;
    }

    updateColorTheme();

    setProperty(property);

    return draggerContainer;
}

void LinearGizmo::uninitDragger()
{
    dragger = nullptr;
    draggerContainer = nullptr;
}

void LinearGizmo::updateColorTheme()
{
    auto* styleParameterManager = Base::provideService<Gui::StyleParameters::ParameterManager>();
    Base::Color baseColor = styleParameterManager->resolve(StyleParameters::LinearGizmoBaseColor);
    Base::Color activeColor = styleParameterManager->resolve(StyleParameters::LinearGizmoActiveColor);

    dragger->color = baseColor.asValue<SbColor>();
    dragger->activeColor = activeColor.asValue<SbColor>();

    auto baseGeom = SO_GET_PART(dragger, "baseGeom", SoArrowBase);
    Base::Color baseGeomColor = styleParameterManager->resolve(
        StyleParameters::DimensionVisualizerColor
    );
    baseGeom->color = baseGeomColor.asValue<SbColor>();
}

GizmoPlacement LinearGizmo::getDraggerPlacement()
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    return {draggerContainer->translation.getValue(), draggerContainer->getPointerDirection()};
}

void LinearGizmo::setDraggerPlacement(const SbVec3f& pos, const SbVec3f& dir)
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    draggerContainer->translation = pos;
    draggerContainer->setPointerDirection(dir);
    updateValueLabel();
}

void LinearGizmo::reverseDir()
{
    auto dir = getDraggerContainer()->getPointerDirection();
    getDraggerContainer()->setPointerDirection(dir * -1);
    updateValueLabel();
}

double LinearGizmo::getDragLength()
{
    double dragLength = dragger->translationIncrementCount.getValue()
        * dragger->translationIncrement.getValue();

    return (dragLength - addFactor) / multFactor;
}

void LinearGizmo::setDragLength(double dragLength)
{
    dragLength = dragLength * multFactor + addFactor;
    dragger->translation = {0, static_cast<float>(dragLength), 0};
    updateValueLabel();
}

void LinearGizmo::setGeometryScale(float scale)
{
    dragger->geometryScale = SbVec3f(scale, scale, scale);
    // Scales the dragger increment in exponents of 10 based on the zoom level (scale)
    constexpr float base = 10.0F;
    dragger->translationIncrement = multFactor * std::pow(base, std::floor(std::log10(scale)));
}

SoLinearDraggerContainer* LinearGizmo::getDraggerContainer()
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    return draggerContainer;
}

void LinearGizmo::setProperty(QuantitySpinBox* property)
{
    QuantitySpinBox::disconnect(quantityChangedConnection);
    QuantitySpinBox::disconnect(formulaDialogConnection);

    this->property = property;
    quantityChangedConnection = QuantitySpinBox::connect(
        property,
        qOverload<double>(&Gui::QuantitySpinBox::valueChanged),
        [this](double value) { setDragLength(value); }
    );
    formulaDialogConnection
        = QuantitySpinBox::connect(property, &Gui::QuantitySpinBox::showFormulaDialog, [this](bool) {
              // Shows the formula, or the value again, once the formula dialog closes
              setVisibility(visible);
              updateValueLabel();
          });

    // Updates the gizmo state based on the new property
    setDragLength(property->rawValue());
    setVisibility(visible);

    if (container) {
        container->rebuildValueLabels();
    }
}

void LinearGizmo::setMultFactor(const double val)
{
    multFactor = val;
    setDragLength(property->value().getValue());
}

void LinearGizmo::setAddFactor(const double val)
{
    addFactor = val;
    setDragLength(property->value().getValue());
}

void LinearGizmo::setDraggerStyle(LinearDraggerStyle style)
{
    draggerStyle = style;
}

void LinearGizmo::setClickCallback(ClickCallback callback)
{
    clickCallback = std::move(callback);
}

void LinearGizmo::setVisibility(bool visible)
{
    this->visible = visible;
    getDraggerContainer()->visible = visible;

    if (container) {
        container->refreshValueLabels();
    }
}

void LinearGizmo::updateValueLabel()
{
    if (!draggerContainer) {
        return;
    }
    if (valueLabel) {
        valueLabel->showDistance(
            draggerContainer->translation.getValue(),
            draggerContainer->getPointerDirection(),
            dragger->translation.getValue()[1]
        );
        showValueInLabel();
    }
    updateCountLabel();
}

void LinearGizmo::updateCountLabel()
{
    if (!countLabel || !draggerContainer || !countGetter) {
        return;
    }
    SbVec3f dir = draggerContainer->getPointerDirection();
    dir.normalize();
    // Just past the arrow head, in the arrow's own units so the gap looks the same at any zoom
    constexpr float beyondTip = 8.0F;
    const float travel = dragger->translation.getValue()[1];
    const float scale = dragger->geometryScale.getValue()[0];
    countLabel->showBoxAt(
        draggerContainer->translation.getValue() + dir * (travel + beyondTip * scale),
        dir
    );
    countLabel->setValue(countGetter());
}

void LinearGizmo::showGuideGeometry(bool show)
{
    if (dragger) {
        dragger->baseGeomVisible = show && draggerStyle == LinearDraggerStyle::Arrow;
    }
}

void LinearGizmo::draggingStarted()
{
    initialValue = property->value().getValue();
    hasDragged = false;
    dragger->translationIncrementCount.setValue(0);

    if (isDelayedUpdateEnabled()) {
        property->blockSignals(true);
    }
}

void LinearGizmo::draggingFinished()
{
    if (isDelayedUpdateEnabled()) {
        property->blockSignals(false);
        property->valueChanged(property->value().getValue());
    }

    if (!hasDragged && clickCallback) {
        clickCallback();
    }

    if (valueLabel && valueLabel->isShown()) {
        valueLabel->focus();
    }
    else {
        property->setFocus();
        property->selectAll();
    }
}

void LinearGizmo::draggingContinued()
{
    if (!hasDragged) {
        // Dragging a value that a formula drives replaces the formula, as typing over it does
        releaseExpression();
    }
    hasDragged = true;
    double value = initialValue + getDragLength();

    auto fineModifier = GizmoContainer::getFineSnapModifier();
    auto modifiers = QApplication::queryKeyboardModifiers();
    bool fineModifierPressed = modifiers == fineModifier;
    bool coarseByDefault = GizmoContainer::isCoarseByDefault();
    bool useCoarseSnap = coarseByDefault != fineModifierPressed;

    if (GizmoContainer::isCoarseSnapEnabled() && useCoarseSnap) {
        double baseStep = std::abs(dragger->translationIncrement.getValue() / multFactor);
        value = snapToStep(value, baseStep * getCoarseLinearSnapMultiplier());
    }

    value = std::clamp(value, property->minimum(), property->maximum());

    property->setValue(value);
    setDragLength(value);
}


RotationGizmo::RotationGizmo(QuantitySpinBox* property)
{
    this->property = property;
}

RotationGizmo::~RotationGizmo()
{
    translationSensor.detach();
    translationSensor.setData(nullptr);
    translationSensor.setFunction(nullptr);
}

SoInteractionKit* RotationGizmo::initDragger()
{
    multFactor = std::numbers::pi_v<float> / 180.0;
    draggerContainer = new SoRotationDraggerContainer;

    draggerContainer->color.setValue(1, 0, 0);
    dragger = draggerContainer->getDragger();
    dragger->rotationIncrement = std::numbers::pi / 180.0;

    auto rotator = new SoRotatorGeometry;
    rotator->arcAngle = std::numbers::pi_v<float> / 6.0f;
    rotator->arcRadius = 16.0f;
    dragger->setPart("rotator", rotator);

    dragger->addStartCallback(
        [](void* data, SoDragger*) { static_cast<RotationGizmo*>(data)->draggingStarted(); },
        this
    );
    dragger->addFinishCallback(
        [](void* data, SoDragger*) { static_cast<RotationGizmo*>(data)->draggingFinished(); },
        this
    );
    dragger->addMotionCallback(
        [](void* data, SoDragger*) { static_cast<RotationGizmo*>(data)->draggingContinued(); },
        this
    );

    setProperty(property);

    updateColorTheme();

    return draggerContainer;
}

void RotationGizmo::uninitDragger()
{
    dragger = nullptr;
    draggerContainer = nullptr;

    translationSensor.detach();
    translationSensor.setData(nullptr);
    translationSensor.setFunction(nullptr);
}

void RotationGizmo::updateColorTheme()
{
    auto* styleParameterManager = Base::provideService<Gui::StyleParameters::ParameterManager>();
    Base::Color baseColor = styleParameterManager->resolve(StyleParameters::RotationGizmoBaseColor);
    Base::Color activeColor = styleParameterManager->resolve(StyleParameters::RotationGizmoActiveColor);

    dragger->color = baseColor.asValue<SbColor>();
    dragger->activeColor = activeColor.asValue<SbColor>();
}

GizmoPlacement RotationGizmo::getDraggerPlacement()
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    return {draggerContainer->translation.getValue(), draggerContainer->getPointerDirection()};
}

void RotationGizmo::setDraggerPlacement(const SbVec3f& pos, const SbVec3f& dir)
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    draggerContainer->translation = pos;
    draggerContainer->setPointerDirection(dir);
    updateValueLabel();
}

void RotationGizmo::reverseDir()
{
    auto dir = getDraggerContainer()->getPointerDirection();
    getDraggerContainer()->setPointerDirection(dir * -1);
    updateValueLabel();
}

void RotationGizmo::placeOverLinearGizmo(LinearGizmo* gizmo)
{
    linearGizmo = gizmo;

    GizmoPlacement placement = gizmo->getDraggerPlacement();

    draggerContainer->translation = Base::convertTo<SbVec3f>(placement.pos);
    draggerContainer->setPointerDirection(placement.dir);

    translationSensor.setData(this);
    translationSensor.setFunction(translationSensorCB);
    translationSensor.setPriority(0);
    SoSFVec3f& translation = gizmo->getDraggerContainer()->getDragger()->translation;
    translationSensor.attach(&translation);
    translation.touch();

    automaticOrientation = true;
    updateValueLabel();
}

void RotationGizmo::translationSensorCB(void* data, SoSensor* sensor)
{
    auto sudoThis = static_cast<RotationGizmo*>(data);
    auto translationSensor = static_cast<SoFieldSensor*>(sensor);

    GizmoPlacement placement = sudoThis->linearGizmo->getDraggerPlacement();

    SbVec3f translation = static_cast<SoSFVec3f*>(translationSensor->getAttachedField())->getValue();
    float yComp = translation.getValue()[1];
    SbVec3f dir = placement.dir;
    dir.normalize();
    sudoThis->draggerContainer->translation = placement.pos + dir * (yComp + sudoThis->sepDistance);
    sudoThis->updateValueLabel();
}

void RotationGizmo::placeBelowLinearGizmo(LinearGizmo* gizmo)
{
    linearGizmo = gizmo;

    GizmoPlacement placement = gizmo->getDraggerPlacement();

    draggerContainer->translation = Base::convertTo<SbVec3f>(placement.pos);
    draggerContainer->setPointerDirection(-placement.dir);

    translationSensor.setData(this);
    translationSensor.setFunction(translationSensorCB);
    translationSensor.setPriority(0);
    SoSFVec3f& translation = gizmo->getDraggerContainer()->getDragger()->translation;
    translationSensor.attach(&translation);
    translation.touch();
    updateValueLabel();
}

double RotationGizmo::getRotAngle()
{
    double rotAngle = dragger->rotationIncrementCount.getValue()
        * dragger->rotationIncrement.getValue();

    return (rotAngle - addFactor) / multFactor;
}

void RotationGizmo::setRotAngle(double angle)
{
    angle = multFactor * angle + addFactor;
    dragger->rotation = SbRotation({0, 0, 1.0f}, static_cast<float>(angle));
    updateValueLabel();
}

void RotationGizmo::setGeometryScale(float scale)
{
    dragger->geometryScale = SbVec3f(scale, scale, scale);
}

SoRotationDraggerContainer* RotationGizmo::getDraggerContainer()
{
    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    return draggerContainer;
}

void RotationGizmo::draggingStarted()
{
    initialValue = property->value().getValue();
    lastDragOffset = 0.0;
    hasDragged = false;
    dragger->rotationIncrementCount.setValue(0);

    if (isDelayedUpdateEnabled()) {
        property->blockSignals(true);
    }
}

void RotationGizmo::draggingFinished()
{
    if (isDelayedUpdateEnabled()) {
        property->blockSignals(false);
        property->valueChanged(property->value().getValue());
    }

    if (!hasDragged && clickCallback) {
        clickCallback();
    }

    if (valueLabel && valueLabel->isShown()) {
        valueLabel->focus();
    }
    else {
        property->setFocus();
        property->selectAll();
    }
}

void RotationGizmo::draggingContinued()
{
    if (!hasDragged) {
        // Dragging a value that a formula drives replaces the formula, as typing over it does
        releaseExpression();
    }
    hasDragged = true;
    const double period = getRotationPeriod(multFactor);
    double dragOffset = getClosestEquivalentAngle(getRotAngle(), lastDragOffset, period);
    lastDragOffset = dragOffset;
    double value = initialValue + dragOffset;

    auto fineModifier = GizmoContainer::getFineSnapModifier();
    auto modifiers = QApplication::queryKeyboardModifiers();
    bool fineModifierPressed = modifiers == fineModifier;
    bool coarseByDefault = GizmoContainer::isCoarseByDefault();
    bool useCoarseSnap = coarseByDefault != fineModifierPressed;

    if (GizmoContainer::isCoarseSnapEnabled() && useCoarseSnap) {
        value = snapToStep(value, getCoarseRotationSnapMultiplier());
    }

    value = clampDragAngle(value, property->minimum(), property->maximum(), period);

    property->setValue(value);
    setRotAngle(value);
}

void RotationGizmo::orientAlongCamera(SoCamera* camera)
{
    if (!automaticOrientation) {
        return;
    }

    SbVec3f cameraDir {0, 0, 1};
    camera->orientation.getValue().multVec(cameraDir, cameraDir);
    SbVec3f pointerDir = getDraggerContainer()->getPointerDirection();

    pointerDir.normalize();
    auto proj = cameraDir - cameraDir.dot(pointerDir) * pointerDir;
    if (proj.equals(SbVec3f {0, 0, 0}, 0.001)) {
        return;
    }

    assert(draggerContainer && "Forgot to call GizmoContainer::initGizmos?");
    draggerContainer->setArcNormalDirection(proj);
}

void RotationGizmo::setProperty(QuantitySpinBox* property)
{
    QuantitySpinBox::disconnect(quantityChangedConnection);
    QuantitySpinBox::disconnect(formulaDialogConnection);

    this->property = property;
    quantityChangedConnection = QuantitySpinBox::connect(
        property,
        qOverload<double>(&Gui::QuantitySpinBox::valueChanged),
        [this](double value) { setRotAngle(value); }
    );
    formulaDialogConnection
        = QuantitySpinBox::connect(property, &Gui::QuantitySpinBox::showFormulaDialog, [this](bool) {
              // Shows the formula, or the value again, once the formula dialog closes
              setVisibility(visible);
              updateValueLabel();
          });

    // Updates the gizmo state based on the new property
    setRotAngle(property->rawValue());
    setVisibility(visible);

    if (container) {
        container->rebuildValueLabels();
    }
}

void RotationGizmo::setMultFactor(const double val)
{
    multFactor = val;
    setRotAngle(property->value().getValue());
}

void RotationGizmo::setAddFactor(const double val)
{
    addFactor = val;
    setRotAngle(property->value().getValue());
}

void RotationGizmo::setClickCallback(ClickCallback callback)
{
    clickCallback = std::move(callback);
}

void RotationGizmo::setVisibility(bool visible)
{
    this->visible = visible;
    getDraggerContainer()->visible = visible;

    if (container) {
        container->refreshValueLabels();
    }
}

void RotationGizmo::updateValueLabel()
{
    if (!draggerContainer) {
        return;
    }
    if (valueLabel) {
        // The handle sits at the rotator's pivot, turned by the dragger's rotation about the
        // container's local Z; at a value of zero it points along the pivot
        auto rotator = SO_GET_PART(dragger, "rotator", SoRotatorGeometryKit);
        SbVec3f pivot = rotator->pivotPosition.getValue();
        SbRotation placement = draggerContainer->rotation.getValue();

        SbVec3f axis(0.0F, 0.0F, 1.0F);
        placement.multVec(axis, axis);
        SbVec3f zeroRay;
        placement.multVec(pivot, zeroRay);

        // Just outside the handle, so the box never covers the handle it belongs to; in the
        // rotator's own units, so the gap stays the same on screen at any zoom
        constexpr float clearance = 2.5F;
        float radius = (pivot.length() + clearance) * dragger->geometryScale.getValue()[0];
        auto sweep = static_cast<float>(property->rawValue() * multFactor + addFactor);

        valueLabel->showAngle(draggerContainer->translation.getValue(), axis, zeroRay, sweep, radius);
        showValueInLabel();
    }
    updateCountLabel();
}

void RotationGizmo::updateCountLabel()
{
    if (!countLabel || !draggerContainer || !countGetter) {
        return;
    }
    auto rotator = SO_GET_PART(dragger, "rotator", SoRotatorGeometryKit);
    SbVec3f pivot = rotator->pivotPosition.getValue();
    SbRotation placement = draggerContainer->rotation.getValue();
    SbVec3f axis(0.0F, 0.0F, 1.0F);
    placement.multVec(axis, axis);
    SbVec3f zeroRay;
    placement.multVec(pivot, zeroRay);

    // Where the handle is now: turned from the zero ray by the value
    auto sweep = static_cast<float>(property->rawValue() * multFactor + addFactor);
    SbVec3f handleRay;
    SbRotation(axis, sweep).multVec(zeroRay, handleRay);
    handleRay.normalize();

    // Further out than the angle's own box, which runs just outside the handle
    constexpr float clearance = 6.0F;
    float radius = (pivot.length() + clearance) * dragger->geometryScale.getValue()[0];
    countLabel->showBoxAt(draggerContainer->translation.getValue() + handleRay * radius, handleRay);
    countLabel->setValue(countGetter());
}

void RotationGizmo::showGuideGeometry(bool show)
{
    if (dragger) {
        dragger->baseGeomVisible = show && hasGuideGeometry();
    }
}

DirectedRotationGizmo::DirectedRotationGizmo(QuantitySpinBox* property)
    : RotationGizmo(property)
{}

SoInteractionKit* DirectedRotationGizmo::initDragger()
{
    SoInteractionKit* ret = inherited::initDragger();

    auto dragger = getDraggerContainer()->getDragger();
    auto rotator = new SoRotatorGeometry2;
    rotator->arcAngle = std::numbers::pi_v<float> / 6.0f;
    rotator->arcRadius = 16.0f;
    rotator->rightArrowVisible = false;
    dragger->setPart("rotator", rotator);

    updateColorTheme();

    return ret;
}

void DirectedRotationGizmo::flipArrow()
{
    auto dragger = getDraggerContainer()->getDragger();
    auto rotator = SO_GET_PART(dragger, "rotator", SoRotatorGeometry2);

    rotator->toggleArrowVisibility();
}


RadialGizmo::RadialGizmo(QuantitySpinBox* property)
    : RotationGizmo(property)
{}

SoInteractionKit* RadialGizmo::initDragger()
{
    SoInteractionKit* ret = inherited::initDragger();

    auto dragger = getDraggerContainer()->getDragger();
    auto rotator = new SoRotatorArrow;
    rotator->geometryScale.connectFrom(&dragger->geometryScale);
    dragger->setPart("rotator", rotator);

    dragger->instantiateBaseGeometry();

    updateColorTheme();

    return ret;
}

void RadialGizmo::setRadius(float radius)
{
    auto dragger = getDraggerContainer()->getDragger();
    auto rotator = SO_GET_PART(dragger, "rotator", SoRotatorArrow);
    auto baseGeom = SO_GET_PART(dragger, "baseGeom", SoRotatorBase);

    rotator->radius = baseGeom->arcRadius = radius;
}

void RadialGizmo::flipArrow()
{
    auto dragger = getDraggerContainer()->getDragger();
    auto rotator = SO_GET_PART(dragger, "rotator", SoRotatorArrow);

    rotator->flipArrow();
}

void RadialGizmo::updateColorTheme()
{
    auto dragger = getDraggerContainer()->getDragger();

    auto* styleParameterManager = Base::provideService<Gui::StyleParameters::ParameterManager>();
    Base::Color baseColor = styleParameterManager->resolve(StyleParameters::RotationGizmoBaseColor);
    Base::Color activeColor = styleParameterManager->resolve(StyleParameters::RotationGizmoActiveColor);

    dragger->color = baseColor.asValue<SbColor>();
    dragger->activeColor = activeColor.asValue<SbColor>();

    auto baseGeom = SO_GET_PART(dragger, "baseGeom", SoRotatorBase);
    Base::Color baseGeomColor = styleParameterManager->resolve(
        StyleParameters::DimensionVisualizerColor
    );
    baseGeom->color = baseGeomColor.asValue<SbColor>();
}

SO_KIT_SOURCE(GizmoContainer)

void GizmoContainer::initClass()
{
    SO_KIT_INIT_CLASS(GizmoContainer, SoBaseKit, "BaseKit");
}

GizmoContainer::GizmoContainer()
    : viewProvider(nullptr)
    , labelContext(std::make_unique<QObject>())
{
    SO_KIT_CONSTRUCTOR(GizmoContainer);

#if defined(Q_OS_MACOS) || defined(Q_OS_FREEBSD) || defined(Q_OS_OPENBSD)
    this->ref();
#endif

    FC_ADD_CATALOG_ENTRY(annotation, So3DAnnotation, this);
    FC_ADD_CATALOG_ENTRY(pickStyle, SoPickStyle, annotation);
    FC_ADD_CATALOG_ENTRY(toggleSwitch, SoToggleSwitch, annotation);
    FC_ADD_CATALOG_ENTRY(geometry, SoSeparator, toggleSwitch);

    SO_KIT_INIT_INSTANCE();

    SO_KIT_ADD_FIELD(visible, (1));

    auto pickStyle = SO_GET_ANY_PART(this, "pickStyle", SoPickStyle);
    pickStyle->style = SoPickStyle::SHAPE_ON_TOP;

    auto toggleSwitch = SO_GET_ANY_PART(this, "toggleSwitch", SoToggleSwitch);
    toggleSwitch->on.connectFrom(&visible);

    setPart("geometry", new SoSeparator);

    cameraSensor.setFunction(&GizmoContainer::cameraChangeCallback);
    cameraSensor.setData(this);

    cameraPositionSensor.setData(this);
    cameraPositionSensor.setFunction(cameraPositionChangeCallback);

    visibleSensor.setFunction(&GizmoContainer::visibleChangedCallback);
    visibleSensor.setData(this);
    visibleSensor.setPriority(0);
    visibleSensor.attach(&visible);
}

GizmoContainer::~GizmoContainer()
{
    visibleSensor.setData(nullptr);
    visibleSensor.detach();

    // The labels point back at the gizmos, so they go first
    removeValueLabels();

    cameraSensor.setData(nullptr);
    cameraSensor.detach();

    cameraPositionSensor.setData(nullptr);
    cameraPositionSensor.detach();

    uninitGizmos();

    if (!viewProvider.expired()) {
        viewProvider->setGizmoContainer(nullptr);
    }
}

void GizmoContainer::initGizmos()
{
    auto geometry = SO_GET_ANY_PART(this, "geometry", SoSeparator);
    for (auto gizmo : gizmos) {
        geometry->addChild(gizmo->initDragger());
    }
}

void GizmoContainer::uninitGizmos()
{
    for (auto gizmo : gizmos) {
        gizmo->uninitDragger();
        delete gizmo;
    }
    gizmos.clear();
}

void GizmoContainer::addGizmos(std::initializer_list<Gui::Gizmo*> gizmos)
{
    assert(this->gizmos.size() == 0 && "Already called GizmoContainer::addGizmos?");

    for (auto gizmo : gizmos) {
        addGizmo(gizmo);
    }
    initGizmos();
}

void GizmoContainer::addGizmo(Gizmo* gizmo)
{
    assert(std::ranges::find(gizmos, gizmo) == gizmos.end() && "this gizmo is already added!");
    gizmos.push_back(gizmo);
    gizmo->setContainer(this);
}

void GizmoContainer::attachViewer(Gui::View3DInventorViewer* viewer, Base::Placement& origin)
{
    if (!viewer) {
        return;
    }

    setUpAutoScale(viewer->getSoRenderManager()->getCamera());

    auto mat = origin.toMatrix();

    viewer->getDocument()->setEditingTransform(mat);
    So3DAnnotation* annotation = SO_GET_ANY_PART(this, "annotation", So3DAnnotation);
    viewer->setupEditingRoot(annotation, &mat);

    labelViewer = viewer;
    labelOrigin = origin;
    createValueLabels();

    // The task panel queues focus for its own first field while it is built, which is
    // before this; queueing now hands the keyboard to the first box after that
    QTimer::singleShot(0, labelContext.get(), [this]() {
        focusFirstValueLabel();
        firstFocusDone = true;
    });
}

void GizmoContainer::setUpAutoScale(SoCamera* cameraIn)
{
    if (cameraIn->getTypeId() == SoOrthographicCamera::getClassTypeId()) {
        auto localCamera = dynamic_cast<SoOrthographicCamera*>(cameraIn);
        cameraSensor.attach(&localCamera->height);
        cameraPositionSensor.attach(&localCamera->orientation);
        calculateScaleAndOrientation();
    }
    else if (cameraIn->getTypeId() == SoPerspectiveCamera::getClassTypeId()) {
        auto localCamera = dynamic_cast<SoPerspectiveCamera*>(cameraIn);
        cameraSensor.attach(&localCamera->position);
        cameraPositionSensor.attach(&localCamera->orientation);
        calculateScaleAndOrientation();
    }
}

void GizmoContainer::calculateScaleAndOrientation()
{
    if (cameraSensor.getAttachedField()) {
        cameraChangeCallback(this, nullptr);
        cameraPositionChangeCallback(this, nullptr);
    }
}

void GizmoContainer::cameraChangeCallback(void* data, SoSensor*)
{
    auto sudoThis = static_cast<GizmoContainer*>(data);

    SoField* field = sudoThis->cameraSensor.getAttachedField();
    if (!field) {
        return;
    }

    auto camera = static_cast<SoCamera*>(field->getContainer());

    SbViewVolume viewVolume = camera->getViewVolume();
    for (auto gizmo : sudoThis->gizmos) {
        float localScale = viewVolume.getWorldToScreenScale(gizmo->getDraggerPlacement().pos, 0.015);
        gizmo->setGeometryScale(localScale);
        gizmo->updateValueLabel();
    }
}

void GizmoContainer::cameraPositionChangeCallback(void* data, SoSensor*)
{
    auto sudoThis = static_cast<GizmoContainer*>(data);

    SoField* field = sudoThis->cameraSensor.getAttachedField();
    if (field) {
        auto camera = static_cast<SoCamera*>(field->getContainer());

        for (auto gizmo : sudoThis->gizmos) {
            gizmo->orientAlongCamera(camera);
            gizmo->updateValueLabel();
        }
    }
}

bool GizmoContainer::isEnabled()
{
    static auto hGrp = getGizmoParameterGroup();

    return hGrp->GetBool("EnableGizmos", true);
}

bool GizmoContainer::isCoarseSnapEnabled()
{
    return getGizmoParameterGroup()->GetBool("EnableCoarseSnap", true);
}

Qt::KeyboardModifier GizmoContainer::getFineSnapModifier()
{
    auto modifier = static_cast<Qt::KeyboardModifier>(
        getGizmoParameterGroup()->GetInt("FineSnapModifier", static_cast<long>(Qt::ShiftModifier))
    );
    if (modifier == Qt::ControlModifier) {
        return modifier;
    }
    return Qt::ShiftModifier;
}

InputHint::UserInput GizmoContainer::getFineSnapKey()
{
    if (getFineSnapModifier() == Qt::ControlModifier) {
        return InputHint::UserInput::ModifierCtrl;
    }
    return InputHint::UserInput::ModifierShift;
}

bool GizmoContainer::isCoarseByDefault()
{
    return getGizmoParameterGroup()->GetInt(
               "DefaultCoarseDragBehavior",
               static_cast<int>(DefaultDragBehavior::Coarse)
           )
        == static_cast<int>(DefaultDragBehavior::Coarse);
}

bool GizmoContainer::isValueLabelsEnabled()
{
    return getGizmoParameterGroup()->GetBool("ShowValueLabels", true);
}

void GizmoContainer::createValueLabels()
{
    removeValueLabels();
    if (!labelViewer || !isValueLabelsEnabled()) {
        return;
    }

    // One box per task panel field: Fillet's two arrows, and an equal-distance Chamfer's,
    // edit the same field
    std::vector<QuantitySpinBox*> labelled;
    for (auto gizmo : gizmos) {
        QuantitySpinBox* property = gizmo->getProperty();
        if (!property || std::ranges::find(labelled, property) != labelled.end()) {
            continue;
        }
        labelled.push_back(property);

        auto label = std::make_unique<GizmoValueLabel>(labelViewer, labelOrigin, property->unit());
        GizmoValueLabel* raw = label.get();
        connectLabel(raw);

        gizmo->setValueLabel(raw);
        valueLabels.push_back(std::move(label));
    }

    for (auto gizmo : gizmos) {
        if (!gizmo->hasCountBinding()) {
            continue;
        }
        auto label = std::make_unique<GizmoValueLabel>(
            labelViewer,
            labelOrigin,
            Base::Unit(),
            GizmoValueLabel::Kind::Count
        );
        GizmoValueLabel* raw = label.get();
        connectLabel(raw);
        gizmo->setCountLabel(raw);
        valueLabels.push_back(std::move(label));
    }

    refreshValueLabels();
}

void GizmoContainer::connectLabel(GizmoValueLabel* raw)
{
    QObject::connect(raw, &GizmoValueLabel::accepted, labelContext.get(), &acceptActiveDialog);
    QObject::connect(raw, &GizmoValueLabel::cancelled, labelContext.get(), &rejectActiveDialog);
    QObject::connect(raw, &GizmoValueLabel::tabbed, labelContext.get(), [this, raw](bool backwards) {
        focusNextValueLabel(raw, backwards);
    });
    QObject::connect(raw, &GizmoValueLabel::focusLeft, labelContext.get(), [this]() {
        QTimer::singleShot(0, labelContext.get(), [this]() { refreshValueLabels(); });
    });
}

void GizmoContainer::removeValueLabels()
{
    for (auto gizmo : gizmos) {
        gizmo->setValueLabel(nullptr);
        gizmo->setCountLabel(nullptr);
    }
    valueLabels.clear();
}

std::vector<std::pair<Gizmo*, GizmoValueLabel*>> GizmoContainer::labelsInOrder() const
{
    std::vector<std::pair<Gizmo*, GizmoValueLabel*>> labels;
    for (auto gizmo : gizmos) {
        if (GizmoValueLabel* value = gizmo->getValueLabel()) {
            labels.emplace_back(gizmo, value);
        }
        if (GizmoValueLabel* count = gizmo->getCountLabel()) {
            labels.emplace_back(gizmo, count);
        }
    }
    return labels;
}

void GizmoContainer::rebuildValueLabels()
{
    // Nothing to rebuild before the gizmos are attached to a view, or with labels turned off
    if (valueLabels.empty()) {
        return;
    }
    createValueLabels();
}

void GizmoContainer::refreshValueLabels()
{
    for (auto [gizmo, label] : labelsInOrder()) {
        // A count box already hides when the value box's own formula hides the whole
        // dragger (isShownInView(), below) - this adds the count's own formula as a
        // second, independent reason for the count box alone to hide, on top of that
        bool isCountLabel = label == gizmo->getCountLabel();
        bool shown = visible.getValue() && gizmo->isShownInView()
            && (!isCountLabel || !gizmo->hasCountExpression());
        // A box being typed in never disappears under the user, e.g. when what has been
        // typed so far fails to recompute and the task panel hides its gizmos
        if (!shown && label->hasFocus()) {
            shown = true;
        }

        bool appears = shown && !label->isShown();
        label->setShown(shown);
        if (appears && firstFocusDone && isKeyboardOnView()) {
            label->focus();
        }
    }
}

void GizmoContainer::focusFirstValueLabel()
{
    for (auto [gizmo, label] : labelsInOrder()) {
        if (label->isShown()) {
            label->focus();
            return;
        }
    }
}

void GizmoContainer::focusNextValueLabel(GizmoValueLabel* from, bool backwards)
{
    std::vector<GizmoValueLabel*> shown;
    for (auto [gizmo, label] : labelsInOrder()) {
        if (label->isShown()) {
            shown.push_back(label);
        }
    }

    auto found = std::ranges::find(shown, from);
    if (shown.size() < 2 || found == shown.end()) {
        return;
    }

    auto count = static_cast<std::ptrdiff_t>(shown.size());
    auto index = std::distance(shown.begin(), found);
    shown[(index + (backwards ? count - 1 : 1)) % count]->focus();
}

bool GizmoContainer::isKeyboardOnView() const
{
    QWidget* focus = QApplication::focusWidget();
    if (!focus) {
        return true;
    }
    if (qobject_cast<QAbstractSpinBox*>(focus) || qobject_cast<QLineEdit*>(focus)) {
        return false;
    }
    return labelViewer && (focus == labelViewer || labelViewer->isAncestorOf(focus));
}

void GizmoContainer::visibleChangedCallback(void* data, SoSensor*)
{
    if (auto self = static_cast<GizmoContainer*>(data)) {
        self->refreshValueLabels();
    }
}

std::unique_ptr<GizmoContainer> GizmoContainer::create(
    std::initializer_list<Gui::Gizmo*> gizmos,
    ViewProviderDragger* vp
)
{
    auto gizmoContainer = std::make_unique<GizmoContainer>();
    gizmoContainer->addGizmos(gizmos);
    gizmoContainer->viewProvider = vp;

    vp->setGizmoContainer(gizmoContainer.get());

    return gizmoContainer;
}
