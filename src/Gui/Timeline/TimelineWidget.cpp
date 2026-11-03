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


#include <algorithm>
#include <cstddef>
#include <cstring>
#include <sstream>
#include <unordered_set>

#include <QAction>
#include <QApplication>
#include <QCursor>
#include <QEvent>
#include <QFrame>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QKeyEvent>
#include <QLabel>
#include <QLayoutItem>
#include <QLineEdit>
#include <QMenu>
#include <QMouseEvent>
#include <QPainter>
#include <QPaintEvent>
#include <QPalette>
#include <QScrollArea>
#include <QScrollBar>
#include <QSize>
#include <QSizePolicy>
#include <QString>
#include <QStyle>
#include <QTimer>
#include <QToolButton>

#include <App/Application.h>
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/GeoFeatureGroupExtension.h>
#include <App/Part.h>
#include <App/Property.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <App/SuppressibleExtension.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <Base/Type.h>
#include <Gui/ActiveObjectList.h>
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/Document.h>
#include <Gui/MainWindow.h>
#include <Gui/MDIView.h>
#include <Gui/ViewProvider.h>
#include <Gui/ViewProviderDocumentObject.h>

#include "TimelineMarker.h"
#include "TimelineWidget.h"


using namespace Gui::Timeline;

namespace
{
constexpr int stripMargin = 2;
constexpr int markerSpacing = 1;
// The grab area; the line drawn in the middle of it is thinner
constexpr int playheadWidth = 11;
constexpr int playheadLineWidth = 3;
constexpr int playheadGripHeight = 5;
constexpr int stepButtonExtent = 20;
constexpr int stepIconExtent = 12;
constexpr int scrollBarThickness = 8;
// Between the markers and the scroll bar under them, when it shows
constexpr int scrollBarGap = 3;
// Long enough that a slider drag or a batch of property changes collapses into
// a single update, short enough to feel immediate.
constexpr int updateDelay = 120;

constexpr int dropIndicatorWidth = 3;
// Between the fields of a stored group, which never occurs in a name or a number
constexpr char groupFieldSeparator = '\t';
// Long enough to read why a drop was refused
constexpr int refusalMessageTimeout = 6000;

const char* const bodyTypeName = "PartDesign::Body";

bool anyDocumentRecomputing()
{
    const std::vector<App::Document*> docs = App::GetApplication().getDocuments();
    return std::any_of(docs.begin(), docs.end(), [](const App::Document* doc) {
        return doc->testStatus(App::Document::Recomputing);
    });
}
const char* const solidTypeName = "PartDesign::Feature";
const char* const partFeatureTypeName = "Part::Feature";

/// A feature and the steps of its own a MultiTransform keeps in the body's Group, which
/// are not on the strip and go wherever the MultiTransform goes
std::vector<App::DocumentObject*> withSteps(App::DocumentObject* obj)
{
    std::vector<App::DocumentObject*> result {obj};
    auto* steps = freecad_cast<App::PropertyLinkList*>(obj->getPropertyByName("Transformations"));
    if (steps) {
        for (App::DocumentObject* step : steps->getValues()) {
            if (step) {
                result.push_back(step);
            }
        }
    }
    return result;
}

/// Everything obj is built on, through every link but the two the body keeps up itself:
/// BaseFeature, which the body rewires whenever its order changes, and _Body, which leads
/// back to the body and from there to every feature in it.
void collectDependencies(
    const App::DocumentObject* obj,
    const App::DocumentObject* body,
    std::unordered_set<const App::DocumentObject*>& result
)
{
    std::vector<const App::DocumentObject*> pending {obj};
    while (!pending.empty()) {
        const App::DocumentObject* current = pending.back();
        pending.pop_back();

        std::vector<App::Property*> props;
        current->getPropertyList(props);
        for (App::Property* prop : props) {
            const char* name = prop->getName();
            auto* link = freecad_cast<App::PropertyLinkBase*>(prop);
            if (!link || !name || std::strcmp(name, "BaseFeature") == 0
                || std::strcmp(name, "_Body") == 0) {
                continue;
            }
            std::vector<App::DocumentObject*> linked;
            link->getLinks(linked);
            for (App::DocumentObject* target : linked) {
                if (target && target != body && target != obj && result.insert(target).second) {
                    pending.push_back(target);
                }
            }
        }
    }
}

// The scroll area makes room for its bar from the bar's size hint, not its fixed height, so a
// bar pinned thinner than the theme's would still take the theme's extent out of the
// viewport and be drawn over the bottom of the markers.
class ThinScrollBar: public QScrollBar
{
public:
    explicit ThinScrollBar(Qt::Orientation orientation)
        : QScrollBar(orientation)
    {
        setFixedHeight(scrollBarThickness);
    }

    QSize sizeHint() const override
    {
        return {QScrollBar::sizeHint().width(), scrollBarThickness};
    }
};

// Fusion's history marker: a line between the features with a grip at either end, and a
// grab area wider than the line, which on its own was too thin to find or to catch.
// The style sheet's color is the accent the line is drawn in.
class Playhead: public QWidget
{
public:
    explicit Playhead(QWidget* parent)
        : QWidget(parent)
    {
        setAttribute(Qt::WA_Hover, true);
        setMouseTracking(true);
    }

protected:
    void paintEvent(QPaintEvent* event) override
    {
        Q_UNUSED(event)
        QPainter painter(this);
        painter.setRenderHint(QPainter::Antialiasing, true);
        QColor accent = palette().color(QPalette::WindowText);
        const bool lit = underMouse() || property("timelineDragging").toBool();
        if (lit) {
            accent = accent.lighter(135);
        }
        painter.setPen(Qt::NoPen);
        painter.setBrush(accent);

        const qreal centre = width() / 2.0;
        const qreal line = lit ? playheadLineWidth + 1 : playheadLineWidth;
        painter.drawRect(QRectF(centre - line / 2.0, 0, line, height()));

        // a grip at the top and the bottom, like the handle of a slider
        const QRectF top(0.5, 0.5, width() - 1.0, playheadGripHeight);
        const QRectF bottom(0.5, height() - playheadGripHeight - 0.5, width() - 1.0, playheadGripHeight);
        painter.drawRoundedRect(top, 2.0, 2.0);
        painter.drawRoundedRect(bottom, 2.0, 2.0);
    }

    bool event(QEvent* event) override
    {
        if (event->type() == QEvent::HoverEnter || event->type() == QEvent::HoverLeave) {
            update();
        }
        return QWidget::event(event);
    }
};
}  // namespace


TimelineWidget::TimelineWidget(QWidget* parent)
    : QWidget(parent)
    // Attached at the end of the constructor: the observer must not deliver a
    // selection change before the strip exists.
    , Gui::SelectionObserver(false)
{
    setupUi();

    updateTimer = new QTimer(this);
    updateTimer->setSingleShot(true);
    updateTimer->setInterval(updateDelay);
    connect(updateTimer, &QTimer::timeout, this, &TimelineWidget::onTimeout);

    connectDocumentSignals();
    attachSelection();
    scheduleRebuild();
}

TimelineWidget::~TimelineWidget() = default;

void TimelineWidget::setupUi()
{
    setObjectName(QStringLiteral("Timeline"));
    setAttribute(Qt::WA_StyledBackground, true);
    setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Fixed);

    auto* outerLayout = new QHBoxLayout(this);
    outerLayout->setContentsMargins(stripMargin, stripMargin, stripMargin, stripMargin);
    outerLayout->setSpacing(stripMargin);

    auto* controls = new QWidget(this);
    controls->setObjectName(QStringLiteral("TimelineControls"));
    controls->setAttribute(Qt::WA_StyledBackground, true);

    auto* controlLayout = new QHBoxLayout(controls);
    controlLayout->setContentsMargins(0, 0, 0, 0);
    controlLayout->setSpacing(1);

    stepBackButton = new QToolButton(controls);
    stepBackButton->setObjectName(QStringLiteral("TimelineStepButton"));
    stepBackButton->setIcon(style()->standardIcon(QStyle::SP_MediaSeekBackward));
    stepBackButton->setAutoRaise(true);
    // Tab reaches the strip's own controls, which is what makes the arrow keys below
    // usable without the mouse; a click still leaves the focus where the user put it.
    stepBackButton->setFocusPolicy(Qt::TabFocus);
    stepBackButton->setIconSize(QSize(stepIconExtent, stepIconExtent));
    stepBackButton->setFixedSize(stepButtonExtent, stepButtonExtent);
    stepBackButton->setToolTip(tr("Step the history back one feature"));
    // Tab can land here, and the strip has to claim its keys and answer them from a
    // focused button exactly as it does from a focused marker.
    stepBackButton->installEventFilter(this);
    connect(stepBackButton, &QToolButton::clicked, this, &TimelineWidget::stepBack);

    stepForwardButton = new QToolButton(controls);
    stepForwardButton->setObjectName(QStringLiteral("TimelineStepButton"));
    stepForwardButton->setIcon(style()->standardIcon(QStyle::SP_MediaSeekForward));
    stepForwardButton->setAutoRaise(true);
    stepForwardButton->setFocusPolicy(Qt::TabFocus);
    stepForwardButton->setIconSize(QSize(stepIconExtent, stepIconExtent));
    stepForwardButton->setFixedSize(stepButtonExtent, stepButtonExtent);
    stepForwardButton->setToolTip(tr("Step the history forward one feature"));
    stepForwardButton->installEventFilter(this);
    connect(stepForwardButton, &QToolButton::clicked, this, &TimelineWidget::stepForward);

    controlLayout->addWidget(stepBackButton);
    controlLayout->addWidget(stepForwardButton);

    auto* scrollArea = new QScrollArea(this);
    scrollArea->setObjectName(QStringLiteral("TimelineScroll"));
    scrollArea->setFrameShape(QFrame::NoFrame);
    // A scroll area takes the focus on a click by default, and a click on a marker walks
    // up to it. That would leave the focus inside the strip after an ordinary click and
    // hand it keys the user meant for the rest of the window; it would also let the scroll
    // area answer the arrows with a scroll of its own. Tab is the only way in.
    scrollArea->setFocusPolicy(Qt::NoFocus);
    scrollArea->setWidgetResizable(true);
    scrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    scrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    strip = new QWidget;
    strip->setObjectName(QStringLiteral("TimelineStrip"));
    strip->setAttribute(Qt::WA_StyledBackground, true);
    scrollArea->setWidget(strip);

    stripLayout = new QHBoxLayout(strip);
    stripLayout->setContentsMargins(0, 0, 0, 0);
    stripLayout->setSpacing(markerSpacing);

    playhead = new Playhead(strip);
    playhead->setObjectName(QStringLiteral("TimelinePlayhead"));
    playhead->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    playhead->setFixedWidth(playheadWidth);
    playhead->setCursor(Qt::SizeHorCursor);
    playhead->setToolTip(tr("Drag to roll the model history back and forward"));
    playhead->installEventFilter(this);
    playhead->hide();

    // Laid over the strip rather than in its layout, so showing it moves no marker
    dropIndicator = new QWidget(strip);
    dropIndicator->setObjectName(QStringLiteral("TimelineDropIndicator"));
    dropIndicator->setAttribute(Qt::WA_StyledBackground, true);
    dropIndicator->setAttribute(Qt::WA_TransparentForMouseEvents, true);
    dropIndicator->hide();

    emptyLabel = new QLabel(tr("No feature history"), strip);
    emptyLabel->setObjectName(QStringLiteral("TimelineEmptyLabel"));
    emptyLabel->hide();

    bodyLabel = new QLabel(this);
    bodyLabel->setObjectName(QStringLiteral("TimelineBodyLabel"));
    // A click makes the body on the strip the active one, as the tree's indicator does
    bodyLabel->setCursor(Qt::PointingHandCursor);
    bodyLabel->installEventFilter(this);
    bodyLabel->hide();

    outerLayout->addWidget(bodyLabel, 0, Qt::AlignVCenter);
    outerLayout->addWidget(controls, 0, Qt::AlignVCenter);
    outerLayout->addWidget(scrollArea, 1);

    // The scroll bar's own extent has to be reserved whether or not it is showing,
    // and the theme's is taller than the markers themselves, so it is pinned to
    // something proportionate instead. Fusion's timeline is a thin strip.
    scrollArea->setHorizontalScrollBar(new ThinScrollBar(Qt::Horizontal));
    setFixedHeight(
        TimelineMarker::tileSize().height() + 2 * stripMargin + scrollBarGap + scrollBarThickness
    );
}

