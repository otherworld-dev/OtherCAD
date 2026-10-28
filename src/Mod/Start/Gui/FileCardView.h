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

#pragma once

#include <QColor>
#include <QListView>

namespace StartGui
{

/// A wrapping grid of file cards. The cards are painted by FileCardDelegate, so the stylesheet
/// hands over their colours as properties, see StartGui--FileCardView in the QSS. Any colour
/// left unset falls back to one taken from the palette.
class FileCardView: public QListView
{
    Q_OBJECT
    Q_PROPERTY(QColor cardColor READ cardColor WRITE setCardColor)
    Q_PROPERTY(QColor wellColor READ wellColor WRITE setWellColor)
    Q_PROPERTY(QColor borderColor READ borderColor WRITE setBorderColor)
    Q_PROPERTY(QColor accentColor READ accentColor WRITE setAccentColor)
    Q_PROPERTY(QColor mutedTextColor READ mutedTextColor WRITE setMutedTextColor)

public:
    explicit FileCardView(QWidget* parent = nullptr);

    int heightForWidth(int width) const override;

    QSize sizeHint() const override;
    QSize minimumSizeHint() const override;

    QColor cardColor() const;
    QColor wellColor() const;
    QColor borderColor() const;
    QColor accentColor() const;
    QColor mutedTextColor() const;
    void setCardColor(const QColor& color);
    void setWellColor(const QColor& color);
    void setBorderColor(const QColor& color);
    void setAccentColor(const QColor& color);
    void setMutedTextColor(const QColor& color);

private:
    int m_cardSpacing;
    QColor m_cardColor;
    QColor m_wellColor;
    QColor m_borderColor;
    QColor m_accentColor;
    QColor m_mutedTextColor;
};

}  // namespace StartGui
