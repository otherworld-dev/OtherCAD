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


#pragma once

#include <string>
#include <vector>

#include <QList>
#include <QPoint>
#include <QString>
#include <QWidget>

#include <fastsignals/signal.h>

#include <FCGlobal.h>
#include <Gui/Selection/Selection.h>

class QEvent;
class QHBoxLayout;
class QKeyEvent;
class QLabel;
class QTimer;
class QToolButton;

namespace App
{
class Document;
class DocumentObject;
class PropertyStringList;
}  // namespace App

namespace Gui
{
class Document;

namespace Timeline
{

class TimelineMarker;

/**
 * Fusion style history strip: one marker per modelling feature of a body, in
 * creation order, with a playhead that rolls the model back by moving the tip of
 * the body.
 *
 * The strip is filled from a PartDesign body of the active document: the body of
 * the object in edit while an edit is open, otherwise the body the user last
 * pointed at, by selecting something in it or by activating it, and failing both
 * the active body. A body that is not the active one is labelled as such, and is
 * activated before anything on the strip acts on it.
 *
 * PartDesign is not linked from Gui, so the body is recognised by type name and
 * read and written through its Group, Tip and BaseFeature properties, which
 * keeps the timeline out of the module dependency graph. Outside a body the
 * strip falls back to the Part features of the document in dependency order,
 * which has no tip and therefore no playhead.
 *
 * One step of the playhead is one undo entry: the tip and the visibility of the
 * sketches and datums the step rolls past are written inside a single
 * transaction. Which features the strip hid is remembered in the RollbackHidden
 * property of the body's view provider rather than in the widget, so it is saved
 * with the document and survives both a reload and a switch to another body.
 *
 * Nothing here holds a document object across event loop turns: features are
 * remembered by internal name and resolved again on use, and every rebuild is
 * deferred through a timer so that it never runs inside a document signal.
 * @author FuCad contributors
 */
class GuiExport TimelineWidget: public QWidget, public Gui::SelectionObserver
{
    Q_OBJECT

public:
    explicit TimelineWidget(QWidget* parent = nullptr);
    ~TimelineWidget() override;

public Q_SLOTS:
    /// Move the playhead one marker back, towards the start of the history.
    void stepBack();
    /// Move the playhead one marker forward, towards the end of the history.
    void stepForward();
    /// Roll the whole history back, leaving the body without a tip.
    void rollToStart();
    /// Roll the history forward again, up to and including the last feature.
    void rollToEnd();

protected:
    bool event(QEvent* event) override;
    bool eventFilter(QObject* watched, QEvent* event) override;
    void keyPressEvent(QKeyEvent* event) override;
    /// Observer message from the Selection
    void onSelectionChanged(const Gui::SelectionChanges& msg) override;

private:
    /// Not a playhead position, since -1 is the state before the first feature.
    static constexpr int noPlayheadRequest = -2;

    void setupUi();
    void connectDocumentSignals();
    void trackDocument(Gui::Document* doc);

    void scheduleRebuild();
    void scheduleRefresh();
    void onTimeout();

    void rebuild();
    void clearStrip();
    void refreshMarkers();
    void applyStates();
    /// Shows the "(inactive)" label when the body on the strip is not the active one
    void updateBodyLabel();

    App::Document* currentDocument() const;
    App::DocumentObject* currentBody() const;
    App::DocumentObject* resolve(const std::string& name) const;
    App::DocumentObject* activeBody(Gui::Document* guiDoc) const;
    /// The body obj belongs to, the body itself, or nullptr when it is in none
    App::DocumentObject* bodyOf(App::DocumentObject* obj) const;
    /// The body of the object in edit, or nullptr when no edit is open
    App::DocumentObject* editedBody(Gui::Document* guiDoc) const;
    /// The body the strip shows: the edited one, the followed one, or the active one
    App::DocumentObject* shownBody(Gui::Document* guiDoc) const;
    /// Makes the body on the strip the active one, if it is not; false when that failed
    bool activateShownBody();

    void collectBodyFeatures(App::DocumentObject* body, std::vector<App::DocumentObject*>& features) const;
    void collectDocumentFeatures(App::Document* doc, std::vector<App::DocumentObject*>& features) const;