void TimelineWidget::connectDocumentSignals()
{
    Gui::Application* app = Gui::Application::Instance;
    if (!app) {
        return;
    }

    connActiveDocument = app->signalActiveDocument.connect([this](const Gui::Document&) {
        scheduleRebuild();
    });
    connNewDocument = app->signalNewDocument.connect([this](const Gui::Document&, bool) {
        scheduleRebuild();
    });
    connDeleteDocument = app->signalDeleteDocument.connect([this](const Gui::Document& doc) {
        if (&doc == trackedDocument) {
            connActiveObject.disconnect();
            connInEdit.disconnect();
            connResetEdit.disconnect();
            trackedDocument = nullptr;
        }
        // A document opened later under the same name must not inherit what was followed here
        if (followedDocumentName == doc.getDocument()->getName()) {
            followedBodyName.clear();
            followedDocumentName.clear();
        }
        // Nor the groups that were unfolded in it
        const std::string prefix = std::string(doc.getDocument()->getName()) + "/";
        std::erase_if(expandedGroups, [&prefix](const std::string& key) {
            return key.starts_with(prefix);
        });
        scheduleRebuild();
    });
    connNewObject = app->signalNewObject.connect([this](const Gui::ViewProvider&) {
        scheduleRebuild();
    });
    connDeletedObject = app->signalDeletedObject.connect([this](const Gui::ViewProvider&) {
        scheduleRebuild();
    });
    connChangedObject = app->signalChangedObject.connect(
        [this](const Gui::ViewProvider&, const App::Property& prop) {
            const char* name = prop.getName();
            const bool structural = name != nullptr
                && (std::strcmp(name, "Group") == 0 || std::strcmp(name, "Tip") == 0
                    || std::strcmp(name, "TimelineGroups") == 0
                    || std::strcmp(name, "BaseFeature") == 0
                    || std::strcmp(name, "Transformations") == 0);
            if (structural) {
                scheduleRebuild();
            }
            else {
                scheduleRefresh();
            }
        }
    );
    connRelabelObject = app->signalRelabelObject.connect([this](const Gui::ViewProvider&) {
        scheduleRefresh();
    });
    connActivateView = app->signalActivateView.connect([this](const Gui::MDIView*) {
        scheduleRebuild();
    });
    connCloseView = app->signalCloseView.connect([this](const Gui::MDIView*) { scheduleRebuild(); });
}

void TimelineWidget::trackDocument(Gui::Document* doc)
{
    if (doc == trackedDocument) {
        return;
    }

    connActiveObject.disconnect();
    connInEdit.disconnect();
    connResetEdit.disconnect();
    trackedDocument = doc;

    if (doc) {
        connActiveObject = doc->signalActivatedViewProvider.connect(
            [this](const Gui::ViewProviderDocumentObject*, const char* key) {
                if (key && std::strcmp(key, PDBODYKEY) == 0) {
                    // Activating a body is pointing at it: it wins over an older selection
                    followedBodyName.clear();
                    followedDocumentName.clear();
                }
                scheduleRebuild();
            }
        );
        // The body being edited takes the strip for as long as the edit lasts
        connInEdit = doc->signalInEdit.connect([this](const Gui::ViewProviderDocumentObject&) {
            scheduleRebuild();
        });
        // Picks made during the edit left the strip alone, so it stays on the body just edited
        connResetEdit = doc->signalResetEdit.connect([this](const Gui::ViewProviderDocumentObject& vp) {
            App::DocumentObject* obj = vp.getObject();
            App::DocumentObject* body = obj && obj->isAttachedToDocument() ? bodyOf(obj) : nullptr;
            if (body && body->isAttachedToDocument()) {
                followedBodyName = body->getNameInDocument();
                followedDocumentName = body->getDocument()->getName();
            }
            scheduleRebuild();
        });
    }
}

void TimelineWidget::scheduleRebuild()
{
    pendingRebuild = true;
    updateTimer->start();
}

void TimelineWidget::scheduleRefresh()
{
    updateTimer->start();
}

void TimelineWidget::onTimeout()
{
    // Rebuilding deletes the markers, the one being dragged among them, so it waits
    if (dragInProgress()) {
        updateTimer->start();
        return;
    }
    // Opening or recomputing a document changes object after object, and the progress bar
    // runs the event loop throughout, so the timer would fire again and again midway.
    // Wait for the load or the recompute to finish.
    if (App::GetApplication().isRestoring() || anyDocumentRecomputing()) {
        updateTimer->start();
        return;
    }

    if (pendingRebuild) {
        pendingRebuild = false;
        rebuild();
    }
    else {
        refreshMarkers();
    }
}

void TimelineWidget::clearStrip()
{
    while (QLayoutItem* item = stripLayout->takeAt(0)) {
        if (QWidget* widget = item->widget()) {
            widget->hide();
        }
        delete item;
    }
}

