// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2024 The FreeCAD Project Association AISBL               *
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

#include "FileCardView.h"

#include <App/Application.h>
#include "../App/DisplayedFilesModel.h"
#include <algorithm>

namespace StartGui
{

FileCardView::FileCardView(QWidget* parent)
    : QListView(parent)
{
    // Expanding rather than MinimumExpanding, so the grid may be narrower than its one-row
    // size hint and wraps instead, see minimumSizeHint()
    QSizePolicy sizePolicy(QSizePolicy::Policy::Expanding, QSizePolicy::Policy::MinimumExpanding);
    sizePolicy.setHeightForWidth(true);
    setSizePolicy(sizePolicy);
    setHorizontalScrollBarPolicy(Qt::ScrollBarPolicy::ScrollBarAlwaysOff);
    setVerticalScrollBarPolicy(Qt::ScrollBarPolicy::ScrollBarAsNeeded);
    setViewMode(QListView::ViewMode::IconMode);
    setFlow(QListView::Flow::LeftToRight);
    setResizeMode(QListView::ResizeMode::Adjust);
    setUniformItemSizes(true);
    setMouseTracking(true);
    // A card opens its file on click, so there is no selection to show afterwards
    setSelectionMode(QAbstractItemView::NoSelection);
    setFocusPolicy(Qt::NoFocus);
    setFrameShape(QFrame::NoFrame);
    viewport()->setAutoFillBackground(false);
    viewport()->setCursor(Qt::PointingHandCursor);

    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    m_cardSpacing = static_cast<int>(hGrp->GetInt("FileCardSpacing", 16));  // NOLINT

    setSpacing(m_cardSpacing);
}

QColor FileCardView::cardColor() const
{
    return m_cardColor.isValid() ? m_cardColor : palette().color(QPalette::Base);
}

QColor FileCardView::wellColor() const
{
    return m_wellColor.isValid() ? m_wellColor : palette().color(QPalette::Window).darker(108);
}

QColor FileCardView::borderColor() const
{
    return m_borderColor.isValid() ? m_borderColor : palette().color(QPalette::Mid);
}

QColor FileCardView::accentColor() const
{
    return m_accentColor.isValid() ? m_accentColor : palette().color(QPalette::Highlight);
}

QColor FileCardView::mutedTextColor() const
{
    return m_mutedTextColor.isValid() ? m_mutedTextColor : palette().color(QPalette::PlaceholderText);
}

void FileCardView::setCardColor(const QColor& color)
{
    m_cardColor = color;
    viewport()->update();
}

void FileCardView::setWellColor(const QColor& color)
{
    m_wellColor = color;
    viewport()->update();
}

void FileCardView::setBorderColor(const QColor& color)
{
    m_borderColor = color;
    viewport()->update();
}

void FileCardView::setAccentColor(const QColor& color)
{
    m_accentColor = color;
    viewport()->update();
}

void FileCardView::setMutedTextColor(const QColor& color)
{
    m_mutedTextColor = color;
    viewport()->update();
}

int FileCardView::heightForWidth(int width) const
{
    auto model = this->model();
    auto delegate = this->itemDelegate();
    if (!model || !delegate) {
        return 0;
    }
    int numCards = model->rowCount();
    auto cardSize = delegate->sizeHint(QStyleOptionViewItem(), model->index(0, 0));
    // The view keeps a spacing before the first card and after every card
    int cardsPerRow
        = std::max(1, static_cast<int>((width - m_cardSpacing) / (cardSize.width() + m_cardSpacing)));
    int numRows = static_cast<int>(
        ceil(static_cast<double>(numCards) / static_cast<double>(cardsPerRow))
    );
    int neededHeight = numRows * cardSize.height();
    constexpr int extra = 4;  // avoid tiny scrollbars
    return neededHeight + m_cardSpacing * (numRows - 1) + 2 * m_cardSpacing + extra;
}

QSize FileCardView::sizeHint() const
{
    auto model = this->model();
    auto delegate = this->itemDelegate();
    if (!model || !delegate) {
        // The model and/or delegate have not been set yet, this was an early startup call
        return {m_cardSpacing, m_cardSpacing};
    }
    int numCards = model->rowCount();
    auto cardSize = delegate->sizeHint(QStyleOptionViewItem(), model->index(0, 0));
    return {
        (cardSize.width() + m_cardSpacing) * numCards + m_cardSpacing,
        cardSize.height() + 2 * m_cardSpacing
    };
}

QSize FileCardView::minimumSizeHint() const
{
    // One card wide: any narrower and the grid wraps onto more rows instead
    auto model = this->model();
    auto delegate = this->itemDelegate();
    if (!model || !delegate) {
        return {m_cardSpacing, m_cardSpacing};
    }
    auto cardSize = delegate->sizeHint(QStyleOptionViewItem(), model->index(0, 0));
    return {cardSize.width() + 2 * m_cardSpacing, cardSize.height() + 2 * m_cardSpacing};
}

}  // namespace StartGui
