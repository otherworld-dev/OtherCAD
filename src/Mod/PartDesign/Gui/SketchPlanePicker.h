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

#pragma once

#include <functional>
#include <memory>
#include <QPointer>
#include <QString>

#include <Gui/Selection/Selection.h>
#include <Gui/TaskView/TaskDialog.h>

class SoEventCallback;

namespace App
{
class Document;
class DocumentObject;
}  // namespace App
namespace Gui
{
class View3DInventorViewer;
}
namespace PartDesign
{
class Body;
}

namespace PartDesignGui
{

/**
 * Waits for one click in the 3D view, so that a command works the way Fusion's do:
 * click the command, click what it works on. Create Sketch waits for the surface to
 * sketch on, the profile commands for the region or face to build from.
 *
 * The dialog owns nothing but the wait. Acting on the selection and tidying up
 * afterwards belong to the caller, which hands them in as callbacks. A pick the
 * handler turns down leaves the dialog open, so the user can simply click something
 * else. Esc in the 3D view, the Cancel button and closing the document all end the
 * wait with nothing picked.
 */
class TaskDlgWaitForPick: public Gui::TaskView::TaskDialog, public Gui::SelectionObserver
{
    Q_OBJECT

public:
    /// Acts on the current selection; returns null to keep on picking.
    using PickHandler = std::function<App::DocumentObject*()>;
    /// Runs once the dialog has left the task panel; the object is null after a cancel.
    using DoneHandler = std::function<void(App::DocumentObject* picked)>;

    /// What the dialog says and lets through
    struct Options
    {
        QString title;
        const char* pixmap {nullptr};
        QString panelText;
        /// The status bar hint after the mouse button, such as "select a face or plane"
        QString hint;
        QString panelName;
        std::function<Gui::SelectionGate*()> makeGate;
    };

    TaskDlgWaitForPick(PartDesign::Body* body, Options options, PickHandler onPick, DoneHandler onDone);
    ~TaskDlgWaitForPick() override;

    void open() override;
    bool accept() override;
    bool reject() override;
    void autoClosedOnDeletedDocument() override;

    QDialogButtonBox::StandardButtons getStandardButtons() const override
    {
        return QDialogButtonBox::Cancel;
    }
    bool isAllowedAlterDocument() const override
    {
        return false;
    }

    void onSelectionChanged(const Gui::SelectionChanges& msg) override;

private:
    void tryPick();
    void cancel();
    static void handleKeyboardCB(void* userdata, SoEventCallback* cb);

    PartDesign::Body* body;
    Options options;
    PickHandler onPick;
    DoneHandler onDone;
    App::DocumentObject* picked {nullptr};
    bool opened {false};
    bool pickScheduled {false};
    bool documentClosing {false};
    QPointer<Gui::View3DInventorViewer> viewer;
};

/// Create Sketch's wait: one click on a planar face, datum plane or origin plane
class TaskDlgSketchPlanePick: public TaskDlgWaitForPick
{
    Q_OBJECT

public:
    TaskDlgSketchPlanePick(PartDesign::Body* body, PickHandler onPick, DoneHandler onDone);
};

}  // namespace PartDesignGui