void TimelineWidget::rebuild()
{
    clearStrip();

    for (TimelineMarker* marker : markers) {
        marker->deleteLater();
    }
    markers.clear();
    for (const ShownGroup& group : shownGroups) {
        group.marker->deleteLater();
    }
    shownGroups.clear();
    featureGroup.clear();
    stripItems.clear();
    featureNames.clear();
    solidIndices.clear();
    hasBaseFeature = false;
    documentName.clear();
    bodyName.clear();
    tipIndex = -1;

    Gui::Application* app = Gui::Application::Instance;
    Gui::Document* guiDoc = app ? app->activeDocument() : nullptr;
    trackDocument(guiDoc);

    App::Document* appDoc = guiDoc ? guiDoc->getDocument() : nullptr;
    std::vector<App::DocumentObject*> features;
    App::DocumentObject* body = nullptr;

    if (appDoc) {
        documentName = appDoc->getName();
        body = shownBody(guiDoc);
    }

    if (appDoc) {
        if (body) {
            bodyName = body->getNameInDocument();
            collectBodyFeatures(body, features);
        }
        else {
            collectDocumentFeatures(appDoc, features);
        }
    }

    App::DocumentObject* baseFeature = nullptr;
    App::DocumentObject* tip = nullptr;
    if (body) {
        auto* baseProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("BaseFeature"));
        if (baseProp) {
            baseFeature = baseProp->getValue();
        }
        auto* tipProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("Tip"));
        if (tipProp) {
            tip = tipProp->getValue();
        }
    }

    const Base::Type solidType = Base::Type::fromName(solidTypeName);

    for (std::size_t i = 0; i < features.size(); ++i) {
        App::DocumentObject* obj = features[i];
        auto* marker = new TimelineMarker(obj, strip);
        connect(marker, &TimelineMarker::selectRequested, this, &TimelineWidget::onMarkerSelect);
        connect(marker, &TimelineMarker::editRequested, this, &TimelineWidget::onMarkerEdit);
        // Queued: the context menu spins a nested event loop, which must not run
        // inside the event handler of the marker that opened it.
        connect(
            marker,
            &TimelineMarker::menuRequested,
            this,
            &TimelineWidget::onMarkerMenu,
            Qt::QueuedConnection
        );
        // A focused marker sits inside a scroll area, which answers the arrow keys with
        // a scroll of its own before they ever reach the strip, so they are taken here.
        marker->installEventFilter(this);

        markers.append(marker);
        featureNames.emplace_back(obj->getNameInDocument());

        if (obj == baseFeature || (!solidType.isBad() && obj->isDerivedFrom(solidType))) {
            solidIndices.push_back(static_cast<int>(i));
        }
        if (obj == tip) {
            tipIndex = static_cast<int>(i);
        }
        if (i == 0 && obj == baseFeature) {
            hasBaseFeature = true;
        }
    }

    // Outside a body there is no tip to roll to, so the whole strip counts as applied.
    if (!body) {
        tipIndex = static_cast<int>(features.size()) - 1;
    }

    const int count = static_cast<int>(markers.size());

    playheadIndex = defaultPlayhead();
    if (requestedPlayhead >= -1 && requestedPlayhead < count
        && solidAtOrBefore(requestedPlayhead) == tipIndex) {
        playheadIndex = requestedPlayhead;
    }
    requestedPlayhead = noPlayheadRequest;

    // Each group is shown as the run of members side by side from its first one. Members
    // something else has since been moved in between (by the tree, say) show on their own.
    featureGroup.assign(static_cast<std::size_t>(count), -1);
    std::vector<long> ids(static_cast<std::size_t>(count), -1);
    for (int i = 0; i < count; ++i) {
        if (App::DocumentObject* obj = markers[i]->object()) {
            ids[static_cast<std::size_t>(i)] = obj->getID();
        }
    }
    for (const FeatureGroup& group : readGroups()) {
        const auto isMember = [&](int i) {
            return featureGroup[static_cast<std::size_t>(i)] < 0
                && std::find(
                       group.members.begin(),
                       group.members.end(),
                       ids[static_cast<std::size_t>(i)]
                   )
                != group.members.end();
        };
        int first = 0;
        while (first < count && !isMember(first)) {
            ++first;
        }
        if (first == count) {
            continue;
        }
        int last = first;
        while (last + 1 < count && isMember(last + 1)) {
            ++last;
        }

        ShownGroup shown;
        shown.key = group.key;
        shown.first = first;
        shown.last = last;
        // A playhead between two members has to be seen there, so that group stays open
        shown.expanded = expandedGroups.count(groupStateKey(group.key)) > 0
            || (playheadIndex >= first && playheadIndex < last);
        shown.marker = new TimelineGroupMarker(QString::fromStdString(group.key), strip);
        connect(shown.marker, &TimelineGroupMarker::selectRequested, this, &TimelineWidget::onGroupSelect);
        connect(shown.marker, &TimelineGroupMarker::toggleRequested, this, &TimelineWidget::onGroupToggle);
        connect(
            shown.marker,
            &TimelineGroupMarker::menuRequested,
            this,
            &TimelineWidget::onGroupMenu,
            Qt::QueuedConnection
        );
        shown.marker->installEventFilter(this);

        bool error = false;
        bool warning = false;
        for (int i = first; i <= last; ++i) {
            featureGroup[static_cast<std::size_t>(i)] = static_cast<int>(shownGroups.size());
            App::DocumentObject* obj = markers[i]->object();
            error = error || (obj && obj->isError());
            warning = warning || markers[i]->hasWarning();
        }
        shown.marker->setGroup(
            QString::fromUtf8(group.label.c_str()),
            last - first + 1,
            shown.expanded,
            error,
            warning
        );
        shownGroups.push_back(shown);
    }

    for (int i = 0; i < count; ++i) {
        const int group = featureGroup[static_cast<std::size_t>(i)];
        if (group >= 0 && shownGroups[static_cast<std::size_t>(group)].first == i) {
            const ShownGroup& shown = shownGroups[static_cast<std::size_t>(group)];
            stripLayout->addWidget(shown.marker);
            shown.marker->show();
            stripItems.push_back({shown.first, shown.last, shown.marker, shown.expanded});
            if (!shown.expanded) {
                // Folded: the group's marker stands in for every member
                for (int member = shown.first; member <= shown.last; ++member) {
                    markers[member]->hide();
                }
                i = shown.last;
                continue;
            }
        }
        stripLayout->addWidget(markers[i]);
        markers[i]->show();
        stripItems.push_back({i, i, markers[i]});
    }

    if (count == 0) {
        stripLayout->addWidget(emptyLabel);
        emptyLabel->show();
    }

    stripLayout->addStretch(1);

    positionPlayhead();
    applyRollbackVisibility();
    applyStates();
    updateBodyLabel();
}

void TimelineWidget::updateBodyLabel()
{
    // The strip names its body and says whether new features go into it, as it can show a
    // body other than the active one. The marks match the tree's active-body indicator.
    App::DocumentObject* body = currentBody();
    Gui::Application* app = Gui::Application::Instance;
    if (!body || !app) {
        bodyLabel->hide();
        return;
    }
    const QString name = QString::fromUtf8(body->Label.getValue());
    const bool active = body == activeBody(app->activeDocument());
    QFont font = bodyLabel->font();
    font.setBold(active);
    bodyLabel->setFont(font);
    if (active) {
        bodyLabel->setText(QString(QChar(0x25C9)) + QLatin1Char(' ') + name);
        bodyLabel->setToolTip(tr("The active body: new features go into it"));
    }
    else {
        bodyLabel->setText(QString(QChar(0x25CB)) + QLatin1Char(' ') + tr("%1 (inactive)").arg(name));
        bodyLabel->setToolTip(tr("Click to make this body the active one"));
    }
    bodyLabel->show();
}

void TimelineWidget::positionPlayhead()
{
    // Without a body there is no tip to roll to, so nothing is ever behind the playhead
    // and the playhead itself stays out of the strip.
    if (bodyName.empty()) {
        stripLayout->removeWidget(playhead);
        playhead->hide();
        return;
    }

    // The items occupy the first positions of the layout and the stretch trails them, so
    // the slot in front of the first item the playhead has not reached is its own.
    const auto reached
        = std::count_if(stripItems.cbegin(), stripItems.cend(), [this](const StripItem& item) {
              return item.first <= playheadIndex;
          });
    stripLayout->removeWidget(playhead);
    stripLayout->insertWidget(static_cast<int>(reached), playhead);
    playhead->show();
}

void TimelineWidget::refreshMarkers()
{
    for (TimelineMarker* marker : markers) {
        marker->refresh();
    }

    applyStates();
    // A relabelled body is only refreshed, not rebuilt
    updateBodyLabel();
}

void TimelineWidget::applyStates()
{
    const int count = static_cast<int>(markers.size());
    for (int i = 0; i < count; ++i) {
        TimelineMarker* marker = markers[i];
        App::DocumentObject* obj = marker->object();
        const bool selected = obj != nullptr && Gui::Selection().isSelected(obj);

        if (selected) {
            marker->setState(TimelineMarker::State::Selected);
        }
        else if (i > playheadIndex) {
            marker->setState(TimelineMarker::State::RolledBack);
        }
        else {
            marker->setState(TimelineMarker::State::Normal);
        }

        marker->setTip(i == tipIndex);
    }

    for (const ShownGroup& group : shownGroups) {
        bool selected = false;
        for (int i = group.first; i <= group.last && !selected; ++i) {
            App::DocumentObject* obj = markers[i]->object();
            selected = obj != nullptr && Gui::Selection().isSelected(obj);
        }
        if (selected) {
            group.marker->setState(TimelineMarker::State::Selected);
        }
        else if (group.first > playheadIndex) {
            group.marker->setState(TimelineMarker::State::RolledBack);
        }
        else {
            group.marker->setState(TimelineMarker::State::Normal);
        }
        group.marker->setTip(!group.expanded && tipIndex >= group.first && tipIndex <= group.last);
    }

    const bool hasBody = !bodyName.empty();
    stepBackButton->setEnabled(hasBody && playheadIndex >= 0);
    stepForwardButton->setEnabled(hasBody && playheadIndex + 1 < count);
}

App::Document* TimelineWidget::currentDocument() const
{
    if (documentName.empty()) {
        return nullptr;
    }

    return App::GetApplication().getDocument(documentName.c_str());
}

App::DocumentObject* TimelineWidget::resolve(const std::string& name) const
{
    if (name.empty()) {
        return nullptr;
    }

    App::Document* doc = currentDocument();
    return doc ? doc->getObject(name.c_str()) : nullptr;
}

App::DocumentObject* TimelineWidget::currentBody() const
{
    App::DocumentObject* body = resolve(bodyName);
    if (!body) {
        return nullptr;
    }

    const Base::Type bodyType = Base::Type::fromName(bodyTypeName);
    if (bodyType.isBad() || !body->isDerivedFrom(bodyType)) {
        return nullptr;
    }

    return body;
}

App::DocumentObject* TimelineWidget::activeBody(Gui::Document* guiDoc) const
{
    if (!guiDoc) {
        return nullptr;
    }

    Gui::MDIView* view = guiDoc->getActiveView();
    if (!view) {
        return nullptr;
    }

    const Base::Type bodyType = Base::Type::fromName(bodyTypeName);
    if (bodyType.isBad()) {
        return nullptr;
    }

    App::DocumentObject* body = view->getActiveObject<App::DocumentObject*>(PDBODYKEY);
    if (!body || !body->isAttachedToDocument() || !body->isDerivedFrom(bodyType)) {
        return nullptr;
    }
    if (body->getDocument() != guiDoc->getDocument()) {
        return nullptr;
    }

    return body;
}

App::DocumentObject* TimelineWidget::bodyOf(App::DocumentObject* obj) const
{
    const Base::Type bodyType = Base::Type::fromName(bodyTypeName);
    if (bodyType.isBad()) {
        return nullptr;
    }

    // A feature's group is its body. An origin plane or axis is handed straight to the
    // body that owns its origin, and a body inside a Part is found before the Part is.
    for (int depth = 0; obj && depth < 4; ++depth) {
        if (obj->isDerivedFrom(bodyType)) {
            return obj;
        }
        obj = App::GeoFeatureGroupExtension::getGroupOfObject(obj);
    }

    return nullptr;
}

