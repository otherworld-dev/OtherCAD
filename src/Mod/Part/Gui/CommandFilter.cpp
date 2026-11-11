// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2002 Jürgen Riegel <juergen.riegel@web.de>              *
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


#include <QAction>
#include <QApplication>


#include <Gui/Action.h>
#include <Gui/BitmapFactory.h>
#include <Gui/Command.h>
#include <Gui/MainWindow.h>
#include <Gui/View3DInventor.h>

//===============================================================================
// PartCmdSelectFilter (dropdown toolbar button for Vertex, Edge & Face Selection)
//===============================================================================

DEF_STD_CMD_ACL(PartCmdSelectFilter)

PartCmdSelectFilter::PartCmdSelectFilter()
    : Command("Part_SelectFilter")
{
    sGroup = "Standard-View";
    sMenuText = QT_TR_NOOP("Selection Filter");
    sToolTipText = QT_TR_NOOP("Changes the selection filter");
    sStatusTip = sToolTipText;
    sWhatsThis = "Part_SelectFilter";
    sPixmap = "clear-selection";
    eType = Alter3DView;
}

void PartCmdSelectFilter::activated(int iMsg)
{
    Gui::CommandManager& rcCmdMgr = Gui::Application::Instance->commandManager();
    if (iMsg == 0) {
        rcCmdMgr.runCommandByName("Part_VertexSelection");
    }
    else if (iMsg == 1) {
        rcCmdMgr.runCommandByName("Part_EdgeSelection");
    }
    else if (iMsg == 2) {
        rcCmdMgr.runCommandByName("Part_FaceSelection");
    }
    else if (iMsg == 3) {
        rcCmdMgr.runCommandByName("Part_RemoveSelectionGate");
    }
    else {
        return;
    }

    // Since the default icon is reset when enabling/disabling the command we have
    // to explicitly set the icon of the used command.
    auto pcAction = qobject_cast<Gui::ActionGroup*>(_pcAction);
    QList<QAction*> act = pcAction->actions();

    assert(iMsg < act.size());
    pcAction->setIcon(act[iMsg]->icon());
}

namespace
{
/// One entry of the selection-filter group, carrying the icon and the accelerator
/// of the command it stands for.
QAction* addFilterAction(Gui::ActionGroup* group, const char* command, const char* icon)
{
    QAction* action = group->addAction(QString());
    action->setIcon(Gui::BitmapFactory().iconFromTheme(icon));

    Gui::Command* cmd = Gui::Application::Instance->commandManager().getCommandByName(command);
    const char* accel = cmd ? cmd->getAccel() : nullptr;
    if (accel && *accel) {
        action->setShortcut(QKeySequence(QString::fromLatin1(accel)));
    }

    return action;
}
}  // namespace

Gui::Action* PartCmdSelectFilter::createAction()
{
    auto pcAction = new Gui::ActionGroup(this, Gui::getMainWindow());
    pcAction->setDropDownMenu(true);
    applyCommandData(this->className(), pcAction);

    // The four filters are only ever reached through this group - nothing else
    // puts them in a menu or a toolbar, so their own commands never build an
    // action - which means the accelerator that actually fires is the one set
    // here. Take it from the command rather than repeating the literal, so that
    // the two cannot drift apart the way they did while the chords still began
    // with the letters the Fusion tools now hold.
    addFilterAction(pcAction, "Part_VertexSelection", "vertex-selection");
    addFilterAction(pcAction, "Part_EdgeSelection", "edge-selection");
    addFilterAction(pcAction, "Part_FaceSelection", "face-selection");
    addFilterAction(pcAction, "Part_RemoveSelectionGate", "clear-selection");

    _pcAction = pcAction;
    languageChange();

    pcAction->setIcon(Gui::BitmapFactory().iconFromTheme("clear-selection"));
    int defaultId = 3;
    pcAction->setProperty("defaultAction", QVariant(defaultId));

    return pcAction;
}

void PartCmdSelectFilter::languageChange()
{
    Command::languageChange();

    if (!_pcAction) {
        return;
    }

    Gui::CommandManager& rcCmdMgr = Gui::Application::Instance->commandManager();

    auto pcAction = qobject_cast<Gui::ActionGroup*>(_pcAction);
    QList<QAction*> act = pcAction->actions();

    Gui::Command* vertexSelection = rcCmdMgr.getCommandByName("Part_VertexSelection");
    if (vertexSelection) {
        QAction* cmd0 = act[0];
        cmd0->setText(
            QApplication::translate("PartCmdVertexSelection", vertexSelection->getMenuText())
        );
        cmd0->setToolTip(Gui::Action::createToolTip(cmd0, vertexSelection));
        cmd0->setStatusTip(
            QApplication::translate("PartCmdVertexSelection", vertexSelection->getStatusTip())
        );
    }

    Gui::Command* edgeSelection = rcCmdMgr.getCommandByName("Part_EdgeSelection");
    if (edgeSelection) {
        QAction* cmd1 = act[1];
        cmd1->setText(QApplication::translate("PartCmdEdgeSelection", edgeSelection->getMenuText()));
        cmd1->setToolTip(Gui::Action::createToolTip(cmd1, edgeSelection));
        cmd1->setStatusTip(
            QApplication::translate("PartCmdEdgeSelection", edgeSelection->getStatusTip())
        );
    }

    Gui::Command* faceSelection = rcCmdMgr.getCommandByName("Part_FaceSelection");
    if (faceSelection) {
        QAction* cmd1 = act[2];
        cmd1->setText(QApplication::translate("PartCmdFaceSelection", faceSelection->getMenuText()));
        cmd1->setToolTip(Gui::Action::createToolTip(cmd1, faceSelection));
        cmd1->setStatusTip(
            QApplication::translate("PartCmdFaceSelection", faceSelection->getStatusTip())
        );
    }

    Gui::Command* removeSelection = rcCmdMgr.getCommandByName("Part_RemoveSelectionGate");
    if (removeSelection) {
        QAction* cmd2 = act[3];
        cmd2->setText(
            QApplication::translate("PartCmdRemoveSelectionGate", removeSelection->getMenuText())
        );
        cmd2->setToolTip(Gui::Action::createToolTip(cmd2, removeSelection));
        cmd2->setStatusTip(
            QApplication::translate("PartCmdRemoveSelectionGate", removeSelection->getStatusTip())
        );
    }
}

