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

#pragma once

#include <functional>
#include <initializer_list>
#include <memory>
#include <optional>
#include <utility>
#include <vector>

#include <QtCore/Qt>

#include <Inventor/fields/SoSFBool.h>
#include <Inventor/sensors/SoFieldSensor.h>
#include <Inventor/nodekits/SoBaseKit.h>
#include <Inventor/SbVec3f.h>
#include <QMetaObject>
#include <QObject>
#include <QPointer>
#include <QString>

#include <Base/Placement.h>
#include <Gui/DocumentObserver.h>
#include <Gui/InputHint.h>

#include <FCGlobal.h>

class SoDragger;
class SoCamera;
class SoInteractionKit;

namespace Gui
{
class GizmoContainer;
class GizmoValueLabel;
class QuantitySpinBox;
class SoLinearDragger;
class SoLinearDraggerContainer;
class SoRotationDragger;
class SoRotationDraggerContainer;
class View3DInventorViewer;
class ViewProviderDragger;

struct GizmoPlacement
{
    SbVec3f pos;
    SbVec3f dir;
};

class GuiExport Gizmo
{
public:
    virtual ~Gizmo() = default;
    virtual SoInteractionKit* initDragger() = 0;
    virtual void uninitDragger() = 0;

    virtual GizmoPlacement getDraggerPlacement() = 0;
    virtual void setDraggerPlacement(const SbVec3f& pos, const SbVec3f& dir) = 0;
    void setDraggerPlacement(const Base::Vector3d& pos, const Base::Vector3d& dir);

    virtual void setGeometryScale(float scale) = 0;
    virtual void orientAlongCamera([[maybe_unused]] SoCamera* camera) {};
    bool isDelayedUpdateEnabled();

    double getMultFactor();
    double getAddFactor();

    bool getVisibility();

    /// The task panel field this gizmo edits
    QuantitySpinBox* getProperty() const;
    /// The in-view value of this gizmo, or nullptr when it has none
    GizmoValueLabel* getValueLabel() const;
    void setValueLabel(GizmoValueLabel* label);
    /// Brings the value label in line with the gizmo's place and value
    virtual void updateValueLabel()
    {}

    using CountGetter = std::function<int()>;
    using CountSetter = std::function<void(int)>;
    /// Reports whether the count's own source (not the value box's) is driven by a formula
    using CountExpressionGetter = std::function<bool()>;
    /// Gives the gizmo a box beside it for a number of copies, read and written through these;
    /// the box takes no count outside minimum..maximum. hasExpression, when given, is asked
    /// whether the count box hides for a formula: unlike the value box, it takes numbers only
    void setCountBinding(
        CountGetter getter,
        CountSetter setter,
        int minimum,
        int maximum,
        CountExpressionGetter hasExpression = {}
    );
    bool hasCountBinding() const;
    /// Brings the count box's range in step with a panel box that has widened (or since
    /// narrowed) from outside, without touching the getter, the setter or the current value -
    /// cheaper than setCountBinding, which rebuilds every value label in the container
    void setCountRange(int minimum, int maximum);
    /// Whether the count's own source is a formula, if setCountBinding was given a way to ask
    bool hasCountExpression() const;
    GizmoValueLabel* getCountLabel() const;
    void setCountLabel(GizmoValueLabel* label);
    /// Brings the count box in line with the gizmo's place and the current count
    virtual void updateCountLabel()
    {}

    /// Whether the gizmo is drawn. One whose field has a formula is drawn too, with the
    /// formula in its box.
    bool isShownInView();
    void setContainer(GizmoContainer* container);

protected:
    /// Puts the field's value, or its formula when it has one, in the value label
    void showValueInLabel();
    /// Binds the field to a formula typed in the value label, or sets a number typed over
    /// one; returns why the text cannot be used
    QString commitTypedText(const QString& text, std::optional<double> number);
    /// Drops the field's formula as a drag begins, so the dragged value replaces it
    void releaseExpression();

    /// Shows or hides the gizmo's own guide line or arc, which the value label replaces
    virtual void showGuideGeometry([[maybe_unused]] bool show)
    {}

    double multFactor = 1.0f;
    double addFactor = 0.0f;

    QuantitySpinBox* property = nullptr;
    double initialValue;

    bool visible = true;

