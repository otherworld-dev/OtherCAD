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

#include <QDateTime>
#include <QFile>
#include <QFileIconProvider>
#include <QLocale>
#include <QPainterPath>
#include <QImageReader>
#include <QPainter>
#include <QStyleOptionViewItem>
#include <QLabel>
#include <QModelIndex>
#include <QVBoxLayout>
#include <QApplication>
#include <QPushButton>
#include <QString>
#include <QAbstractItemView>

#include "FileCardDelegate.h"
#include "FileCardView.h"
#include "../App/DisplayedFilesModel.h"
#include "App/Application.h"
#include <Base/Color.h>
#include <Base/Console.h>
#include <Gui/Application.h>
#include <Gui/MainWindow.h>

using namespace Start;

QCache<QString, QPixmap> FileCardDelegate::_thumbnailCache;

FileCardDelegate::FileCardDelegate(QObject* parent)
    : QStyledItemDelegate(parent)
{
    _parameterGroup = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    setObjectName(QStringLiteral("thumbnailWidget"));

    // Initialize cache size based on thumbnail size (only once)
    if (_thumbnailCache.maxCost() == 0) {
        int thumbnailSize = static_cast<int>(_parameterGroup->GetInt("FileThumbnailIconsSize", 128));
        int thumbnailMemory = thumbnailSize * thumbnailSize * 4;  // rgba
        int maxCacheItems = (CACHE_SIZE_MB * 1024 * 1024) / thumbnailMemory;
        _thumbnailCache.setMaxCost(maxCacheItems);
        Base::Console().log(
            "FileCardDelegate: Initialized thumbnail cache for %d items (%d MB)\n",
            maxCacheItems,
            CACHE_SIZE_MB
        );
    }
}

