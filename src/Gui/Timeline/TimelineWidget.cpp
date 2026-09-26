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
#include <App/Property.h>
#include <App/PropertyLinks.h>
#include <App/PropertyStandard.h>
#include <Base/Exception.h>
#include <Base/Tools.h>
#include <Base/Type.h>
#include <Gui/ActiveObjectList.h>
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/Document.h>
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
constexpr int playheadWidth = 3;
constexpr int stepButtonExtent = 20;
constexpr int stepIconExtent = 12;
constexpr int scrollBarThickness = 8;
// Long enough that a slider drag or a batch of property changes collapses into
// a single update, short enough to feel immediate.
constexpr int updateDelay = 120;

const char* const bodyTypeName = "PartDesign::Body";
const char* const solidTypeName = "PartDesign::Feature";
const char* const partFeatureTypeName = "Part::Feature";
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

    playhead = new QWidget(strip);
    playhead->setObjectName(QStringLiteral("TimelinePlayhead"));
    playhead->setAttribute(Qt::WA_StyledBackground, true);
    playhead->setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Expanding);
    playhead->setFixedWidth(playheadWidth);
    playhead->setCursor(Qt::SizeHorCursor);
    playhead->setToolTip(tr("Drag to roll the model history back and forward"));
    playhead->installEventFilter(this);
    playhead->hide();

    emptyLabel = new QLabel(tr("No feature history"), strip);
    emptyLabel->setObjectName(QStringLiteral("TimelineEmptyLabel"));
    emptyLabel->hide();

    outerLayout->addWidget(controls, 0, Qt::AlignVCenter);
    outerLayout->addWidget(scrollArea, 1);

    // The scroll bar's own extent has to be reserved whether or not it is showing,
    // and the theme's is taller than the markers themselves, so it is pinned to
    // something proportionate instead. Fusion's timeline is a thin strip.
    scrollArea->horizontalScrollBar()->setFixedHeight(scrollBarThickness);
    setFixedHeight(TimelineMarker::tileSize().height() + 2 * stripMargin + scrollBarThickness);
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
            trackedDocument = nullptr;
        }
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
    trackedDocument = doc;

    if (doc) {
        connActiveObject = doc->signalActivatedViewProvider.connect(
            [this](const Gui::ViewProviderDocumentObject*, const char*) { scheduleRebuild(); }
        );
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
    featureNames.clear();
    solidIndices.clear();
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
        body = activeBody(guiDoc);
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

    for (int i = 0; i < count; ++i) {
        stripLayout->addWidget(markers[i]);
        markers[i]->show();
    }

    if (count == 0) {
        stripLayout->addWidget(emptyLabel);
        emptyLabel->show();
    }

    stripLayout->addStretch(1);

    positionPlayhead();
    applyRollbackVisibility();
    applyStates();
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

    // The markers occupy the first positions of the layout and the stretch trails them, so
    // the slot in front of the marker after the playhead is the playhead's own.
    stripLayout->removeWidget(playhead);
    stripLayout->insertWidget(playheadIndex + 1, playhead);
    playhead->show();
}

void TimelineWidget::refreshMarkers()
{
    for (TimelineMarker* marker : markers) {
        marker->refresh();
    }

    applyStates();
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
    const int count = static_cast<int>(markers.size());
    for (int i = 0; i < count; ++i) {
        if (markers[i]->geometry().center().x() <= stripPos.x()) {
            index = i;
        }
    }

    return index;
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
    // A focused marker or step button is offered the key before the strip is, so the
    // claim has to be made here as well as in event() above.
    if (event->type() == QEvent::ShortcutOverride && keyAction(static_cast<QKeyEvent*>(event))) {
        event->accept();
        return true;
    }

    if (event->type() == QEvent::KeyPress && handleKey(static_cast<QKeyEvent*>(event))) {
        return true;
    }

    if (watched != playhead) {
        return QWidget::eventFilter(watched, event);
    }

    switch (event->type()) {
        case QEvent::MouseButtonPress:
            if (static_cast<QMouseEvent*>(event)->button() == Qt::LeftButton) {
                draggingPlayhead = true;
                return true;
            }
            return false;
        case QEvent::MouseMove:
            return draggingPlayhead;
        case QEvent::MouseButtonRelease: {
            if (!draggingPlayhead) {
                return false;
            }
            draggingPlayhead = false;
            moveTo(markerIndexAt(strip->mapFromGlobal(QCursor::pos())));
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

    QMenu menu(this);
    QAction* editAction = menu.addAction(tr("Edit"));
    QAction* renameAction = menu.addAction(tr("Rename"));
    QAction* deleteAction = menu.addAction(tr("Delete"));
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
    else if (chosen == rollAction) {
        moveTo(index);
    }
}

void TimelineWidget::editFeature(const std::string& name)
{
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

void TimelineWidget::moveTo(int index)
{
    const int count = static_cast<int>(markers.size());
    index = std::clamp(index, -1, count - 1);
    if (index == playheadIndex) {
        return;
    }

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

    // One step is one undo entry. The tip goes first on purpose: Visibility is a NoModify
    // property, which never opens a transaction of its own and is only recorded once one
    // is already running, so the writes that do open one have to come before it.
    const int transaction = Gui::Command::openActiveDocumentCommand(
        std::string(QT_TRANSLATE_NOOP("Command", "Roll history"))
    );

    if (!tipMoves || rollTo(index)) {
        applyRollbackVisibility();
        Gui::Command::commitCommand(transaction);
        return;
    }

    // The roll never happened, so neither should the half of it that may already have been
    // written; the rebuild puts the strip back in step with the document as it really is.
    Gui::Command::abortCommand(transaction);
    scheduleRebuild();
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
    moveTo(playheadIndex - 1);
}

void TimelineWidget::stepForward()
{
    moveTo(playheadIndex + 1);
}

void TimelineWidget::rollToStart()
{
    moveTo(-1);
}

void TimelineWidget::rollToEnd()
{
    moveTo(static_cast<int>(markers.size()) - 1);
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
    Q_UNUSED(msg)

    applyStates();
}

#include "moc_TimelineWidget.cpp"
