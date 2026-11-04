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


#include <QAbstractItemView>
#include <QEvent>
#include <QFont>
#include <QFrame>
#include <QHBoxLayout>
#include <QKeyEvent>
#include <QList>
#include <QMenu>
#include <QPainter>
#include <QPaintEvent>
#include <QSignalBlocker>
#include <QSize>
#include <QSizePolicy>
#include <QStackedWidget>
#include <QStyle>
#include <QTabBar>
#include <QToolButton>
#include <QVBoxLayout>

#include <Gui/MDIView.h>
#include <Gui/MainWindow.h>

#include "RibbonBar.h"
#include "WorkbenchSwitcher.h"
#include "RibbonPage.h"


using namespace Gui;
using namespace Gui::Ribbon;

namespace
{
// Matches Fusion: a tab strip over a page tall enough for a row of icon-only
// buttons, plus the panel caption underneath it.
constexpr int ribbonBarHeight = 86;
// Selected on by the stylesheet as QTabBar#RibbonTabBar[contextTab="true"].
constexpr const char* contextTabProperty = "contextTab";
// The workspace block keeps the side margin of a panel body so that the
// selector lines up with the buttons beside it.
constexpr int workspaceBlockSideMargin = 8;
constexpr int workspaceBlockVerticalMargin = 6;
constexpr int workspaceSelectorMinimumWidth = 180;
// The block names where the user is, so it reads a step larger than the
// captions under the panels.
constexpr int workspaceSelectorPointSizeDelta = 2;
constexpr int separatorWidth = 1;
// The small down arrow after the title, drawn rather than typed
constexpr int workspaceArrowWidth = 7;
constexpr int workspaceArrowGap = 8;

// The block's title with a small down arrow after it, which says the block opens something.
// The arrow used to be the character U+25BE, but the first geometric shape Qt lays out
// makes it query every fallback font on the system, which took about a second of startup.
class WorkspaceButton: public QToolButton
{
public:
    using QToolButton::QToolButton;

    QSize sizeHint() const override
    {
        QSize size = QToolButton::sizeHint();
        size.rwidth() += workspaceArrowGap + workspaceArrowWidth;
        return size;
    }

protected:
    void paintEvent(QPaintEvent* event) override
    {
        QToolButton::paintEvent(event);
        // just after the title, which the button centres
        const int textWidth = fontMetrics().horizontalAdvance(text());
        const qreal x = (width() + textWidth) / 2.0 + workspaceArrowGap;
        const qreal y = height() / 2.0 - workspaceArrowWidth / 4.0;
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);
        painter.setPen(Qt::NoPen);
        painter.setBrush(palette().color(QPalette::ButtonText));
        const QPointF points[3] = {
            {x, y},
            {x + workspaceArrowWidth, y},
            {x + workspaceArrowWidth / 2.0, y + workspaceArrowWidth / 2.0 + 1.0},
        };
        painter.drawPolygon(points, 3);
    }
};
}  // namespace


RibbonBar::RibbonBar(QWidget* parent)
    : QWidget(parent)
    , tabBar(nullptr)
    , pageStack(nullptr)
{
    setObjectName(QStringLiteral("RibbonBar"));
    setAttribute(Qt::WA_StyledBackground, true);
    setFixedHeight(ribbonBarHeight);
    setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Fixed);

    auto* layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    layout->setSpacing(0);

    tabBar = new QTabBar(this);
    tabBar->setObjectName(QStringLiteral("RibbonTabBar"));
    tabBar->setExpanding(false);
    tabBar->setDrawBase(false);
    tabBar->setUsesScrollButtons(true);
    tabBar->setElideMode(Qt::ElideNone);
    // Focus is all QTabBar needs to move between tabs with Left and Right; its
    // own keyPressEvent() does the rest.
    tabBar->setFocusPolicy(Qt::TabFocus);
    tabBar->setProperty(contextTabProperty, false);
    // The strip is the ribbon's one tab stop, and the arrow keys reach the rest
    // of the ribbon from it; see eventFilter().
    tabBar->installEventFilter(this);

    auto* pageRow = new QWidget(this);
    pageRow->setObjectName(QStringLiteral("RibbonPageRow"));
    pageRow->setAttribute(Qt::WA_StyledBackground, true);

    auto* rowLayout = new QHBoxLayout(pageRow);
    rowLayout->setContentsMargins(0, 0, 0, 0);
    rowLayout->setSpacing(0);

    pageStack = new QStackedWidget(pageRow);
    pageStack->setObjectName(QStringLiteral("RibbonPages"));
    pageStack->setFrameShape(QFrame::NoFrame);

    if (QWidget* workspaceBlock = createWorkspaceBlock(pageRow)) {
        rowLayout->addWidget(workspaceBlock, 0);
    }
    rowLayout->addWidget(pageStack, 1);

    layout->addWidget(tabBar, 0);
    layout->addWidget(pageRow, 1);

    connect(tabBar, &QTabBar::currentChanged, this, [this](int index) {
        if (index >= 0 && index < pageStack->count()) {
            pageStack->setCurrentIndex(index);
        }
        Q_EMIT tabActivated(index);
    });
}