void FileCardDelegate::paint(
    QPainter* painter,
    const QStyleOptionViewItem& option,
    const QModelIndex& index
) const
{
    painter->save();
    painter->setRenderHint(QPainter::Antialiasing);
    painter->setRenderHint(QPainter::SmoothPixmapTransform);

    // Colours come from the view, which takes them from the stylesheet
    QColor cardColor = option.palette.color(QPalette::Base);
    QColor wellColor = option.palette.color(QPalette::Window).darker(108);
    QColor borderColor = option.palette.color(QPalette::Mid);
    QColor accentColor = option.palette.color(QPalette::Highlight);
    QColor mutedColor = option.palette.color(QPalette::PlaceholderText);
    if (auto view = qobject_cast<const StartGui::FileCardView*>(option.widget)) {
        cardColor = view->cardColor();
        wellColor = view->wellColor();
        borderColor = view->borderColor();
        accentColor = view->accentColor();
        mutedColor = view->mutedTextColor();
    }
    const bool hovered = (option.state & QStyle::State_MouseOver) != 0;

    // Card
    const QRectF card = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5);
    QPainterPath cardPath;
    cardPath.addRoundedRect(card, cardRadius, cardRadius);
    painter->fillPath(cardPath, cardColor);

    // Thumbnail well, the top of the card
    const int width = option.rect.width();
    const QRectF well(card.left(), card.top(), card.width(), width * 3.0 / 4.0);
    painter->save();
    QPainterPath wellPath;
    wellPath.addRect(well);
    painter->setClipPath(cardPath.intersected(wellPath));
    painter->fillRect(well, wellColor);

    auto image = index.data(static_cast<int>(DisplayedFilesModelRoles::image)).toByteArray();
    auto path = index.data(static_cast<int>(DisplayedFilesModelRoles::path)).toString();
    QPixmap pixmap;
    if (!image.isEmpty()) {
        pixmap.loadFromData(image);
    }
    if (!pixmap.isNull()) {
        // A real thumbnail fills the well, cropped to it, so its own background does not
        // sit as a pale square in the middle of the card
        QSizeF cover = QSizeF(pixmap.size()).scaled(well.size(), Qt::KeepAspectRatioByExpanding);
        QRectF target(QPointF(), cover);
        target.moveCenter(well.center());
        painter->drawPixmap(target, pixmap, QRectF(pixmap.rect()));
    }
    else {
        // An icon stands for a file with no thumbnail of its own
        pixmap = generateThumbnail(path);
        constexpr double iconShare = 0.42;
        const QSizeF iconSize = QSizeF(pixmap.size())
                                    .scaled(
                                        QSizeF(well.height() * iconShare, well.height() * iconShare),
                                        Qt::KeepAspectRatio
                                    );
        QRectF iconRect(QPointF(), iconSize);
        iconRect.moveCenter(well.center());
        painter->drawPixmap(iconRect, pixmap, QRectF(pixmap.rect()));
    }
    painter->restore();

    // File type badge in the corner of the well
    const QString suffix = QFileInfo(path).suffix().toUpper();
    if (!suffix.isEmpty()) {
        QFont badgeFont = option.font;
        constexpr double badgeScale = 0.75;
        badgeFont.setPointSizeF(badgeFont.pointSizeF() * badgeScale);
        badgeFont.setWeight(QFont::DemiBold);
        const QFontMetrics badgeMetrics(badgeFont);
        const QRectF badge(
            well.left() + padding * badgeScale,
            well.top() + padding * badgeScale,
            badgeMetrics.horizontalAdvance(suffix) + padding,
            badgeMetrics.height() + 2
        );
        QPainterPath badgePath;
        badgePath.addRoundedRect(badge, 4, 4);
        constexpr int badgeAlpha = 190;
        painter->fillPath(badgePath, QColor(10, 15, 22, badgeAlpha));  // NOLINT
        painter->setFont(badgeFont);
        painter->setPen(QColor(242, 239, 230));  // NOLINT
        painter->drawText(badge, Qt::AlignCenter, suffix);
    }

    // Name, then size and, for recent files, how long ago they were saved
    auto baseName = index.data(static_cast<int>(DisplayedFilesModelRoles::baseName)).toString();
    auto size = index.data(static_cast<int>(DisplayedFilesModelRoles::size)).toString();
    QString details = size;
    if (_showAge) {
        auto modified = QDateTime::fromString(
            index.data(static_cast<int>(DisplayedFilesModelRoles::modifiedTime)).toString(),
            Qt::ISODate
        );
        QString age = describeAge(modified, QDateTime::currentDateTime());
        if (!age.isEmpty()) {
            details = size.isEmpty() ? age : size + QStringLiteral(" · ") + age;
        }
    }

    const QFontMetrics nameMetrics(option.font);
    const QFont detailsFont = detailsFontFor(option.font);
    const QFontMetrics detailsMetrics(detailsFont);
    const int textWidth = width - 2 * padding;
    const QRectF nameRect(
        card.left() + padding,
        well.bottom() + padding,
        textWidth,
        nameMetrics.lineSpacing()
    );
    const QRectF detailsRect(
        nameRect.left(),
        nameRect.bottom() + textspacing,
        textWidth,
        detailsMetrics.lineSpacing()
    );
    painter->setFont(option.font);
    painter->setPen(option.palette.color(QPalette::Text));
    painter->drawText(
        nameRect,
        Qt::AlignLeft | Qt::AlignVCenter,
        nameMetrics.elidedText(baseName, Qt::ElideMiddle, textWidth)
    );
    painter->setFont(detailsFont);
    painter->setPen(mutedColor);
    painter->drawText(
        detailsRect,
        Qt::AlignLeft | Qt::AlignVCenter,
        detailsMetrics.elidedText(details, Qt::ElideRight, textWidth)
    );

    // Outline, in the accent colour under the mouse
    painter->setBrush(Qt::NoBrush);
    constexpr double hoverPenWidth = 1.5;
    painter->setPen(QPen(hovered ? accentColor : borderColor, hovered ? hoverPenWidth : 1.0));
    painter->drawPath(cardPath);
    painter->restore();
}


QSize FileCardDelegate::sizeHint(const QStyleOptionViewItem& option, const QModelIndex& index) const
{
    Q_UNUSED(index);

    // FileCardView asks with a default option, so take the font from the view when there is one
    QFont font = option.widget ? option.widget->font() : QGuiApplication::font();
    if (auto view = qobject_cast<QWidget*>(parent())) {
        font = view->font();
    }
    const int width = cardWidth();
    const int wellHeight = width * 3 / 4;
    const int textHeight = QFontMetrics(font).lineSpacing() + textspacing
        + QFontMetrics(detailsFontFor(font)).lineSpacing();
    return {width, wellHeight + padding + textHeight + padding + 2};
}

QFont FileCardDelegate::detailsFontFor(const QFont& font)
{
    QFont details = font;
    constexpr double detailsScale = 0.88;
    details.setPointSizeF(details.pointSizeF() * detailsScale);
    return details;
}

int FileCardDelegate::cardWidth() const
{
    // The thumbnail well is 4:3 and a little wider than the thumbnail size preference, so a
    // square thumbnail fills its height with room either side
    auto thumbnailSize = static_cast<int>(_parameterGroup->GetInt("FileThumbnailIconsSize", 128));  // NOLINT
    constexpr int numerator = 11;
    constexpr int denominator = 8;
    return thumbnailSize * numerator / denominator;
}

