// SPDX-License-Identifier: LGPL-2.1-or-later

/**************************************************************************
 *   Copyright (c) 2026 FreeCAD contributors                               *
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
 ***************************************************************************/

#include <QApplication>
#include <QLabel>
#include <QTimer>
#include <QVBoxLayout>

#include <Inventor/events/SoKeyboardEvent.h>
#include <Inventor/nodes/SoEventCallback.h>

#include <App/Application.h>
#include <App/Datums.h>
#include <App/Document.h>
#include <Base/Exception.h>
#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/InputHint.h>
#include <Gui/MainWindow.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>
#include <Mod/Part/App/Part2DObject.h>
#include <Mod/PartDesign/App/Body.h>

#include "SketchPlanePicker.h"
#include "ReferenceSelection.h"

using namespace PartDesignGui;

namespace
{

/// Lets through only what a FlatFace sketch can sit on: planar faces, datum planes
/// and the origin planes of the body the sketch is going into.
class SketchPlaneGate: public ReferenceSelection
{
public:
    explicit SketchPlaneGate(PartDesign::Body* body)
        : ReferenceSelection(nullptr, planarFaces())
        , body(body)
    {}

    bool allow(App::Document* document, App::DocumentObject* object, const char* subName) override
    {
        if (!object || !body || document != body->getDocument()) {
            return false;
        }
        // ReferenceSelection treats a sketch as a face, but nothing is sketched on a
        // sketch here: that route needs the attachment editor.
        if (object->isDerivedFrom<Part::Part2DObject>()) {
            return false;
        }
        if (object->isDerivedFrom<App::DatumElement>()) {
            return object->isDerivedFrom<App::Plane>() && body->hasObject(object, true);
        }
        return ReferenceSelection::allow(document, object, subName);
    }

private:
    static AllowSelectionFlags planarFaces()
    {
        AllowSelectionFlags flags;
        flags.setFlag(AllowSelection::FACE);
        flags.setFlag(AllowSelection::PLANAR);
        flags.setFlag(AllowSelection::OTHERBODY);
        return flags;
    }

    PartDesign::Body* body;
};

Gui::View3DInventorViewer* viewerOf(App::Document* document)
{
    if (auto* guiDocument = Gui::Application::Instance->getDocument(document)) {
        if (auto* view = dynamic_cast<Gui::View3DInventor*>(guiDocument->getActiveView())) {
            return view->getViewer();
        }
    }
    if (auto* view = qobject_cast<Gui::View3DInventor*>(Gui::getMainWindow()->activeWindow())) {
        return view->getViewer();
    }
    return nullptr;
}

}  // namespace

TaskDlgWaitForPick::TaskDlgWaitForPick(
    PartDesign::Body* body,
    Options options,
    PickHandler onPick,
    DoneHandler onDone
)
    : Gui::TaskView::TaskDialog()
    , Gui::SelectionObserver(/* attach = */ false)
    , body(body)
    , options(std::move(options))
    , onPick(std::move(onPick))
    , onDone(std::move(onDone))
{
    setDocumentName(body->getDocument()->getName());
    setAutoCloseOnDeletedDocument(true);

    auto* panel = new QWidget();
    panel->setObjectName(this->options.panelName);
    panel->setWindowTitle(this->options.title);
    auto* layout = new QVBoxLayout(panel);
    auto* hint = new QLabel(this->options.panelText, panel);
    hint->setWordWrap(true);
    layout->addWidget(hint);
    addTaskBox(Gui::BitmapFactory().pixmap(this->options.pixmap), panel);
}

TaskDlgSketchPlanePick::TaskDlgSketchPlanePick(
    PartDesign::Body* body,
    PickHandler onPick,
    DoneHandler onDone
)
    : TaskDlgWaitForPick(
          body,
          Options {
              .title = tr("Create Sketch"),
              .pixmap = "Sketcher_NewSketch",
              .panelText = tr("Select a planar face, datum plane or origin plane to sketch on."),
              .hint = tr("select a face or plane"),
              .panelName = QStringLiteral("PartDesignGui__TaskSketchPlanePick"),
              .makeGate = [body]() -> Gui::SelectionGate* { return new SketchPlaneGate(body); },
          },
          std::move(onPick),
          std::move(onDone)
      )
{}