App::DocumentObject* TimelineWidget::editedBody(Gui::Document* guiDoc) const
{
    Gui::ViewProvider* provider = guiDoc ? guiDoc->getInEdit() : nullptr;
    auto* objectProvider = freecad_cast<Gui::ViewProviderDocumentObject*>(provider);
    return objectProvider ? bodyOf(objectProvider->getObject()) : nullptr;
}

App::DocumentObject* TimelineWidget::shownBody(Gui::Document* guiDoc) const
{
    if (App::DocumentObject* body = editedBody(guiDoc)) {
        return body;
    }

    if (guiDoc && !followedBodyName.empty()
        && followedDocumentName == guiDoc->getDocument()->getName()) {
        App::DocumentObject* body = guiDoc->getDocument()->getObject(followedBodyName.c_str());
        // A followed body that has been deleted, or a name now taken by something else
        if (body && body->isAttachedToDocument() && bodyOf(body) == body) {
            return body;
        }
    }

    return activeBody(guiDoc);
}

bool TimelineWidget::activateShownBody()
{
    App::DocumentObject* body = currentBody();
    Gui::Application* app = Gui::Application::Instance;
    Gui::Document* guiDoc = app ? app->activeDocument() : nullptr;
    if (!body || !guiDoc || guiDoc->getDocument() != body->getDocument()) {
        return false;
    }
    if (activeBody(guiDoc) == body) {
        return true;
    }

    // What double-clicking the body in the tree does, less the switch of workbench: a body
    // inside a Part needs its Part active too. Neither is a change to the document, so none
    // of it lands in the undo history and one undo still takes back only the action itself.
    try {
        if (App::Part* part = App::Part::getPartOfObject(body)) {
            Gui::Command::doCommand(
                Gui::Command::Gui,
                "Gui.ActiveDocument.ActiveView.setActiveObject('%s',%s)",
                PARTKEY,
                Gui::Command::getObjectCmd(part).c_str()
            );
        }
        Gui::Command::doCommand(
            Gui::Command::Gui,
            "Gui.ActiveDocument.ActiveView.setActiveObject('%s',%s)",
            PDBODYKEY,
            Gui::Command::getObjectCmd(body).c_str()
        );
    }
    catch (const Base::Exception& e) {
        e.reportException();
        return false;
    }

    // Acting on a body is pointing at it, so the strip stays on it whatever was selected
    followedBodyName = body->getNameInDocument();
    followedDocumentName = body->getDocument()->getName();
    return activeBody(guiDoc) == body;
}

void TimelineWidget::collectBodyFeatures(
    App::DocumentObject* body,
    std::vector<App::DocumentObject*>& features
) const
{
    // The origin and its planes and axes are part of the body group but they
    // are not history, so they never reach the strip.
    std::unordered_set<const App::DocumentObject*> skipped;
    auto* originProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("Origin"));
    if (originProp) {
        App::DocumentObject* origin = originProp->getValue();
        if (origin) {
            skipped.insert(origin);
            auto* originGroup = freecad_cast<App::PropertyLinkList*>(
                origin->getPropertyByName("Group")
            );
            if (originGroup) {
                for (App::DocumentObject* child : originGroup->getValues()) {
                    if (child) {
                        skipped.insert(child);
                    }
                }
            }
        }
    }

    auto* baseProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("BaseFeature"));
    if (baseProp) {
        App::DocumentObject* base = baseProp->getValue();
        if (base && base->isAttachedToDocument()) {
            features.push_back(base);
        }
    }

    auto* groupProp = freecad_cast<App::PropertyLinkList*>(body->getPropertyByName("Group"));
    if (groupProp) {
        // The steps of a MultiTransform are edited through it and make no shape of their own,
        // the way the tree shows them under it. As markers they would be solids the playhead
        // could stop on, and rolling to one would make it the body's tip.
        for (App::DocumentObject* child : groupProp->getValues()) {
            auto* steps = child
                ? freecad_cast<App::PropertyLinkList*>(child->getPropertyByName("Transformations"))
                : nullptr;
            if (steps) {
                for (App::DocumentObject* step : steps->getValues()) {
                    skipped.insert(step);
                }
            }
        }

        for (App::DocumentObject* child : groupProp->getValues()) {
            if (child && child->isAttachedToDocument() && skipped.count(child) == 0) {
                features.push_back(child);
            }
        }
    }
}

void TimelineWidget::collectDocumentFeatures(
    App::Document* doc,
    std::vector<App::DocumentObject*>& features
) const
{
    const Base::Type featureType = Base::Type::fromName(partFeatureTypeName);
    if (featureType.isBad()) {
        return;
    }

    // Creation order, which is what a history strip wants anyway. Sorting
    // topologically instead would be wrong here: on a document whose dependency
    // graph has no zero-in-degree node, which a body with an origin readily
    // produces, topologicalSort() reports a cyclic dependency straight to stderr
    // and hands back an empty list rather than throwing, so the panel would go
    // blank while the report view filled up.
    for (App::DocumentObject* obj : doc->getObjects()) {
        if (obj && obj->isAttachedToDocument() && obj->isDerivedFrom(featureType)) {
            features.push_back(obj);
        }
    }
}

int TimelineWidget::markerIndexAt(const QPoint& stripPos) const
{
    int index = -1;
    for (const StripItem& item : stripItems) {
        if (item.widget->geometry().center().x() <= stripPos.x()) {
            index = item.header ? item.first - 1 : item.last;
        }
    }

    return index;
}

int TimelineWidget::itemIndexOf(const QObject* widget) const
{
    const int count = static_cast<int>(stripItems.size());
    for (int i = 0; i < count; ++i) {
        if (stripItems[static_cast<std::size_t>(i)].widget == widget) {
            return i;
        }
    }

    return -1;
}

int TimelineWidget::indexOfFeature(const std::string& name) const
{
    const int count = static_cast<int>(featureNames.size());
    for (int i = 0; i < count; ++i) {
        if (featureNames[static_cast<std::size_t>(i)] == name) {
            return i;
        }
    }

    return -1;
}

int TimelineWidget::solidAtOrBefore(int index) const
{
    int result = -1;
    for (int solid : solidIndices) {
        if (solid > index) {
            break;
        }
        result = solid;
    }

    return result;
}

bool TimelineWidget::isSolidIndex(int index) const
{
    return std::find(solidIndices.begin(), solidIndices.end(), index) != solidIndices.end();
}

App::PropertyStringList* TimelineWidget::rollbackHiddenProperty() const
{
    App::DocumentObject* body = currentBody();
    Gui::Application* app = Gui::Application::Instance;
    if (!body || !app) {
        return nullptr;
    }

    Gui::ViewProvider* provider = app->getViewProvider(body);
    if (!provider) {
        return nullptr;
    }

    // Read by name so that Gui does not have to know the PartDesign view provider that
    // declares it; a body without the property simply remembers nothing.
    return freecad_cast<App::PropertyStringList*>(provider->getPropertyByName("RollbackHidden"));
}

void TimelineWidget::applyRollbackVisibility()
{
    // Outside a body there is no tip to roll to and nowhere to write down what was held
    // back, so the strip leaves visibility alone rather than letting go of a rollback the
    // user can still see. Coming back to the body finds the list where it left it.
    App::PropertyStringList* hiddenProperty = rollbackHiddenProperty();
    if (!hiddenProperty) {
        return;
    }

    const std::vector<std::string> remembered = hiddenProperty->getValues();
    const auto wasHidden = [&remembered](const std::string& name) {
        return std::find(remembered.begin(), remembered.end(), name) != remembered.end();
    };

    // Worked out in full before anything is written: the list is a plain property and the
    // visibilities are not, so writing the list first is what opens the transaction that
    // the visibility changes then land in. A name that has gone from the strip is dropped
    // on the way, since the strip can no longer put that feature back.
    std::vector<std::string> hidden;
    std::vector<App::DocumentObject*> toHide;
    std::vector<App::DocumentObject*> toShow;

    const int count = static_cast<int>(featureNames.size());
    for (int i = 0; i < count; ++i) {
        const std::string& name = featureNames[static_cast<std::size_t>(i)];
        App::DocumentObject* obj = resolve(name);
        if (!obj || !obj->isAttachedToDocument()) {
            continue;
        }

        // The tip owns the solids: moving it already shows the one it lands on and
        // hides the rest, and fighting that here would undo its work.
        if (isSolidIndex(i)) {
            continue;
        }

        if (i > playheadIndex) {
            // Only what the strip itself took off the screen is put back later, so a
            // sketch the user hid by hand is left out of the list.
            if (obj->Visibility.getValue()) {
                toHide.push_back(obj);
                hidden.push_back(name);
            }
            else if (wasHidden(name)) {
                hidden.push_back(name);
            }
        }
        else if (wasHidden(name)) {
            toShow.push_back(obj);
        }
    }

    if (hidden != remembered) {
        hiddenProperty->setValues(hidden);
    }

    for (App::DocumentObject* obj : toHide) {
        obj->Visibility.setValue(false);
    }
    for (App::DocumentObject* obj : toShow) {
        obj->Visibility.setValue(true);
    }
}

TimelineWidget::RollAction TimelineWidget::keyAction(const QKeyEvent* event) const
{
    // Nothing to roll without a body, and swallowing the arrows would then only stop the
    // strip's neighbours from seeing them.
    if (bodyName.empty()) {
        return nullptr;
    }

    // The number pad sends the same keys with a modifier of its own.
    if ((event->modifiers() & ~Qt::KeypadModifier) != Qt::NoModifier) {
        return nullptr;
    }

    // The one place the strip's keys are written down: the claim below and the press that
    // follows it have to agree on the list, so they both read it from here.
    switch (event->key()) {
        case Qt::Key_Left:
            return &TimelineWidget::stepBack;
        case Qt::Key_Right:
            return &TimelineWidget::stepForward;
        case Qt::Key_Home:
            return &TimelineWidget::rollToStart;
        case Qt::Key_End:
            return &TimelineWidget::rollToEnd;
        default:
            return nullptr;
    }
}