    GizmoValueLabel* valueLabel = nullptr;
    GizmoContainer* container = nullptr;
    QMetaObject::Connection valueLabelConnection;
    QMetaObject::Connection expressionConnection;
    QMetaObject::Connection labelFocusConnection;

    CountGetter countGetter;
    CountSetter countSetter;
    CountExpressionGetter countExpressionGetter;
    int countMinimum = 1;
    int countMaximum = 1;
    GizmoValueLabel* countLabel = nullptr;
    QMetaObject::Connection countLabelConnection;
};

enum class LinearDraggerStyle
{
    Arrow,
    Sphere,
};

class GuiExport LinearGizmo: public Gizmo
{
public:
    using ClickCallback = std::function<void()>;

    LinearGizmo(QuantitySpinBox* property);
    ~LinearGizmo() override = default;

    SoInteractionKit* initDragger() override;
    void uninitDragger() override;

    void updateColorTheme();

    // Returns the position and rotation of the base of the dragger
    GizmoPlacement getDraggerPlacement() override;
    void setDraggerPlacement(const SbVec3f& pos, const SbVec3f& dir) override;
    void reverseDir();
    // Returns the drag distance from the base of the feature
    double getDragLength();
    void setDragLength(double dragLength);
    void setGeometryScale(float scale) override;
    SoLinearDraggerContainer* getDraggerContainer();
    void setProperty(QuantitySpinBox* property);
    void setMultFactor(const double val);
    void setAddFactor(const double val);
    void setDraggerStyle(LinearDraggerStyle style);
    void setClickCallback(ClickCallback callback);
    void setVisibility(bool visible);
    void updateValueLabel() override;
    void updateCountLabel() override;

protected:
    void showGuideGeometry(bool show) override;

private:
    SoLinearDragger* dragger = nullptr;
    SoLinearDraggerContainer* draggerContainer = nullptr;
    QMetaObject::Connection quantityChangedConnection;
    QMetaObject::Connection formulaDialogConnection;
    LinearDraggerStyle draggerStyle = LinearDraggerStyle::Arrow;
    bool hasDragged = false;
    ClickCallback clickCallback;

    void draggingStarted();
    void draggingFinished();
    void draggingContinued();

    using inherited = Gizmo;
};

class GuiExport RotationGizmo: public Gizmo
{
public:
    using ClickCallback = std::function<void()>;

    RotationGizmo(QuantitySpinBox* property);
    ~RotationGizmo() override;

    SoInteractionKit* initDragger() override;
    void uninitDragger() override;

    void updateColorTheme();

    // Distance between the linear gizmo base and rotation gizmo
    double sepDistance = 0;
    // Controls if the gizmo is automatically rotated around the pointer in the
    // to always face the camera
    bool automaticOrientation = false;

    // Returns the position and rotation of the base of the dragger
    GizmoPlacement getDraggerPlacement() override;
    void setDraggerPlacement(const SbVec3f& pos, const SbVec3f& dir) override;
    void reverseDir();
    // The two gizmos are separated by sepDistance units
    void placeOverLinearGizmo(LinearGizmo* gizmo);
    void placeBelowLinearGizmo(LinearGizmo* gizmo);
    // Returns the rotation angle wrt the normal axis
    double getRotAngle();
    void setRotAngle(double angle);
    void setGeometryScale(float scale) override;
    SoRotationDraggerContainer* getDraggerContainer();
    void orientAlongCamera(SoCamera* camera) override;
    void setProperty(QuantitySpinBox* property);
    void setMultFactor(const double val);
    void setAddFactor(const double val);
    void setClickCallback(ClickCallback callback);
    void setVisibility(bool visible);
    void updateValueLabel() override;
    void updateCountLabel() override;

protected:
    void showGuideGeometry(bool show) override;
    /// Whether the dragger draws a guide arc of its own (see RadialGizmo)
    virtual bool hasGuideGeometry() const
    {
        return false;
    }

private:
    SoRotationDragger* dragger = nullptr;
    SoRotationDraggerContainer* draggerContainer = nullptr;
    SoFieldSensor translationSensor;
    LinearGizmo* linearGizmo = nullptr;
    QMetaObject::Connection quantityChangedConnection;
    QMetaObject::Connection formulaDialogConnection;
    double lastDragOffset = 0.0;
    bool hasDragged = false;
    ClickCallback clickCallback;

    void draggingStarted();
    void draggingFinished();
    void draggingContinued();
    static void translationSensorCB(void* data, SoSensor* sensor);