bool PartCmdSelectFilter::isActive()
{
    Gui::MDIView* view = Gui::getMainWindow()->activeWindow();
    return view && view->isDerivedFrom<Gui::View3DInventor>();
}


//===========================================================================
// Part_VertexSelection
//===========================================================================
DEF_3DV_CMD(PartCmdVertexSelection)

PartCmdVertexSelection::PartCmdVertexSelection()
    : Command("Part_VertexSelection")
{
    sGroup = "Standard-View";
    sMenuText = QT_TR_NOOP("Vertex Selection");
    sToolTipText = QT_TR_NOOP("Only allows the selection of vertices");
    sWhatsThis = "Part_VertexSelection";
    sStatusTip = sToolTipText;
    sPixmap = "vertex-selection";
    // The selection filters sit behind U rather than behind the shape letter they
    // name: X, E, F and C are Fusion tool letters now, and a Fusion letter fires its
    // own command at once instead of waiting for a chord that starts with it (see
    // Gui/DefaultShortcuts.cpp), so "X, S" and friends could never complete.
    sAccel = "U, V";
    eType = Alter3DView;
}

void PartCmdVertexSelection::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    doCommand(Command::Gui, "Gui.Selection.addSelectionGate('SELECT Part::Feature SUBELEMENT Vertex SELECT App::Link SUBELEMENT Vertex')");
}


//===========================================================================
// Part_EdgeSelection
//===========================================================================
DEF_3DV_CMD(PartCmdEdgeSelection)

PartCmdEdgeSelection::PartCmdEdgeSelection()
    : Command("Part_EdgeSelection")
{
    sGroup = "Standard-View";
    sMenuText = QT_TR_NOOP("Edge Selection");
    sToolTipText = QT_TR_NOOP("Only allows the selection of edges");
    sWhatsThis = "Part_EdgeSelection";
    sStatusTip = sToolTipText;
    sPixmap = "edge-selection";
    sAccel = "U, E";
    eType = Alter3DView;
}

void PartCmdEdgeSelection::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    doCommand(Command::Gui, "Gui.Selection.addSelectionGate('SELECT Part::Feature SUBELEMENT Edge SELECT App::Link SUBELEMENT Edge')");
}


//===========================================================================
// Part_FaceSelection
//===========================================================================
DEF_3DV_CMD(PartCmdFaceSelection)

PartCmdFaceSelection::PartCmdFaceSelection()
    : Command("Part_FaceSelection")
{
    sGroup = "Standard-View";
    sMenuText = QT_TR_NOOP("Face Selection");
    sToolTipText = QT_TR_NOOP("Only allows the selection of faces");
    sWhatsThis = "Part_FaceSelection";
    sStatusTip = sToolTipText;
    sPixmap = "face-selection";
    sAccel = "U, F";
    eType = Alter3DView;
}

void PartCmdFaceSelection::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    doCommand(
        Command::Gui,
        "Gui.Selection.addSelectionGate('SELECT Part::Feature SUBELEMENT Face "
        "SELECT App::Link SUBELEMENT Face "
        "SELECT Part::Part2DObject SUBELEMENT InternalFace')"
    );
}


//===========================================================================
// Part_RemoveSelectionGate
//===========================================================================
DEF_3DV_CMD(PartCmdRemoveSelectionGate)

PartCmdRemoveSelectionGate::PartCmdRemoveSelectionGate()
    : Command("Part_RemoveSelectionGate")
{
    sGroup = "Standard-View";
    sMenuText = QT_TR_NOOP("No Selection Filters");
    sToolTipText = QT_TR_NOOP("Clears all selection filters");
    sWhatsThis = "Part_RemoveSelectionGate";
    sStatusTip = sToolTipText;
    sPixmap = "clear-selection";
    sAccel = "U, C";
    eType = Alter3DView;
}

void PartCmdRemoveSelectionGate::activated(int iMsg)
{
    Q_UNUSED(iMsg);
    doCommand(Command::Gui, "Gui.Selection.removeSelectionGate()");
}

void CreatePartSelectCommands()
{
    Gui::CommandManager& rcCmdMgr = Gui::Application::Instance->commandManager();
    // NOLINTBEGIN
    rcCmdMgr.addCommand(new PartCmdSelectFilter());
    rcCmdMgr.addCommand(new PartCmdVertexSelection());
    rcCmdMgr.addCommand(new PartCmdEdgeSelection());
    rcCmdMgr.addCommand(new PartCmdFaceSelection());
    rcCmdMgr.addCommand(new PartCmdRemoveSelectionGate());
    // NOLINTEND
}