bool RibbonBar::eventFilter(QObject* watched, QEvent* event)
{
    if (event->type() != QEvent::KeyPress) {
        return QWidget::eventFilter(watched, event);
    }

    const int key = static_cast<QKeyEvent*>(event)->key();

    if (watched == tabBar) {
        // Down steps from the strip onto the page it names, the way a menu bar
        // opens onto its menu.
        if (key == Qt::Key_Down && focusFirstPageButton()) {
            return true;
        }

        if (key == Qt::Key_Escape && focusActiveView()) {
            return true;
        }

        // Left and Right are QTabBar's own, and they are what moves between tabs.
        return QWidget::eventFilter(watched, event);
    }

    auto* button = qobject_cast<QToolButton*>(watched);
    if (!button) {
        return QWidget::eventFilter(watched, event);
    }

    switch (key) {
        case Qt::Key_Right:
            return focusAdjacentPageButton(button, 1);
        case Qt::Key_Left:
            return focusAdjacentPageButton(button, -1);
        case Qt::Key_Up:
            tabBar->setFocus(Qt::OtherFocusReason);
            return true;
        case Qt::Key_Down:
            // The drop-down of a split button is otherwise out of reach: a
            // click on such a button runs its command instead of opening it.
            if (button->menu()) {
                button->showMenu();
                return true;
            }
            return QWidget::eventFilter(watched, event);
        case Qt::Key_Return:
        case Qt::Key_Enter:
            // QAbstractButton answers Space but ignores Return. A click also
            // opens the menu of a button whose whole job is one, because
            // QToolButton pops an InstantPopup menu from pressed().
            button->click();
            return true;
        case Qt::Key_Escape:
            return focusActiveView();
        default:
            return QWidget::eventFilter(watched, event);
    }
}

QList<QToolButton*> RibbonBar::pageButtons() const
{
    // The page knows its panels, which of their buttons are on show, and
    // where its overflow button sits among them.
    auto* page = qobject_cast<RibbonPage*>(pageStack->currentWidget());
    return page ? page->keyboardButtons() : QList<QToolButton*> {};
}

bool RibbonBar::focusFirstPageButton()
{
    const QList<QToolButton*> buttons = pageButtons();
    if (buttons.isEmpty()) {
        return false;
    }

    buttons.first()->setFocus(Qt::OtherFocusReason);
    return true;
}

bool RibbonBar::focusAdjacentPageButton(QToolButton* from, int offset)
{
    const QList<QToolButton*> buttons = pageButtons();
    const qsizetype index = buttons.indexOf(from);
    if (index < 0) {
        return false;
    }

    // Wrapping keeps the arrows from dead-ending at either edge of the page.
    const qsizetype count = buttons.size();
    const qsizetype next = ((index + offset) % count + count) % count;
    buttons.at(next)->setFocus(Qt::OtherFocusReason);
    return true;
}

bool RibbonBar::focusActiveView()
{
    // Escape hands the keyboard back to the model, which is where the next key
    // belongs once the user is done with the ribbon. With no view open there is
    // nowhere to hand it to, and Esc is left to whoever else wants it.
    MainWindow* window = getMainWindow();
    QWidget* view = window ? window->activeWindow() : nullptr;
    if (!view) {
        return false;
    }

    view->setFocus(Qt::OtherFocusReason);
    return true;
}