    using inherited = Gizmo;
};

class GuiExport DirectedRotationGizmo: public RotationGizmo
{
public:
    DirectedRotationGizmo(QuantitySpinBox* property);

    SoInteractionKit* initDragger() override;

    void flipArrow();

private:
    using inherited = RotationGizmo;
};

class GuiExport RadialGizmo: public RotationGizmo
{
public:
    RadialGizmo(QuantitySpinBox* property);

    SoInteractionKit* initDragger() override;

    void updateColorTheme();

    void setRadius(float radius);
    void flipArrow();

protected:
    bool hasGuideGeometry() const override
    {
        return true;
    }

private:
    using inherited = RotationGizmo;
};

class GuiExport GizmoContainer: public SoBaseKit
{
    SO_KIT_HEADER(GizmoContainer);
    SO_KIT_CATALOG_ENTRY_HEADER(annotation);
    SO_KIT_CATALOG_ENTRY_HEADER(pickStyle);
    SO_KIT_CATALOG_ENTRY_HEADER(toggleSwitch);
    SO_KIT_CATALOG_ENTRY_HEADER(geometry);

public:
    static void initClass();
    GizmoContainer();
    ~GizmoContainer() override;

    SoSFBool visible;

    void initGizmos();
    void uninitGizmos();

    template<typename T = Gizmo>
    T* getGizmo(int index)
    {
        assert(index >= 0 && index < static_cast<int>(gizmos.size()) && "index out of range!");
        return dynamic_cast<T*>(gizmos[index]);
    }
    // This should be called only once after construction
    void addGizmos(std::initializer_list<Gui::Gizmo*> gizmos);
    void attachViewer(Gui::View3DInventorViewer* viewer, Base::Placement& origin);
    void setUpAutoScale(SoCamera* cameraIn);
    void calculateScaleAndOrientation();

    // Checks if the gizmos are enabled in the preferences
    static bool isEnabled();
    // Checks if coarse snapping is enabled in the preferences
    static bool isCoarseSnapEnabled();
    // Returns the modifier key used for fine snapping (Shift or Ctrl)
    static Qt::KeyboardModifier getFineSnapModifier();
    // Returns the InputHint key for the fine snap modifier
    static InputHint::UserInput getFineSnapKey();
    // Returns true when coarse dragging is the default behavior
    static bool isCoarseByDefault();
    // Checks if gizmo values are shown in the 3D view in the preferences
    static bool isValueLabelsEnabled();

    /// Shows the value labels of the gizmos that are shown; a box that newly appears
    /// takes the keyboard if it is in the 3D view
    void refreshValueLabels();
    /// Makes the value labels again, e.g. after a gizmo was bound to another field
    void rebuildValueLabels();
    /// Gives the keyboard to the first shown value box, unconditionally - what happens when
    /// the panel first opens, and what a pick that just ended must also do, since it holds
    /// the keyboard in its own field for as long as it lasts
    void focusFirstValueLabel();

    static std::unique_ptr<GizmoContainer> create(
        std::initializer_list<Gui::Gizmo*> gizmos,
        ViewProviderDragger* vp
    );

private:
    std::vector<Gizmo*> gizmos;
    SoFieldSensor cameraSensor;
    SoFieldSensor cameraPositionSensor;
    WeakPtrT<ViewProviderDragger> viewProvider;
    std::unique_ptr<QObject> labelContext;
    std::vector<std::unique_ptr<GizmoValueLabel>> valueLabels;
    QPointer<View3DInventorViewer> labelViewer;
    Base::Placement labelOrigin;
    SoFieldSensor visibleSensor;
    bool firstFocusDone = false;

    void addGizmo(Gizmo* gizmo);
    void createValueLabels();
    void removeValueLabels();
    /// Every shown gizmo's boxes in Tab order: its value, then its count
    std::vector<std::pair<Gizmo*, GizmoValueLabel*>> labelsInOrder() const;
    void connectLabel(GizmoValueLabel* label);
    void focusNextValueLabel(GizmoValueLabel* from, bool backwards);
    bool isKeyboardOnView() const;

    static void visibleChangedCallback(void* data, SoSensor*);

    static void cameraChangeCallback(void* data, SoSensor*);
    static void cameraPositionChangeCallback(void* data, SoSensor*);
};

}  // namespace Gui
