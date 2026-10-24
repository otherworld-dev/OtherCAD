/***************************************************************************
 *   Copyright (c) 2026 FuCad contributors                                 *
 *                                                                         *
 *   This file is part of FreeCAD.                                         *
 *                                                                         *
 *   FreeCAD is free software: you can redistribute it and/or modify it    *
 *   under the terms of the GNU Lesser General Public License as           *
 *   published by the Free Software Foundation, either version 2.1 of the  *
 *   License, or (at your option) any later version.                       *
 *                                                                         *
 *   FreeCAD is distributed in the hope that it will be useful, but        *
 *   WITHOUT ANY WARRANTY; without even the implied warranty of            *
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU      *
 *   Lesser General Public License for more details.                       *
 *                                                                         *
 *   You should have received a copy of the GNU Lesser General Public      *
 *   License along with FreeCAD. If not, see                               *
 *   <https://www.gnu.org/licenses/>.                                      *
 *                                                                         *
 ***************************************************************************/


#include <QAction>
#include <QActionEvent>
#include <QApplication>
#include <QByteArray>
#include <QDrag>
#include <QEvent>
#include <QMimeData>
#include <QMouseEvent>
#include <QPixmap>
#include <QSize>

#include "RibbonPanelMenu.h"


using namespace Gui::Ribbon;

namespace
{
const char* const ribbonMimeType = "application/x-othercad-ribbon-command";
// Set on any QAction that a drag may pick up; see RibbonPanelMenu::tagCommand.
const char* const commandProperty = "ribbonCommand";
constexpr int dragPixmapExtent = 24;
}  // namespace


const char* RibbonPanelMenu::mimeType()
{
    return ribbonMimeType;
}

QMimeData* RibbonPanelMenu::createMimeData(const QString& panelKey, const QString& command)
{
    auto* data = new QMimeData();
    data->setData(
        QString::fromLatin1(ribbonMimeType),
        (panelKey + QLatin1Char('\n') + command).toUtf8()
    );
    return data;
}

bool RibbonPanelMenu::readMimeData(const QMimeData* data, QString& panelKey, QString& command)
{
    if (!data || !data->hasFormat(QString::fromLatin1(ribbonMimeType))) {
        return false;
    }

    const QString payload = QString::fromUtf8(data->data(QString::fromLatin1(ribbonMimeType)));
    const qsizetype split = payload.indexOf(QLatin1Char('\n'));
    if (split < 0) {
        return false;
    }

    panelKey = payload.left(split);
    command = payload.mid(split + 1);
    return !panelKey.isEmpty() && !command.isEmpty();
}

void RibbonPanelMenu::tagCommand(QAction* action, const QString& command)
{
    if (action && !command.isEmpty()) {
        action->setProperty(commandProperty, command);
    }
}

QString RibbonPanelMenu::commandOf(const QAction* action)
{
    return action ? action->property(commandProperty).toString() : QString();
}

QAction* RibbonPanelMenu::createProxyAction(QAction* source, const QString& label, QObject* parent)
{
    auto* proxy = new QAction(source->icon(), label, parent);
    proxy->setToolTip(source->toolTip());
    proxy->setStatusTip(source->statusTip());
    proxy->setWhatsThis(source->whatsThis());
    proxy->setCheckable(source->isCheckable());
    proxy->setChecked(source->isChecked());
    proxy->setEnabled(source->isEnabled());

    QObject::connect(proxy, &QAction::triggered, source, [source]() { source->trigger(); });
    QObject::connect(source, &QAction::changed, proxy, [proxy, source]() {
        proxy->setIcon(source->icon());
        proxy->setEnabled(source->isEnabled());
        proxy->setChecked(source->isChecked());
    });

    return proxy;
}

RibbonPanelMenu::RibbonPanelMenu(const QString& panelKey, QWidget* parent)
    : QMenu(parent)
    , panelKey(panelKey)
    , root(this)
{
    setObjectName(QStringLiteral("RibbonPanelMenu"));
}

RibbonPanelMenu::RibbonPanelMenu(const QString& panelKey, RibbonPanelMenu* root, const QString& title)
    : QMenu(title, root)
    , panelKey(panelKey)
    , root(root)
{
    setObjectName(QStringLiteral("RibbonPanelMenu"));
}

RibbonPanelMenu* RibbonPanelMenu::addSubmenu(const QString& title)
{
    auto* submenu = new RibbonPanelMenu(panelKey, root ? root.data() : this, title);
    addMenu(submenu);
    return submenu;
}

RibbonPanelMenu* RibbonPanelMenu::insertSubmenu(QAction* before, const QString& title)
{
    auto* submenu = new RibbonPanelMenu(panelKey, root ? root.data() : this, title);
    insertMenu(before, submenu);
    return submenu;
}

void RibbonPanelMenu::actionEvent(QActionEvent* event)
{
    QMenu::actionEvent(event);

    if (event->type() == QEvent::ActionAdded || event->type() == QEvent::ActionRemoved) {
        Q_EMIT entriesChanged();
    }
}

void RibbonPanelMenu::mousePressEvent(QMouseEvent* event)
{
    pressedAction = nullptr;

    if (event->button() == Qt::LeftButton) {
        QAction* action = actionAt(event->position().toPoint());
        if (!commandOf(action).isEmpty()) {
            pressedAction = action;
            pressPosition = event->position().toPoint();
        }
    }

    QMenu::mousePressEvent(event);
}

void RibbonPanelMenu::mouseMoveEvent(QMouseEvent* event)
{
    if (!pressedAction.isNull() && (event->buttons() & Qt::LeftButton)
        && (event->position().toPoint() - pressPosition).manhattanLength()
            >= QApplication::startDragDistance()) {
        QAction* action = pressedAction.data();
        pressedAction = nullptr;
        startDrag(action);
        return;
    }

    QMenu::mouseMoveEvent(event);
}

void RibbonPanelMenu::mouseReleaseEvent(QMouseEvent* event)
{
    pressedAction = nullptr;
    QMenu::mouseReleaseEvent(event);
}

void RibbonPanelMenu::startDrag(QAction* action)
{
    // The drop-down hangs below the caption, so the row is not covered, but a
    // menu that stays open would swallow the release that ends the drag and
    // then sit there once the entry has become a button.
    if (root) {
        root->hide();
    }
    else {
        hide();
    }

    auto* drag = new QDrag(this);
    drag->setMimeData(createMimeData(panelKey, commandOf(action)));
    const QPixmap pixmap = action->icon().pixmap(QSize(dragPixmapExtent, dragPixmapExtent));
    if (!pixmap.isNull()) {
        drag->setPixmap(pixmap);
        drag->setHotSpot(pixmap.rect().center());
    }

    // The panel applies a drop only once exec() has returned: a page rebuilt
    // while the drag still runs would delete this menu under the drag.
    Q_EMIT dragStarted();
    // Something other than the drop may still rebuild the page under the
    // drag, which deletes this menu and, as its child, the drag.
    QPointer<RibbonPanelMenu> self(this);
    drag->exec(Qt::MoveAction);
    if (self) {
        drag->deleteLater();
        Q_EMIT dragFinished();
    }
}

#include "moc_RibbonPanelMenu.cpp"