bool TimelineWidget::handleKey(QKeyEvent* event)
{
    const RollAction roll = keyAction(event);
    if (!roll) {
        return false;
    }

    (this->*roll)();
    return true;
}

void TimelineWidget::keyPressEvent(QKeyEvent* event)
{
    if (handleKey(event)) {
        event->accept();
        return;
    }

    QWidget::keyPressEvent(event);
}

bool TimelineWidget::event(QEvent* event)
{
    // Home already belongs to the Home view command, and a command shortcut is answered
    // before the widget that has the focus ever sees the key. Qt offers the focused widget
    // the first refusal through this event: claiming the key here is what hands the press
    // to the strip instead of the camera, and only while the strip holds the focus, so the
    // command keeps Home everywhere else.
    if (event->type() == QEvent::ShortcutOverride && keyAction(static_cast<QKeyEvent*>(event))) {
        event->accept();
        return true;
    }

    return QWidget::event(event);
}

bool TimelineWidget::eventFilter(QObject* watched, QEvent* event)
{
    if (watched == bodyLabel && event->type() == QEvent::MouseButtonRelease
        && static_cast<QMouseEvent*>(event)->button() == Qt::LeftButton) {
        activateShownBody();
        updateBodyLabel();
        return true;
    }
    // A focused marker or step button is offered the key before the strip is, so the
    // claim has to be made here as well as in event() above.
    if (event->type() == QEvent::ShortcutOverride && keyAction(static_cast<QKeyEvent*>(event))) {
        event->accept();
        return true;
    }

    if (event->type() == QEvent::KeyPress && handleKey(static_cast<QKeyEvent*>(event))) {
        return true;
    }

    // A marker dragged along the strip moves its feature. The press is still the marker's
    // own, which selects the feature; only a move past the drag distance starts a drag.
    if (watched != playhead && !bodyName.empty() && itemIndexOf(watched) >= 0) {
        switch (event->type()) {
            case QEvent::MouseButtonPress: {
                auto* mouse = static_cast<QMouseEvent*>(event);
                if (mouse->button() == Qt::LeftButton) {
                    endMarkerDrag();
                    pressedItem = static_cast<QWidget*>(watched);
                    pressPos = mouse->globalPosition().toPoint();
                }
                break;
            }
            case QEvent::MouseMove: {
                auto* mouse = static_cast<QMouseEvent*>(event);
                if (pressedItem.data() != watched || !(mouse->buttons() & Qt::LeftButton)) {
                    break;
                }
                const QPoint globalPos = mouse->globalPosition().toPoint();
                if (!draggingMarker
                    && (globalPos - pressPos).manhattanLength() >= QApplication::startDragDistance()) {
                    const StripItem& item = stripItems[static_cast<std::size_t>(itemIndexOf(watched))];
                    draggingMarker = true;
                    dragFirst = item.first;
                    dragLast = item.last;
                    dragWholeGroup = qobject_cast<TimelineGroupMarker*>(item.widget) != nullptr;
                    dragDependencies.clear();
                }
                if (draggingMarker) {
                    updateMarkerDrag(globalPos);
                    return true;
                }
                break;
            }
            case QEvent::MouseButtonRelease: {
                auto* mouse = static_cast<QMouseEvent*>(event);
                if (mouse->button() != Qt::LeftButton || pressedItem.data() != watched) {
                    break;
                }
                if (draggingMarker) {
                    finishMarkerDrag(mouse->globalPosition().toPoint());
                    return true;
                }
                endMarkerDrag();
                break;
            }
            default:
                break;
        }
    }

    if (watched != playhead) {
        return QWidget::eventFilter(watched, event);
    }

    switch (event->type()) {
        case QEvent::MouseButtonPress:
            if (static_cast<QMouseEvent*>(event)->button() == Qt::LeftButton) {
                endScrub();
                draggingPlayhead = true;
                playhead->setProperty("timelineDragging", true);
                playhead->update();
                return true;
            }
            return false;
        case QEvent::MouseMove:
            // The model follows the playhead while it is dragged, as in Fusion
            if (draggingPlayhead) {
                const QPoint globalPos = static_cast<QMouseEvent*>(event)->globalPosition().toPoint();
                scrubTo(markerIndexAt(strip->mapFromGlobal(globalPos)));
            }
            return draggingPlayhead;
        case QEvent::MouseButtonRelease: {
            if (!draggingPlayhead) {
                return false;
            }
            const QPoint globalPos = static_cast<QMouseEvent*>(event)->globalPosition().toPoint();
            scrubTo(markerIndexAt(strip->mapFromGlobal(globalPos)));
            endScrub();
            return true;
        }
        default:
            return QWidget::eventFilter(watched, event);
    }
}

void TimelineWidget::onMarkerSelect(const QString& feature)
{
    App::DocumentObject* obj = resolve(feature.toStdString());
    if (!obj || !obj->isAttachedToDocument()) {
        return;
    }

    Gui::Selection().clearSelection();
    Gui::Selection().addSelection(obj->getDocument()->getName(), obj->getNameInDocument());
}

void TimelineWidget::onMarkerEdit(const QString& feature)
{
    editFeature(feature.toStdString());
}

void TimelineWidget::onMarkerMenu(const QString& feature, const QPoint& globalPos)
{
    const std::string name = feature.toStdString();
    if (!resolve(name)) {
        return;
    }

    const int index = indexOfFeature(name);

    // A feature in yellow is opened to check or reselect the reference that moved
    const bool warned = std::any_of(markers.cbegin(), markers.cend(), [&](TimelineMarker* marker) {
        App::DocumentObject* obj = marker->object();
        return obj && name == obj->getNameInDocument() && marker->hasWarning();
    });

    QMenu menu(this);
    QAction* editAction = menu.addAction(warned ? tr("Edit to Reselect") : tr("Edit"));
    QAction* renameAction = menu.addAction(tr("Rename"));
    QAction* deleteAction = menu.addAction(tr("Delete"));
    QAction* suppressAction = nullptr;
    auto* suppressible = resolve(name)->getExtensionByType<App::SuppressibleExtension>(true);
    if (suppressible && !suppressible->Suppressed.testStatus(App::Property::Hidden)) {
        suppressAction = menu.addAction(tr("Suppress"));
        suppressAction->setCheckable(true);
        suppressAction->setChecked(suppressible->Suppressed.getValue());
    }
    // Names rather than indices: the menu's event loop may rebuild the strip
    QAction* groupAction = nullptr;
    std::string groupFirst;
    std::string groupLast;
    if (!bodyName.empty() && index >= 0) {
        int first = -1;
        int last = -1;
        groupAction = menu.addAction(tr("Group"));
        groupAction->setEnabled(groupCandidates(index, first, last));
        if (groupAction->isEnabled()) {
            groupFirst = featureNames[static_cast<std::size_t>(first)];
            groupLast = featureNames[static_cast<std::size_t>(last)];
        }
    }
    QAction* rollAction = nullptr;
    if (!bodyName.empty() && index >= 0) {
        menu.addSeparator();
        rollAction = menu.addAction(tr("Roll History Here"));
    }

    // The menu runs its own event loop, so the marker may be gone by the time it
    // closes. Everything below works off the name captured above.
    QAction* chosen = menu.exec(globalPos);
    if (!chosen) {
        return;
    }

    if (chosen == editAction) {
        editFeature(name);
    }
    else if (chosen == renameAction) {
        renameFeature(name);
    }
    else if (chosen == deleteAction) {
        deleteFeature(name);
    }
    else if (chosen == suppressAction) {
        toggleSuppressed(name);
    }
    else if (chosen == rollAction) {
        moveTo(index);
    }
    else if (chosen == groupAction) {
        const int first = indexOfFeature(groupFirst);
        const int last = indexOfFeature(groupLast);
        if (first >= 0 && last >= first) {
            createGroup(first, last);
        }
    }
}

void TimelineWidget::onGroupSelect(const QString& key)
{
    const int index = shownGroupIndex(key.toStdString());
    if (index < 0) {
        return;
    }

    // Picking the group picks what is in it, as a click on a folder row would
    const ShownGroup& group = shownGroups[static_cast<std::size_t>(index)];
    std::vector<App::DocumentObject*> members;
    for (int i = group.first; i <= group.last; ++i) {
        if (App::DocumentObject* obj = markers[i]->object()) {
            members.push_back(obj);
        }
    }
    Gui::Selection().clearSelection();
    for (App::DocumentObject* obj : members) {
        Gui::Selection().addSelection(obj->getDocument()->getName(), obj->getNameInDocument());
    }
}

void TimelineWidget::onGroupToggle(const QString& key)
{
    const int index = shownGroupIndex(key.toStdString());
    if (index < 0) {
        return;
    }

    const std::string state = groupStateKey(key.toStdString());
    if (shownGroups[static_cast<std::size_t>(index)].expanded) {
        expandedGroups.erase(state);
    }
    else {
        expandedGroups.insert(state);
    }
    scheduleRebuild();
}

void TimelineWidget::onGroupMenu(const QString& key, const QPoint& globalPos)
{
    const int index = shownGroupIndex(key.toStdString());
    if (index < 0) {
        return;
    }

    const ShownGroup group = shownGroups[static_cast<std::size_t>(index)];
    const std::string lastMember = featureNames[static_cast<std::size_t>(group.last)];

    QMenu menu(this);
    QAction* toggleAction = menu.addAction(group.expanded ? tr("Collapse") : tr("Expand"));
    QAction* renameAction = menu.addAction(tr("Rename Group"));
    QAction* ungroupAction = menu.addAction(tr("Ungroup"));
    QAction* rollAction = nullptr;
    if (!bodyName.empty()) {
        menu.addSeparator();
        rollAction = menu.addAction(tr("Roll History Here"));
    }

    QAction* chosen = menu.exec(globalPos);
    if (!chosen) {
        return;
    }

    if (chosen == toggleAction) {
        onGroupToggle(key);
    }
    else if (chosen == renameAction) {
        renameGroup(group.key);
    }
    else if (chosen == ungroupAction) {
        ungroup(group.key);
    }
    else if (chosen == rollAction) {
        const int last = indexOfFeature(lastMember);
        if (last >= 0) {
            moveTo(last);
        }
    }
}

