// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2013 Jan Rheinländer                                    *
 *                                   <jrheinlaender@users.sourceforge.net> *
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


#pragma once

#include <App/DocumentObserver.h>
#include <Gui/Selection/Selection.h>
#include "ViewProvider.h"

#include "TaskFeatureAddSubParameters.h"
#include "EnumFlags.h"

class QLineEdit;

namespace App
{
class Property;
class PropertyLinkSub;
class PropertyLinkSubList;
}  // namespace App

namespace PartDesign
{
class ProfileBased;
}

class QLabel;
class QToolButton;

namespace PartDesignGui
{

/// Makes the next profile panel to open start with region picking on, adding to what the
/// feature was started on. Set around the creation of a feature picked from a region.
void pickRegionsOnOpen(bool on);

/** Fusion style profile row.
 *
 * Closed regions bounded by the sketch curves are precomputed by
 * Sketcher::SketchObject as InternalFace1..N. This widget lets the user pick those
 * regions directly in the 3D view and writes them into the feature's Profile link.
 */
class ProfileSelectionWidget: public QWidget, public Gui::SelectionObserver
{
    Q_OBJECT

public:
    explicit ProfileSelectionWidget(PartDesign::ProfileBased* feature, QWidget* parent = nullptr);
    ~ProfileSelectionWidget() override;

    /// Number of closed regions the profile provides, 0 if it is not a sketch with regions.
    static int countRegions(App::DocumentObject* profile);

    bool isPickingActive() const;
    void updateSummary();

    /// The feature is only standing on a region until one is deliberately picked, so the
    /// first pick replaces it rather than adding to it.
    void setProfileProvisional(bool value)
    {
        provisional = value;
    }

public Q_SLOTS:
    void setPickingActive(bool active);

Q_SIGNALS:
    void profileChanged();
    /// Picking has been switched off, so whoever owns the hint row can have it back.
    void pickingFinished();

private:
    void onSelectionChanged(const Gui::SelectionChanges& msg) override;
    void toggleRegion(const std::string& subName);
    PartDesign::ProfileBased* getFeature() const;
    Gui::ViewProvider* getProfileViewProvider() const;

    App::DocumentObjectWeakPtrT feature;
    QLabel* summaryLabel;
    QToolButton* pickButton;
    bool provisional {false};
    bool profileWasVisible {false};
};

/// Convenience class to collect common methods for all SketchBased features
class TaskSketchBasedParameters: public TaskFeatureAddSubParameters, public Gui::SelectionObserver
{
    Q_OBJECT

public:
    TaskSketchBasedParameters(
        PartDesignGui::ViewProvider* vp,
        QWidget* parent,
        const std::string& pixmapname,
        const QString& parname
    );
    ~TaskSketchBasedParameters() override;

protected:
    void onSelectionChanged(const Gui::SelectionChanges& msg) override = 0;
    const QString onAddSelection(const Gui::SelectionChanges& msg, App::PropertyLinkSub& prop);
    virtual void startReferenceSelection(App::DocumentObject* profile, App::DocumentObject* base);
    virtual void finishReferenceSelection(App::DocumentObject* profile, App::DocumentObject* base);
    /*!
     * \brief onSelectReference
     * Start reference selection mode to allow one to select objects of the type defined
     * with \a AllowSelectionFlags.
     * If AllowSelection::NONE is passed the selection mode is finished.
     */
    void onSelectReference(AllowSelectionFlags);
    void exitSelectionMode();
    QVariant setUpToFace(const QString& text);
    /// Try to find the name of a feature with the given label.
    /// For faster access a suggested name can be tested, first.
    QVariant objectNameByLabel(const QString& label, const QVariant& suggest) const;

    QString getFaceReference(const QString& obj, const QString& sub) const;
    void updateReferenceName(
        QLineEdit* lineEdit,
        const App::PropertyLinkSub& reference,
        const QString& emptyPlaceholder
    );
    /// Create a label for the 2D feature: the objects name if it's already 2D,
    /// or the subelement's name if the object is a solid.
    QString make2DLabel(const App::DocumentObject* section, const std::vector<std::string>& subValues);

    ProfileSelectionWidget* getProfileSelectionWidget() const
    {
        return profileWidget;
    }

private:
    Gui::ViewProvider* previouslyVisibleViewProvider {nullptr};
    ProfileSelectionWidget* profileWidget {nullptr};
    const App::DocumentObject* profileRowOwner {nullptr};
};

class TaskDlgSketchBasedParameters: public PartDesignGui::TaskDlgFeatureParameters
{
    Q_OBJECT

public:
    explicit TaskDlgSketchBasedParameters(PartDesignGui::ViewProvider* vp);
    ~TaskDlgSketchBasedParameters() override;

public:
    /// is called by the framework if the dialog is accepted (Ok)
    bool accept() override;
    /// is called by the framework if the dialog is rejected (Cancel)
    bool reject() override;
};

}  // namespace PartDesignGui