    int markerIndexAt(const QPoint& stripPos) const;
    int indexOfFeature(const std::string& name) const;
    int solidAtOrBefore(int index) const;
    bool isSolidIndex(int index) const;
    /// Hide the sketches and datums the playhead has not reached yet, and put back the
    /// ones it has. Solids are left to the tip, which already hides what comes after it.
    void applyRollbackVisibility();
    /// Where the names of the features the rollback hid are kept: a hidden string list on
    /// the view provider of the active body, or nullptr when there is no body to ask.
    App::PropertyStringList* rollbackHiddenProperty() const;
    /// The rightmost playhead position that still resolves to the current tip, which is
    /// where the playhead belongs whenever it has not been put somewhere by hand.
    int defaultPlayhead() const;

    void onMarkerSelect(const QString& feature);
    void onMarkerEdit(const QString& feature);
    void onMarkerMenu(const QString& feature, const QPoint& globalPos);

    void editFeature(const std::string& name);
    void renameFeature(const std::string& name);
    void deleteFeature(const std::string& name);
    void toggleSuppressed(const std::string& name);

    void positionPlayhead();
    void moveTo(int index);
    bool rollTo(int index);
    /// One of the slots above, which is all a key of the strip's ever does.
    using RollAction = void (TimelineWidget::*)();
    /// What the key rolls, or nullptr when the key is not one of the strip's. Asked twice:
    /// once to claim the key from a command shortcut that would otherwise answer it first,
    /// and again when the press itself arrives.
    RollAction keyAction(const QKeyEvent* event) const;
    /// Answers the timeline's own keys wherever they arrive: on the widget itself, or on
    /// the marker or step button Tab has landed on, both of which are filtered so that the
    /// key never has to travel to be answered. True when one was used.
    bool handleKey(QKeyEvent* event);

    QWidget* strip {nullptr};
    QHBoxLayout* stripLayout {nullptr};
    QWidget* playhead {nullptr};
    QLabel* emptyLabel {nullptr};
    /// Names the body on the strip when it is not the active one
    QLabel* bodyLabel {nullptr};
    QToolButton* stepBackButton {nullptr};
    QToolButton* stepForwardButton {nullptr};
    QTimer* updateTimer {nullptr};

    QList<TimelineMarker*> markers;
    std::vector<std::string> featureNames;
    /// Indices into featureNames of the features that may become the tip.
    std::vector<int> solidIndices;
    std::string documentName;
    std::string bodyName;
    /// The body the user last pointed at by selecting in it, by internal name. Cleared when
    /// a body is activated by hand, which is pointing at the active one.
    std::string followedBodyName;
    std::string followedDocumentName;
    int tipIndex {-1};
    /// The last feature the playhead has passed, so -1 is the state before the first one.
    /// The arrows move it one marker at a time. Only a solid feature can carry the tip, so
    /// a step onto a sketch or a datum leaves the tip on the solid behind it and changes
    /// nothing but the strip; without this the arrows could only jump between solids.
    int playheadIndex {-1};
    /// Survives the rebuild that moving the tip triggers, so a step is not snapped back
    /// onto the tip. noPlayheadRequest when the playhead has not been put anywhere by hand.
    int requestedPlayhead {noPlayheadRequest};

    Gui::Document* trackedDocument {nullptr};
    bool pendingRebuild {false};
    bool draggingPlayhead {false};

    fastsignals::scoped_connection connActiveDocument;
    fastsignals::scoped_connection connNewDocument;
    fastsignals::scoped_connection connDeleteDocument;
    fastsignals::scoped_connection connNewObject;
    fastsignals::scoped_connection connDeletedObject;
    fastsignals::scoped_connection connChangedObject;
    fastsignals::scoped_connection connRelabelObject;
    fastsignals::scoped_connection connActivateView;
    fastsignals::scoped_connection connCloseView;
    /// Reconnected on every document switch, so only one document is observed.
    fastsignals::scoped_connection connActiveObject;
    fastsignals::scoped_connection connInEdit;
    fastsignals::scoped_connection connResetEdit;

    Q_DISABLE_COPY(TimelineWidget)
};

}  // namespace Timeline
}  // namespace Gui