App::PropertyStringList* TimelineWidget::groupsProperty() const
{
    App::DocumentObject* body = currentBody();
    Gui::Application* app = Gui::Application::Instance;
    Gui::ViewProvider* provider = body && app ? app->getViewProvider(body) : nullptr;
    return provider
        ? freecad_cast<App::PropertyStringList*>(provider->getPropertyByName("TimelineGroups"))
        : nullptr;
}

std::vector<TimelineWidget::FeatureGroup> TimelineWidget::readGroups() const
{
    std::vector<FeatureGroup> groups;
    const App::PropertyStringList* prop = groupsProperty();
    if (!prop) {
        return groups;
    }

    for (const std::string& entry : prop->getValues()) {
        const QStringList fields
            = QString::fromUtf8(entry.c_str()).split(QLatin1Char(groupFieldSeparator));
        if (fields.size() < 2) {
            continue;
        }
        FeatureGroup group;
        group.key = fields[0].toStdString();
        group.label = fields[1].toStdString();
        for (qsizetype i = 2; i < fields.size(); ++i) {
            bool ok = false;
            const long id = fields[i].toLong(&ok);
            if (ok) {
                group.members.push_back(id);
            }
        }
        groups.push_back(std::move(group));
    }

    return groups;
}

void TimelineWidget::writeGroups(std::vector<FeatureGroup> groups)
{
    App::PropertyStringList* prop = groupsProperty();
    App::Document* doc = currentDocument();
    if (!prop || !doc) {
        return;
    }

    std::vector<std::string> values;
    for (FeatureGroup& group : groups) {
        std::erase_if(group.members, [doc](long id) { return doc->getObjectByID(id) == nullptr; });
        if (group.members.empty()) {
            continue;
        }
        std::string entry = group.key + groupFieldSeparator + group.label;
        for (long id : group.members) {
            entry += groupFieldSeparator + std::to_string(id);
        }
        values.push_back(std::move(entry));
    }

    if (values != prop->getValues()) {
        prop->setValues(values);
    }
}

std::string TimelineWidget::groupStateKey(const std::string& key) const
{
    return documentName + "/" + bodyName + "/" + key;
}

int TimelineWidget::shownGroupIndex(const std::string& key) const
{
    const int count = static_cast<int>(shownGroups.size());
    for (int i = 0; i < count; ++i) {
        if (shownGroups[static_cast<std::size_t>(i)].key == key) {
            return i;
        }
    }

    return -1;
}

bool TimelineWidget::groupCandidates(int clicked, int& first, int& last) const
{
    const int count = static_cast<int>(markers.size());
    if (clicked < 0 || clicked >= count) {
        return false;
    }

    const auto selected = [this](int i) {
        App::DocumentObject* obj = markers[i]->object();
        return obj != nullptr && Gui::Selection().isSelected(obj);
    };
    std::vector<int> chosen;
    if (selected(clicked)) {
        for (int i = 0; i < count; ++i) {
            if (selected(i)) {
                chosen.push_back(i);
            }
        }
    }
    else {
        chosen.push_back(clicked);
    }

    first = chosen.front();
    last = chosen.back();
    if (last - first + 1 != static_cast<int>(chosen.size())) {
        return false;
    }
    return std::none_of(chosen.begin(), chosen.end(), [this](int i) {
        return featureGroup[static_cast<std::size_t>(i)] >= 0;
    });
}

void TimelineWidget::createGroup(int first, int last)
{
    if (!groupsProperty()) {
        return;
    }

    std::vector<FeatureGroup> groups = readGroups();
    const auto keyTaken = [&groups](const std::string& key) {
        return std::any_of(groups.begin(), groups.end(), [&key](const FeatureGroup& group) {
            return group.key == key;
        });
    };
    const auto labelTaken = [&groups](const std::string& label) {
        return std::any_of(groups.begin(), groups.end(), [&label](const FeatureGroup& group) {
            return group.label == label;
        });
    };

    FeatureGroup group;
    int number = 1;
    while (keyTaken(std::to_string(number))) {
        ++number;
    }
    group.key = std::to_string(number);
    number = 1;
    while (labelTaken(tr("Group %1").arg(number).toStdString())) {
        ++number;
    }
    group.label = tr("Group %1").arg(number).toStdString();
    for (int i = first; i <= last; ++i) {
        if (App::DocumentObject* obj = markers[i]->object()) {
            group.members.push_back(obj->getID());
        }
    }
    groups.push_back(std::move(group));

    // Groups are a view of the history rather than part of the model, but they are
    // undone like any other change
    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Group timeline features"))
    );
    writeGroups(std::move(groups));
    Gui::Command::commitCommand(transaction);
    scheduleRebuild();
}

void TimelineWidget::ungroup(const std::string& key)
{
    std::vector<FeatureGroup> groups = readGroups();
    std::erase_if(groups, [&key](const FeatureGroup& group) { return group.key == key; });

    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Ungroup timeline features"))
    );
    writeGroups(std::move(groups));
    Gui::Command::commitCommand(transaction);
    expandedGroups.erase(groupStateKey(key));
    scheduleRebuild();
}

void TimelineWidget::renameGroup(const std::string& key)
{
    const auto byKey = [&key](const FeatureGroup& group) {
        return group.key == key;
    };
    std::vector<FeatureGroup> groups = readGroups();
    auto found = std::find_if(groups.begin(), groups.end(), byKey);
    if (found == groups.end()) {
        return;
    }

    const QString current = QString::fromUtf8(found->label.c_str());
    bool accepted = false;
    const QString typed = QInputDialog::getText(
        this,
        tr("Rename Group"),
        tr("New name:"),
        QLineEdit::Normal,
        current,
        &accepted
    );
    // Simplified, since a tab would split the stored entry
    const QString label = typed.simplified();
    if (!accepted || label.isEmpty() || label == current) {
        return;
    }

    // Read again, as the dialog ran an event loop of its own
    groups = readGroups();
    found = std::find_if(groups.begin(), groups.end(), byKey);
    if (found == groups.end()) {
        return;
    }
    found->label = label.toStdString();

    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Rename timeline group"))
    );
    writeGroups(std::move(groups));
    Gui::Command::commitCommand(transaction);
    scheduleRebuild();
}

int TimelineWidget::skipFoldedGroups(int index, int direction) const
{
    for (const ShownGroup& group : shownGroups) {
        if (!group.expanded && index >= group.first && index < group.last) {
            return direction < 0 ? group.first - 1 : group.last;
        }
    }

    return index;
}

void TimelineWidget::editFeature(const std::string& name)
{
    activateShownBody();

    App::DocumentObject* obj = resolve(name);
    if (!obj) {
        return;
    }

    Gui::Application* app = Gui::Application::Instance;
    if (!app) {
        return;
    }

    Gui::Document* guiDoc = app->getDocument(obj->getDocument());
    if (!guiDoc) {
        return;
    }

    Gui::ViewProvider* provider = guiDoc->getViewProvider(obj);
    if (!provider) {
        return;
    }

    try {
        guiDoc->setEdit(provider);
    }
    catch (const Base::Exception& e) {
        e.reportException();
    }
}

void TimelineWidget::renameFeature(const std::string& name)
{
    App::DocumentObject* obj = resolve(name);
    if (!obj) {
        return;
    }

    const QString current = QString::fromUtf8(obj->Label.getValue());
    bool accepted = false;
    const QString label = QInputDialog::getText(
        this,
        tr("Rename"),
        tr("New name:"),
        QLineEdit::Normal,
        current,
        &accepted
    );
    if (!accepted || label.isEmpty() || label == current) {
        return;
    }

    obj = resolve(name);
    if (!obj) {
        return;
    }

    try {
        const int tid = Gui::Command::openActiveDocumentCommand(std::string("Rename timeline feature"));
        Gui::Command::doCommand(
            Gui::Command::Doc,
            "%s.Label = u'%s'",
            Gui::Command::getObjectCmd(obj).c_str(),
            Base::Tools::escapeEncodeString(label.toStdString()).c_str()
        );
        Gui::Command::commitCommand(tid);
    }
    catch (const Base::Exception& e) {
        e.reportException();
    }
}

void TimelineWidget::deleteFeature(const std::string& name)
{
    activateShownBody();

    App::DocumentObject* obj = resolve(name);
    if (!obj || !obj->isAttachedToDocument()) {
        return;
    }

    Gui::Application* app = Gui::Application::Instance;
    if (!app) {
        return;
    }

    Gui::Selection().clearSelection();
    if (!Gui::Selection().addSelection(obj->getDocument()->getName(), obj->getNameInDocument())) {
        return;
    }

    app->commandManager().runCommandByName("Std_Delete");
}

void TimelineWidget::toggleSuppressed(const std::string& name)
{
    activateShownBody();

    App::DocumentObject* obj = resolve(name);
    auto* suppressible = obj ? obj->getExtensionByType<App::SuppressibleExtension>(true) : nullptr;
    if (!suppressible) {
        return;
    }

    int tid = App::NullTransaction;
    try {
        tid = Gui::Command::openActiveDocumentCommand(std::string("Toggle suppress"));
        Gui::Command::doCommand(
            Gui::Command::Doc,
            "App.getDocument('%s').getObject('%s').Suppressed = %s",
            obj->getDocument()->getName(),
            obj->getNameInDocument(),
            suppressible->Suppressed.getValue() ? "False" : "True"
        );
        // Everything after it changes, so it is rebuilt now rather than on the next edit
        Gui::Command::doCommand(
            Gui::Command::Doc,
            "App.getDocument('%s').recompute()",
            obj->getDocument()->getName()
        );
        Gui::Command::commitCommand(tid);
    }
    catch (const Base::Exception& e) {
        Gui::Command::abortCommand(tid);
        e.reportException();
    }
}