TaskDlgWaitForPick::~TaskDlgWaitForPick()
{
    // Nothing that happens while tidying up may schedule another pick.
    detachSelection();

    if (viewer) {
        viewer->removeEventCallback(
            SoKeyboardEvent::getClassTypeId(),
            &TaskDlgWaitForPick::handleKeyboardCB,
            this
        );
    }
    if (opened && options.makeGate) {
        Gui::Selection().rmvSelectionGate();
        if (auto* mainWindow = Gui::getMainWindow()) {
            mainWindow->hideHints();
        }
    }

    // Like TaskDlgAttacher, the follow-up runs from here: the dialog has already left
    // the task panel, so the editor that comes next is free to take it. A document on
    // its way out takes its pending command with it, so there is nothing to do then.
    // Nothing may leave a destructor: an exception here would end OtherCAD outright.
    if (onDone && !documentClosing) {
        try {
            onDone(picked);
        }
        catch (const Base::Exception& e) {
            e.reportException();
        }
        catch (...) {
        }
    }
}

void TaskDlgWaitForPick::open()
{
    opened = true;
    // Only a shown dialog listens: a pick must never act for a dialog the task panel
    // turned away.
    attachSelection();
    if (options.makeGate) {
        Gui::Selection().addSelectionGate(options.makeGate());
    }

    viewer = viewerOf(body->getDocument());
    if (viewer) {
        viewer->addEventCallback(
            SoKeyboardEvent::getClassTypeId(),
            &TaskDlgWaitForPick::handleKeyboardCB,
            this
        );
    }

    using enum Gui::InputHint::UserInput;
    Gui::getMainWindow()->showHints({
        {.message = QStringLiteral("%1 ") + options.hint, .sequences = {MouseLeft}},
        {.message = tr("%1 cancel"), .sequences = {KeyEscape}},
    });
}

bool TaskDlgWaitForPick::accept()
{
    // Only a successful pick accepts this dialog; there is no OK button.
    return picked != nullptr;
}

bool TaskDlgWaitForPick::reject()
{
    picked = nullptr;
    return true;
}

void TaskDlgWaitForPick::autoClosedOnDeletedDocument()
{
    documentClosing = true;
}

void TaskDlgWaitForPick::onSelectionChanged(const Gui::SelectionChanges& msg)
{
    if (msg.Type != Gui::SelectionChanges::AddSelection || pickScheduled) {
        return;
    }
    // Act on the selection once it has settled: what comes next clears the selection
    // again, which must not happen from inside this notification.
    pickScheduled = true;
    QTimer::singleShot(0, this, [this]() { tryPick(); });
}

void TaskDlgWaitForPick::tryPick()
{
    pickScheduled = false;
    App::DocumentObject* object = onPick ? onPick() : nullptr;
    if (!object) {
        // Not something this command works on: keep waiting for the next click.
        Gui::Selection().clearSelection();
        return;
    }

    picked = object;
    Gui::Control().accept(body->getDocument());
}

void TaskDlgWaitForPick::cancel()
{
    QPointer<TaskDlgWaitForPick> self(this);
    App::Document* document = body->getDocument();
    QTimer::singleShot(0, [self, document]() {
        Gui::TaskView::TaskDialog* active = Gui::Control().activeDialog(document);
        if (self && active == static_cast<Gui::TaskView::TaskDialog*>(self.data())) {
            Gui::Control().reject(document);
        }
    });
}

void TaskDlgWaitForPick::handleKeyboardCB(void* userdata, SoEventCallback* cb)
{
    auto* self = static_cast<TaskDlgWaitForPick*>(userdata);
    const SoEvent* ev = cb->getEvent();
    if (!ev || !ev->isOfType(SoKeyboardEvent::getClassTypeId())) {
        return;
    }
    const auto* ke = static_cast<const SoKeyboardEvent*>(ev);
    if (ke->getKey() != SoKeyboardEvent::ESCAPE) {
        return;
    }
    cb->setHandled();

    // Cancel on the release, and never while a mouse button is down: Coin can crash
    // when Esc interrupts a drag (see ViewProvider::eventCallback).
    if (ke->getState() != SoButtonEvent::UP || QApplication::mouseButtons() != Qt::NoButton) {
        return;
    }
    self->cancel();
}

#include "moc_SketchPlanePicker.cpp"
