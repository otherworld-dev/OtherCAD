// SPDX-License-Identifier: LGPL-2.1-or-later

#include <QApplication>
#include <QLabel>
#include <QTimer>
#include <QVBoxLayout>

#include <Inventor/events/SoKeyboardEvent.h>
#include <Inventor/nodes/SoEventCallback.h>

#include <App/Document.h>
#include <Base/Exception.h>
#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/InputHint.h>
#include <Gui/MainWindow.h>
#include <Gui/Selection/SelectionFilter.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>
#include <Mod/PartDesign/App/Body.h>
#include <Mod/PartDesign/App/FeatureAddSub.h>

#include "PatternFeaturePicker.h"

using namespace PartDesignGui;

PatternFeatureGate::PatternFeatureGate(PartDesign::Body* body)
    : Gui::SelectionFilterGate(nullPointer())
    , body(body)
{}

bool PatternFeatureGate::allow(App::Document* document, App::DocumentObject* object, const char*)
{
    return object && body && document == body->getDocument()
        && object->isDerivedFrom<PartDesign::FeatureAddSub>() && body->hasObject(object);
}

namespace
{

Gui::View3DInventorViewer* viewerOf(App::Document* document)
{
    if (auto* guiDocument = Gui::Application::Instance->getDocument(document)) {
        if (auto* view = dynamic_cast<Gui::View3DInventor*>(guiDocument->getActiveView())) {
            return view->getViewer();
        }
    }
    return nullptr;
}

}  // namespace

TaskDlgPatternFeaturePick::TaskDlgPatternFeaturePick(
    PartDesign::Body* body,
    const QString& title,
    const char* iconName,
    DoneHandler onDone
)
    : Gui::TaskView::TaskDialog()
    , Gui::SelectionObserver(/* attach = */ false)
    , body(body)
    , onDone(std::move(onDone))
{
    setDocumentName(body->getDocument()->getName());
    setAutoCloseOnDeletedDocument(true);

    auto* panel = new QWidget();
    panel->setObjectName(QStringLiteral("PartDesignGui__TaskPatternFeaturePick"));
    panel->setWindowTitle(title);
    auto* layout = new QVBoxLayout(panel);
    auto* hint = new QLabel(tr("Click the feature to copy."), panel);
    hint->setWordWrap(true);
    layout->addWidget(hint);
    addTaskBox(Gui::BitmapFactory().pixmap(iconName), panel);
}

TaskDlgPatternFeaturePick::~TaskDlgPatternFeaturePick()
{
    detachSelection();
    if (viewer) {
        viewer->removeEventCallback(
            SoKeyboardEvent::getClassTypeId(),
            &TaskDlgPatternFeaturePick::handleKeyboardCB,
            this
        );
    }
    if (opened) {
        Gui::Selection().rmvSelectionGate();
        if (auto* mainWindow = Gui::getMainWindow()) {
            mainWindow->hideHints();
        }
    }
    // The dialog has left the task panel, so the pattern's own panel is free to open.
    // Nothing may leave a destructor: an exception here would end OtherCAD outright.
    if (onDone && !documentClosing) {
        try {
            onDone(feature);
        }
        catch (const Base::Exception& e) {
            e.reportException();
        }
        catch (...) {
        }
    }
}

void TaskDlgPatternFeaturePick::open()
{
    opened = true;
    attachSelection();
    Gui::Selection().clearSelection();
    Gui::Selection().addSelectionGate(new PatternFeatureGate(body));

    viewer = viewerOf(body->getDocument());
    if (viewer) {
        viewer->addEventCallback(
            SoKeyboardEvent::getClassTypeId(),
            &TaskDlgPatternFeaturePick::handleKeyboardCB,
            this
        );
    }

    using enum Gui::InputHint::UserInput;
    Gui::getMainWindow()->showHints({
        {.message = tr("%1 select the feature to copy"), .sequences = {MouseLeft}},
        {.message = tr("%1 cancel"), .sequences = {KeyEscape}},
    });
}

bool TaskDlgPatternFeaturePick::accept()
{
    return feature != nullptr;
}

bool TaskDlgPatternFeaturePick::reject()
{
    feature = nullptr;
    return true;
}

void TaskDlgPatternFeaturePick::autoClosedOnDeletedDocument()
{
    documentClosing = true;
}

void TaskDlgPatternFeaturePick::onSelectionChanged(const Gui::SelectionChanges& msg)
{
    if (msg.Type != Gui::SelectionChanges::AddSelection || pickScheduled) {
        return;
    }
    // Opening the pattern clears the selection, which must not happen inside this notification
    pickScheduled = true;
    QTimer::singleShot(0, this, [this]() { tryPick(); });
}

void TaskDlgPatternFeaturePick::tryPick()
{
    pickScheduled = false;
    for (App::DocumentObject* obj :
         Gui::Selection().getObjectsOfType(PartDesign::FeatureAddSub::getClassTypeId(),
                                           body->getDocument()->getName())) {
        if (body->hasObject(obj)) {
            feature = obj;
            Gui::Control().accept(body->getDocument());
            return;
        }
    }
    Gui::Selection().clearSelection();
}

void TaskDlgPatternFeaturePick::cancel()
{
    QPointer<TaskDlgPatternFeaturePick> self(this);
    App::Document* document = body->getDocument();
    QTimer::singleShot(0, [self, document]() {
        Gui::TaskView::TaskDialog* active = Gui::Control().activeDialog(document);
        if (self && active == static_cast<Gui::TaskView::TaskDialog*>(self.data())) {
            Gui::Control().reject(document);
        }
    });
}

void TaskDlgPatternFeaturePick::handleKeyboardCB(void* userdata, SoEventCallback* cb)
{
    auto* self = static_cast<TaskDlgPatternFeaturePick*>(userdata);
    const SoEvent* ev = cb->getEvent();
    if (!ev || !ev->isOfType(SoKeyboardEvent::getClassTypeId())) {
        return;
    }
    const auto* ke = static_cast<const SoKeyboardEvent*>(ev);
    if (ke->getKey() != SoKeyboardEvent::ESCAPE) {
        return;
    }
    cb->setHandled();
    // On the release, and never mid-drag: Coin can crash when Esc interrupts a drag
    if (ke->getState() != SoButtonEvent::UP || QApplication::mouseButtons() != Qt::NoButton) {
        return;
    }
    self->cancel();
}

#include "moc_PatternFeaturePicker.cpp"