void TimelineWidget::moveTo(int index)
{
    const int count = static_cast<int>(markers.size());
    index = std::clamp(index, -1, count - 1);
    if (index == playheadIndex) {
        return;
    }

    // Rolling a body the user is only looking at makes it the one being worked on. That
    // happens outside the step's transaction, so undoing the step leaves the body active.
    if (!activateShownBody() && !bodyName.empty()) {
        return;
    }

    // One step is one undo entry
    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Roll history"))
    );

    if (rollStep(index)) {
        Gui::Command::commitCommand(transaction);
        return;
    }

    // The roll never happened, so neither should the half of it that may already have been
    // written; the rebuild puts the strip back in step with the document as it really is.
    Gui::Command::abortCommand(transaction);
    scheduleRebuild();
}

void TimelineWidget::scrubTo(int index)
{
    const int count = static_cast<int>(markers.size());
    index = std::clamp(index, -1, count - 1);
    if (index == playheadIndex) {
        return;
    }

    // Opened on the first step rather than on the press, so a click on the playhead that
    // moves nothing leaves no empty entry behind
    if (!scrubbing) {
        if (!activateShownBody() && !bodyName.empty()) {
            draggingPlayhead = false;
            return;
        }
        scrubTransaction = Gui::Command::openActiveDocumentCommand(
            std::string(QT_TRANSLATE_NOOP("Command", "Roll history"))
        );
        scrubbing = true;
    }

    if (!rollStep(index)) {
        // A step that failed takes the whole drag back to where it started
        Gui::Command::abortCommand(scrubTransaction);
        scrubbing = false;
        draggingPlayhead = false;
        scheduleRebuild();
    }
}

void TimelineWidget::endScrub()
{
    draggingPlayhead = false;
    playhead->setProperty("timelineDragging", false);
    playhead->update();
    if (scrubbing) {
        scrubbing = false;
        Gui::Command::commitCommand(scrubTransaction);
    }
}

bool TimelineWidget::rollStep(int index)
{
    // Only a solid feature can carry the tip, so a step onto a sketch or a datum lands on
    // the same model state and the document is left alone; the strip moves either way.
    const bool tipMoves = solidAtOrBefore(index) != tipIndex;

    // Moved before the roll rather than after it: the roll is answered by a rebuild a
    // timer tick later, and until then a second click has to see where the first one left
    // the playhead or it repeats the same step.
    playheadIndex = index;
    requestedPlayhead = index;
    positionPlayhead();
    applyStates();

    // The tip goes first on purpose: Visibility is a NoModify property, which never opens
    // a transaction of its own and is only recorded once one is already running, so the
    // writes that do open one have to come before it.
    if (tipMoves && !rollTo(index)) {
        return false;
    }

    // A drag holds off the rebuild that would read the new tip back, and its next step
    // has to know where this one left it
    tipIndex = solidAtOrBefore(index);
    applyRollbackVisibility();
    applyStates();
    return true;
}

bool TimelineWidget::rollTo(int index)
{
    App::DocumentObject* body = currentBody();
    if (!body) {
        return false;
    }

    auto* tipProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("Tip"));
    if (!tipProp) {
        return false;
    }

    // Only a solid feature can carry the tip, so a sketch or a datum rolls to the solid
    // feature it sits behind. Nothing before the first solid feature means the history has
    // been rolled off its start, which leaves the body without a tip at all.
    App::DocumentObject* target = nullptr;
    const int solid = solidAtOrBefore(index);
    if (solid >= 0 && solid < static_cast<int>(featureNames.size())) {
        target = resolve(featureNames[static_cast<std::size_t>(solid)]);
        if (!target || !target->isAttachedToDocument()) {
            return false;
        }
    }

    if (tipProp->getValue() == target) {
        return false;
    }

    // What PartDesign_MoveTip does, without its own transaction: this step owns the one
    // that is already open, and running the command by name would commit it halfway
    // through and leave the visibility changes below in an entry of their own.
    try {
        if (target) {
            FCMD_OBJ_CMD(body, "Tip = " << Gui::Command::getObjectCmd(target));
            // Showing the new tip is what takes the solids after it off the screen.
            FCMD_OBJ_SHOW(target);
        }
        else {
            FCMD_OBJ_CMD(body, "Tip = None");

            // A body with no tip builds nothing, so the solid that was on screen has to
            // be taken off it by hand: there is no feature left to show in its place.
            // CmdPartDesignMoveTip walks the body's Group, which the base feature is not
            // part of, so the base feature is left showing here too.
            App::DocumentObject* baseFeature = nullptr;
            auto* baseProp = freecad_cast<App::PropertyLink*>(body->getPropertyByName("BaseFeature"));
            if (baseProp) {
                baseFeature = baseProp->getValue();
            }

            for (int i : solidIndices) {
                App::DocumentObject* obj = resolve(featureNames[static_cast<std::size_t>(i)]);
                if (obj && obj != baseFeature && obj->isAttachedToDocument()
                    && obj->Visibility.getValue()) {
                    FCMD_OBJ_HIDE(obj);
                }
            }
        }

        FCMD_DOC_CMD(body->getDocument(), "recompute()");
    }
    catch (const Base::Exception& e) {
        e.reportException();
        return false;
    }

    return true;
}

void TimelineWidget::stepBack()
{
    moveTo(skipFoldedGroups(playheadIndex - 1, -1));
}

void TimelineWidget::stepForward()
{
    moveTo(skipFoldedGroups(playheadIndex + 1, 1));
}

void TimelineWidget::rollToStart()
{
    moveTo(-1);
}

void TimelineWidget::rollToEnd()
{
    moveTo(static_cast<int>(markers.size()) - 1);
}

bool TimelineWidget::dragInProgress() const
{
    return draggingPlayhead || !pressedItem.isNull();
}

int TimelineWidget::dropBoundaryAt(const QPoint& stripPos) const
{
    for (const StripItem& item : stripItems) {
        if (item.first >= dragFirst && item.last <= dragLast) {
            continue;
        }
        if (item.widget->geometry().center().x() > stripPos.x()) {
            return item.first;
        }
    }

    return static_cast<int>(featureNames.size());
}

TimelineWidget::MovePlan TimelineWidget::planMove(int first, int last, int boundary, bool wholeGroup)
{
    MovePlan plan;
    const int count = static_cast<int>(featureNames.size());
    if (first < 0 || last < first || last >= count || boundary < 0 || boundary > count
        || (boundary >= first && boundary <= last + 1)) {
        plan.unchanged = true;
        return plan;
    }

    App::DocumentObject* body = currentBody();
    auto* groupProp = body ? freecad_cast<App::PropertyLinkList*>(body->getPropertyByName("Group"))
                           : nullptr;
    if (!groupProp) {
        plan.unchanged = true;
        return plan;
    }

    // The base feature is what the body starts from, and it is not part of the Group at all
    if (hasBaseFeature && first == 0) {
        plan.refusal = tr("The base feature of a body cannot be moved");
        return plan;
    }
    if (hasBaseFeature && boundary == 0) {
        plan.refusal = tr("Nothing can move in front of the base feature of a body");
        return plan;
    }
    // One level of grouping only
    if (wholeGroup && boundary > 0 && boundary < count) {
        const int before = featureGroup[static_cast<std::size_t>(boundary - 1)];
        if (before >= 0 && before == featureGroup[static_cast<std::size_t>(boundary)]) {
            plan.refusal = tr("A group cannot go inside another group");
            return plan;
        }
    }

    std::unordered_set<const App::DocumentObject*> moving;
    for (int i = first; i <= last; ++i) {
        App::DocumentObject* obj = resolve(featureNames[static_cast<std::size_t>(i)]);
        if (!obj) {
            plan.unchanged = true;
            return plan;
        }
        for (App::DocumentObject* member : withSteps(obj)) {
            moving.insert(member);
        }
    }

    const std::vector<App::DocumentObject*> group = groupProp->getValues();
    std::vector<App::DocumentObject*> remaining;
    for (App::DocumentObject* obj : group) {
        if (moving.count(obj) > 0) {
            plan.moving.push_back(obj);
        }
        else {
            remaining.push_back(obj);
        }
    }
    if (plan.moving.size() != moving.size()) {
        plan.unchanged = true;
        return plan;
    }

    // In front of the feature after the drop, and in front of any steps of its own the
    // Group holds before it, so a MultiTransform keeps its steps together
    std::size_t insertAt = remaining.size();
    if (boundary < count) {
        App::DocumentObject* next = resolve(featureNames[static_cast<std::size_t>(boundary)]);
        if (!next) {
            plan.unchanged = true;
            return plan;
        }
        for (App::DocumentObject* member : withSteps(next)) {
            const auto found = std::find(remaining.begin(), remaining.end(), member);
            if (found != remaining.end()) {
                insertAt = std::min(insertAt, static_cast<std::size_t>(found - remaining.begin()));
            }
        }
        if (insertAt == remaining.size()) {
            plan.unchanged = true;
            return plan;
        }
        plan.before = remaining[insertAt];
    }

    std::vector<App::DocumentObject*> order = remaining;
    order.insert(
        order.begin() + static_cast<std::ptrdiff_t>(insertAt),
        plan.moving.begin(),
        plan.moving.end()
    );

    if (dragDependencies.empty()) {
        for (App::DocumentObject* obj : group) {
            collectDependencies(obj, body, dragDependencies[obj]);
        }
    }

    std::unordered_map<const App::DocumentObject*, std::size_t> position;
    for (std::size_t i = 0; i < order.size(); ++i) {
        position[order[i]] = i;
    }

    // Only a pair the move turns round can break, so pairs on the same side are skipped
    const auto label = [](const App::DocumentObject* obj) {
        return QString::fromUtf8(obj->Label.getValue());
    };
    for (std::size_t i = 0; i < order.size(); ++i) {
        const App::DocumentObject* obj = order[i];
        const auto found = dragDependencies.find(obj);
        if (found == dragDependencies.end()) {
            continue;
        }
        const bool objMoves = moving.count(obj) > 0;
        for (const App::DocumentObject* dependency : found->second) {
            const auto at = position.find(dependency);
            if (at == position.end() || (moving.count(dependency) > 0) == objMoves || at->second < i) {
                continue;
            }
            plan.refusal = objMoves
                ? tr("%1 cannot move in front of %2, which it is built on")
                      .arg(label(obj), label(dependency))
                : tr("%1 cannot move past %2, which is built on it").arg(label(dependency), label(obj));
            return plan;
        }
    }

    return plan;
}