QWidget* RibbonBar::createWorkspaceBlock(QWidget* parent)
{
    auto* block = new QWidget(parent);
    block->setObjectName(QStringLiteral("RibbonWorkspaceBlock"));
    block->setAttribute(Qt::WA_StyledBackground, true);

    auto* blockLayout = new QHBoxLayout(block);
    blockLayout->setContentsMargins(0, 0, 0, 0);
    blockLayout->setSpacing(0);

    workspaceButton = new WorkspaceButton(block);
    workspaceButton->setObjectName(QStringLiteral("RibbonWorkspaceSelector"));
    workspaceButton->setToolButtonStyle(Qt::ToolButtonTextOnly);
    workspaceButton->setAutoRaise(true);
    workspaceButton->setToolTip(tr("Switch workbench (Ctrl+Shift+W)"));
    // Sized for the longest title, so the block never shifts the panels when
    // the workbench changes.
    workspaceButton->setMinimumWidth(workspaceSelectorMinimumWidth);
    workspaceButton->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);

    QFont labelFont = workspaceButton->font();
    if (labelFont.pointSizeF() > 0.0) {
        labelFont.setPointSizeF(labelFont.pointSizeF() + workspaceSelectorPointSizeDelta);
        workspaceButton->setFont(labelFont);
    }

    connect(workspaceButton, &QToolButton::clicked, this, [this]() {
        showWorkbenchSwitcher();
    });

    auto* labelLayout = new QHBoxLayout();
    labelLayout->setContentsMargins(
        workspaceBlockSideMargin,
        workspaceBlockVerticalMargin,
        workspaceBlockSideMargin,
        workspaceBlockVerticalMargin
    );
    labelLayout->setSpacing(0);
    labelLayout->addWidget(workspaceButton);

    // The same rule a panel draws down its right edge, so the block reads as
    // the first panel of every page.
    auto* separator = new QWidget(block);
    separator->setObjectName(QStringLiteral("RibbonPanelSeparator"));
    separator->setAttribute(Qt::WA_StyledBackground, true);
    separator->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    separator->setFixedWidth(separatorWidth);

    blockLayout->addLayout(labelLayout);
    blockLayout->addWidget(separator);

    return block;
}

void RibbonBar::setWorkspaceTitle(const QString& title)
{
    if (workspaceButton != nullptr) {
        // The tab titles beside it are upper case, so the block matches them.
        // WorkspaceButton draws the small down arrow after it.
        workspaceButton->setText(title.toUpper());
    }
}

void RibbonBar::showWorkbenchSwitcher()
{
    WorkbenchSwitcher::instance()->popUp(workspaceButton);
}

void RibbonBar::clear()
{
    const QSignalBlocker blocker(tabBar);

    while (tabBar->count() > 0) {
        tabBar->removeTab(0);
    }

    while (pageStack->count() > 0) {
        QWidget* page = pageStack->widget(0);
        pageStack->removeWidget(page);
        delete page;
    }
}

int RibbonBar::addTab(const QString& title)
{
    const QSignalBlocker blocker(tabBar);

    const int index = tabBar->addTab(title);
    pageStack->insertWidget(index, new QWidget(pageStack));
    return index;
}

void RibbonBar::removeTab(int index)
{
    if (index < 0 || index >= tabBar->count()) {
        return;
    }

    const QSignalBlocker blocker(tabBar);

    tabBar->removeTab(index);

    if (index < pageStack->count()) {
        QWidget* page = pageStack->widget(index);
        pageStack->removeWidget(page);
        delete page;
    }
}

int RibbonBar::count() const
{
    return tabBar->count();
}

void RibbonBar::setContextTabPresent(bool present)
{
    if (tabBar->property(contextTabProperty).toBool() == present) {
        return;
    }

    tabBar->setProperty(contextTabProperty, present);

    // A rule that selects on a dynamic property is only re-evaluated once the
    // style is asked to look at the widget again.
    tabBar->style()->unpolish(tabBar);
    tabBar->style()->polish(tabBar);
    tabBar->update();
}

QString RibbonBar::tabText(int index) const
{
    return tabBar->tabText(index);
}

void RibbonBar::setPage(int index, QWidget* page)
{
    if (!page) {
        return;
    }

    if (index < 0 || index >= pageStack->count()) {
        delete page;
        return;
    }

    // None of the buttons is a tab stop of its own, so the bar has to answer
    // the arrow keys on their behalf; see eventFilter().
    for (QToolButton* button : page->findChildren<QToolButton*>()) {
        button->installEventFilter(this);
    }

    QWidget* previous = pageStack->widget(index);
    const bool wasCurrent = pageStack->currentIndex() == index;

    pageStack->insertWidget(index, page);
    pageStack->removeWidget(previous);
    delete previous;

    if (wasCurrent) {
        pageStack->setCurrentIndex(index);
    }
}

int RibbonBar::currentIndex() const
{
    return tabBar->currentIndex();
}

void RibbonBar::setCurrentIndex(int index)
{
    if (index < 0 || index >= tabBar->count()) {
        return;
    }

    tabBar->setCurrentIndex(index);
    pageStack->setCurrentIndex(index);
}

#include "moc_RibbonBar.cpp"
