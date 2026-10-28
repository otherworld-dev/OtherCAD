// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2025 Alfredo Monclus <alfredomonclus@gmail.com>          *
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

#include <QLabel>
#include <QFont>
#include <QIcon>
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QString>

#include "NewFileButton.h"
#include <algorithm>

namespace StartGui
{

NewFileButton::NewFileButton(const NewButton& newButton)
    : mainLayout(new QHBoxLayout(this))
    , textLayout(new QVBoxLayout())
    , headingLabel(new QLabel())
    , descriptionLabel(new QLabel())
{
    // A row in the start page sidebar: icon, name and a one-line description. The
    // stylesheet gives the row its hover background, see #newFileButton in the QSS.
    setObjectName(QStringLiteral("newFileButton"));
    setFlat(true);
    setCursor(Qt::PointingHandCursor);
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );

    constexpr int defaultSize = 28;
    iconSize = int(hGrp->GetInt("NewFileIconSize", defaultSize));

    auto iconLabel = new QLabel(this);
    iconLabel->setObjectName(QStringLiteral("newFileButtonIcon"));
    QIcon baseIcon(newButton.iconPath);
    iconLabel->setPixmap(baseIcon.pixmap(iconSize, iconSize));
    iconLabel->setFixedSize(iconSize, iconSize);

    textLayout->addWidget(headingLabel);
    textLayout->addWidget(descriptionLabel);
    textLayout->setSpacing(0);
    textLayout->setContentsMargins(0, 0, 0, 0);

    headingLabel->setObjectName(QStringLiteral("newFileButtonHeading"));
    headingLabel->setText(newButton.heading);

    descriptionLabel->setObjectName(QStringLiteral("newFileButtonDescription"));
    descriptionLabel->setText(newButton.description);
    QFont small = descriptionLabel->font();
    small.setPointSizeF(small.pointSizeF() * 0.9);
    descriptionLabel->setFont(small);
    QPalette muted = descriptionLabel->palette();
    muted.setColor(QPalette::WindowText, muted.color(QPalette::PlaceholderText));
    descriptionLabel->setPalette(muted);

    for (auto label : {iconLabel, headingLabel, descriptionLabel}) {
        // Clicks go to the button underneath
        label->setAttribute(Qt::WA_TransparentForMouseEvents);
    }

    QFontMetrics qfm(font());
    int margin = qfm.height() / 2;
    mainLayout->setAlignment(Qt::AlignVCenter);
    mainLayout->addWidget(iconLabel);
    mainLayout->addLayout(textLayout, 1);
    mainLayout->setSpacing(margin + margin / 2);
    mainLayout->setContentsMargins(margin, margin / 2 + 1, margin, margin / 2 + 1);
    setLayout(mainLayout);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);
}

QSize NewFileButton::sizeHint() const
{
    return minimumSizeHint();
}

QSize NewFileButton::minimumSizeHint() const
{
    const auto margins = mainLayout->contentsMargins();
    int textWidth = std::max(headingLabel->sizeHint().width(), descriptionLabel->sizeHint().width());
    int minWidth = iconSize + mainLayout->spacing() + textWidth + margins.left() + margins.right();

    int textHeight = headingLabel->sizeHint().height() + descriptionLabel->sizeHint().height();
    int minHeight = std::max(iconSize, textHeight) + margins.top() + margins.bottom();

    return {minWidth, minHeight};
}

}  // namespace StartGui