QString FileCardDelegate::describeAge(const QDateTime& modified, const QDateTime& now)
{
    auto translate = [](const char* text, int n = -1) {
        return QCoreApplication::translate("StartGui::FileCardDelegate", text, nullptr, n);
    };
    // With no translator loaded, %n is filled in but "(s)" is left as it is, so English
    // picks its singular and plural itself
    auto count = [&translate](int n, const char* one, const char* many) {
        return n == 1 ? translate(one) : translate(many, n);
    };
    if (!modified.isValid()) {
        return {};
    }
    const qint64 seconds = modified.secsTo(now);
    constexpr qint64 minute = 60;
    constexpr qint64 hour = 60 * minute;
    if (seconds < minute) {
        return translate("just now");
    }
    if (seconds < hour) {
        return count(static_cast<int>(seconds / minute), "1 minute ago", "%n minutes ago");
    }
    const qint64 days = modified.date().daysTo(now.date());
    if (days == 0) {
        return count(static_cast<int>(seconds / hour), "1 hour ago", "%n hours ago");
    }
    if (days == 1) {
        return translate("yesterday");
    }
    constexpr qint64 week = 7;
    if (days < week) {
        return count(static_cast<int>(days), "1 day ago", "%n days ago");
    }
    return QLocale().toString(modified.date(), QLocale::ShortFormat);
}

QPixmap FileCardDelegate::generateThumbnail(const QString& path) const
{
    auto thumbnailSize = static_cast<int>(_parameterGroup->GetInt("FileThumbnailIconsSize", 128));  // NOLINT

    // check if we have this thumbnail already inside cache, don't load it once again
    QString cacheKey = getCacheKey(path, thumbnailSize);
    if (!cacheKey.isEmpty()) {
        if (QPixmap* cachedThumbnail = _thumbnailCache.object(cacheKey)) {
            return *cachedThumbnail;  // cache hit - we bail out
        }
    }

    // cache miss - go and load the thumbnail as it could be changed
    return loadAndCacheThumbnail(path, thumbnailSize);
}

QString FileCardDelegate::getCacheKey(const QString& path, int thumbnailSize) const
{
    QFileInfo fileInfo(path);
    if (!fileInfo.exists()) {
        return {};
    }

    // create cache key: path:modtime:size
    QString modTime = QString::number(fileInfo.lastModified().toSecsSinceEpoch());
    return QStringLiteral("%1:%2:%3").arg(path, modTime, QString::number(thumbnailSize));
}

QPixmap FileCardDelegate::loadAndCacheThumbnail(const QString& path, int thumbnailSize) const
{
    QPixmap thumbnail;

    if (path.endsWith(QLatin1String(".fcstd"), Qt::CaseSensitivity::CaseInsensitive)) {
        // This is a fallback, the model will have pulled the thumbnail out of the FCStd file if it
        // existed.
        QImageReader reader(QLatin1String(":/icons/othercad-doc.svg"));
        reader.setScaledSize(QSize(thumbnailSize, thumbnailSize));
        thumbnail = QPixmap::fromImage(reader.read());
    }
    else if (path.endsWith(QLatin1String(".fcmacro"), Qt::CaseSensitivity::CaseInsensitive)) {
        QImageReader reader(QLatin1String(":/icons/MacroEditor.svg"));
        reader.setScaledSize(QSize(thumbnailSize, thumbnailSize));
        thumbnail = QPixmap::fromImage(reader.read());
    }
    else if (!QImageReader::imageFormat(path).isEmpty()) {
        // It is an image: it can be its own thumbnail
        QImageReader reader(path);

        // get original size to calculate proper aspect-preserving scaled size
        QSize originalSize = reader.size();
        if (originalSize.isValid()) {
            QSize scaledSize = originalSize.scaled(thumbnailSize, thumbnailSize, Qt::KeepAspectRatio);
            reader.setScaledSize(scaledSize);
        }

        auto image = reader.read();
        if (!image.isNull()) {
            thumbnail = QPixmap::fromImage(image);
        }
        else {
            Base::Console().log(
                "FileCardDelegate: Failed to load image %s: %s\n",
                path.toStdString().c_str(),
                reader.errorString().toStdString().c_str()
            );
        }
    }

    // fallback to system icon if no thumbnail was generated
    if (thumbnail.isNull()) {
        QIcon icon = QFileIconProvider().icon(QFileInfo(path));
        if (!icon.isNull()) {
            thumbnail = icon.pixmap(thumbnailSize);
        }
        else {
            thumbnail = QPixmap(thumbnailSize, thumbnailSize);
            thumbnail.fill();
        }
    }

    // cache the thumbnail if valid
    if (!thumbnail.isNull()) {
        QString cacheKey = getCacheKey(path, thumbnailSize);
        if (!cacheKey.isEmpty()) {
            _thumbnailCache.insert(cacheKey, new QPixmap(thumbnail), 1);
        }
    }

    return thumbnail;
}