void TimelineWidget::moveFeatures(int first, int last, int boundary, bool wholeGroup)
{
    const MovePlan plan = planMove(first, last, boundary, wholeGroup);
    if (plan.unchanged) {
        return;
    }
    if (!plan.refusal.isEmpty()) {
        if (Gui::MainWindow* window = Gui::getMainWindow()) {
            window->showMessage(plan.refusal, refusalMessageTimeout);
        }
        return;
    }

    if (!activateShownBody()) {
        return;
    }
    App::DocumentObject* body = currentBody();
    if (!body) {
        return;
    }

    // The playhead stays behind the feature it was behind, so what was rolled back stays
    // rolled back. One at the end stays at the end, taking the moved features in with it.
    const int count = static_cast<int>(featureNames.size());
    const bool atEnd = playheadIndex >= count - 1;
    std::string anchor;
    for (int i = playheadIndex; i >= 0; --i) {
        if (i < first || i > last) {
            anchor = featureNames[static_cast<std::size_t>(i)];
            break;
        }
    }

    // What PartDesign_MoveFeatureInTree does: out of the Group and back in at the new
    // place, which has the body rewire the BaseFeature of every solid on the way
    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Move feature in timeline"))
    );
    try {
        for (App::DocumentObject* obj : plan.moving) {
            FCMD_OBJ_CMD(body, "removeObject(" << Gui::Command::getObjectCmd(obj) << ")");
        }
        App::DocumentObject* previous = nullptr;
        for (App::DocumentObject* obj : plan.moving) {
            const std::string moved = Gui::Command::getObjectCmd(obj);
            const std::string after = previous ? Gui::Command::getObjectCmd(previous) : std::string();
            const std::string before = plan.before ? Gui::Command::getObjectCmd(plan.before)
                                                   : std::string("None");
            if (previous) {
                FCMD_OBJ_CMD(body, "insertObject(" << moved << ", " << after << ", True)");
            }
            else {
                FCMD_OBJ_CMD(body, "insertObject(" << moved << ", " << before << ", False)");
            }
            previous = obj;
        }

        // A feature dropped between two members of an unfolded group joins it, and one
        // dropped anywhere else leaves the group it was in. Read off the strip as it was.
        if (!wholeGroup && first == last) {
            int joined = -1;
            if (boundary > 0 && boundary < count) {
                const int before = featureGroup[static_cast<std::size_t>(boundary - 1)];
                if (before >= 0 && before == featureGroup[static_cast<std::size_t>(boundary)]) {
                    joined = before;
                }
            }
            App::DocumentObject* obj = resolve(featureNames[static_cast<std::size_t>(first)]);
            if (obj && joined != featureGroup[static_cast<std::size_t>(first)]) {
                std::vector<FeatureGroup> groups = readGroups();
                for (FeatureGroup& group : groups) {
                    std::erase(group.members, obj->getID());
                    if (joined >= 0
                        && group.key == shownGroups[static_cast<std::size_t>(joined)].key) {
                        group.members.push_back(obj->getID());
                    }
                }
                writeGroups(std::move(groups));
            }
        }

        // Read back now, inside the step, so the tip can be put where the playhead goes
        rebuild();
        const int target = atEnd ? static_cast<int>(featureNames.size()) - 1
                                 : (anchor.empty() ? -1 : indexOfFeature(anchor));
        const bool tipMoves = solidAtOrBefore(target) != tipIndex;
        playheadIndex = target;
        requestedPlayhead = target;
        if (!tipMoves || !rollTo(target)) {
            FCMD_DOC_CMD(body->getDocument(), "recompute()");
        }
        tipIndex = solidAtOrBefore(target);

        positionPlayhead();
        applyRollbackVisibility();
        applyStates();
        Gui::Command::commitCommand(transaction);
    }
    catch (const Base::Exception& e) {
        Gui::Command::abortCommand(transaction);
        e.reportException();
    }

    scheduleRebuild();
}

void TimelineWidget::updateMarkerDrag(const QPoint& globalPos)
{
    dropBoundary = dropBoundaryAt(strip->mapFromGlobal(globalPos));
    const MovePlan plan = planMove(dragFirst, dragLast, dropBoundary, dragWholeGroup);
    if (plan.unchanged || stripItems.empty()) {
        dropIndicator->hide();
        if (pressedItem) {
            pressedItem->setCursor(Qt::ClosedHandCursor);
        }
        return;
    }

    // In front of the item the drop lands before, or after the last one
    int x = 0;
    for (const StripItem& item : stripItems) {
        if (item.first >= dragFirst && item.last <= dragLast) {
            continue;
        }
        if (item.first >= dropBoundary) {
            x = item.widget->geometry().left() - markerSpacing;
            break;
        }
        x = item.widget->geometry().right() + markerSpacing;
    }

    const bool valid = plan.refusal.isEmpty();
    dropIndicator->setProperty("dropValid", valid);
    dropIndicator->setToolTip(plan.refusal);
    dropIndicator->setStyleSheet(
        QStringLiteral("background-color: %1;")
            .arg(valid ? palette().color(QPalette::Highlight).name() : QStringLiteral("#d93025"))
    );
    dropIndicator->setGeometry(x - dropIndicatorWidth / 2, 0, dropIndicatorWidth, strip->height());
    dropIndicator->show();
    dropIndicator->raise();
    if (pressedItem) {
        pressedItem->setCursor(valid ? Qt::ClosedHandCursor : Qt::ForbiddenCursor);
    }
}

void TimelineWidget::finishMarkerDrag(const QPoint& globalPos)
{
    const int first = dragFirst;
    const int last = dragLast;
    const bool wholeGroup = dragWholeGroup;
    const int boundary = dropBoundaryAt(strip->mapFromGlobal(globalPos));
    endMarkerDrag();
    moveFeatures(first, last, boundary, wholeGroup);
    dragDependencies.clear();
}

void TimelineWidget::endMarkerDrag()
{
    if (pressedItem) {
        pressedItem->unsetCursor();
    }
    pressedItem = nullptr;
    draggingMarker = false;
    dragFirst = -1;
    dragLast = -1;
    dropBoundary = -1;
    dragWholeGroup = false;
    dropIndicator->hide();
}

int TimelineWidget::defaultPlayhead() const
{
    // Everything up to the solid the tip does not yet include is part of the state the
    // model is in, so a sketch made after the tip does not read as rolled back.
    int position = static_cast<int>(markers.size()) - 1;
    for (int solid : solidIndices) {
        if (solid > tipIndex) {
            position = solid - 1;
            break;
        }
    }

    // A feature the roll took off the screen has to stay behind the playhead, or the very
    // next rebuild would read it as reached, show it again and drop it from the list. That
    // is what used to lose a rollback on a reload, on the way back from another body, or
    // on any unrelated rebuild, since requestedPlayhead only survives a single one.
    const App::PropertyStringList* hiddenProperty = rollbackHiddenProperty();
    if (hiddenProperty) {
        for (const std::string& name : hiddenProperty->getValues()) {
            const int index = indexOfFeature(name);
            if (index >= 0) {
                position = std::min(position, index - 1);
            }
        }
    }

    // Only a solid carries the tip, so the leftmost position that still resolves to the
    // current tip is the tip itself. A list left over from a roll the tip has since been
    // moved past by hand must not drag the playhead behind it.
    return std::max(position, tipIndex);
}

void TimelineWidget::onSelectionChanged(const Gui::SelectionChanges& msg)
{
    // Only a selection that adds something points at a body. Clearing or shrinking the
    // selection, or selecting something outside every body, leaves the strip where it is.
    // So does a pick while an edit is open (another body's face for "up to face", an edge
    // for external geometry): that is input to the edit, and the strip stays on the edited
    // body after it closes too.
    Gui::Application* app = Gui::Application::Instance;
    const bool editing = app && app->editDocument();
    if (!editing
        && (msg.Type == Gui::SelectionChanges::AddSelection
            || msg.Type == Gui::SelectionChanges::SetSelection)) {
        App::Document* doc = App::GetApplication().getDocument(msg.pDocName);
        App::DocumentObject* obj = nullptr;
        std::string subName;
        if (doc && *msg.pObjectName) {
            obj = doc->getObject(msg.pObjectName);
            subName = msg.pSubName;
        }
        else if (doc) {
            // A selection set in one go names no object, so its last entry stands for it
            const auto selection
                = Gui::Selection().getSelection(msg.pDocName, Gui::ResolveMode::NoResolve);
            if (!selection.empty()) {
                obj = selection.back().pObject;
                subName = selection.back().SubName ? selection.back().SubName : "";
            }
        }

        // A pick in 3D names the top object and the path under it: Body + "Pad.Face3"
        if (obj && !subName.empty()) {
            if (App::DocumentObject* sub = obj->getSubObject(subName.c_str())) {
                obj = sub;
            }
        }

        App::DocumentObject* body = bodyOf(obj);
        if (body
            && (body->getNameInDocument() != followedBodyName
                || body->getDocument()->getName() != followedDocumentName)) {
            followedBodyName = body->getNameInDocument();
            // Not the selection's own document: a pick through a link can reach into another
            followedDocumentName = body->getDocument()->getName();
            if (followedBodyName != bodyName || followedDocumentName != documentName) {
                scheduleRebuild();
            }
        }
    }

    applyStates();
}

#include "moc_TimelineWidget.cpp"
