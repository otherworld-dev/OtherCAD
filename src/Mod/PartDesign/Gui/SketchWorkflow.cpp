// SPDX-License-Identifier: LGPL-2.1-or-later

/**************************************************************************
 *   Copyright (c) 2022 Werner Mayer <wmayer[at]users.sourceforge.net>     *
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

#include <TopoDS.hxx>
#include <TopoDS_Face.hxx>
#include <boost/signals2.hpp>
#include <map>
#include <string>
#include <vector>
#include <QApplication>
#include <QMessageBox>


#include "SketchWorkflow.h"
#include "DlgActiveBody.h"
#include "SketchPlanePicker.h"
#include "TaskFeaturePick.h"
#include "Utils.h"
#include "ViewProviderBody.h"
#include "WorkflowManager.h"
#include <Mod/PartDesign/App/Body.h>
#include <Mod/PartDesign/App/DatumPlane.h>
#include <Mod/PartDesign/App/ShapeBinder.h>
#include <Mod/Part/App/AttachExtension.h>
#include <Mod/Part/App/Attacher.h>
#include <Mod/Part/App/Part2DObject.h>
#include <Mod/Part/App/TopoShape.h>
#include <Mod/Sketcher/Gui/Utils.h>
#include <Mod/Sketcher/Gui/ViewProviderSketch.h>

#include <App/Document.h>
#include <App/Link.h>
#include <App/Origin.h>
#include <App/Datums.h>
#include <App/Part.h>
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/Control.h>
#include <Gui/Document.h>
#include <Gui/MainWindow.h>
#include <Gui/ViewParams.h>
#include <Gui/ViewProviderPlane.h>
#include <Gui/Selection/SelectionFilter.h>

using namespace PartDesignGui;

namespace
{
struct RejectException
{
};

struct WrongSelectionException
{
};

struct WrongSupportException
{
};

struct SupportNotPlanarException
{
};

struct MissingPlanesException
{
};

std::tuple<Gui::SelectionFilter, Gui::SelectionFilter, Gui::SelectionFilter>
sketchFilters(PartDesign::Body* activeBody)
{
    // Hint:
    // The behaviour of this command has changed with respect to a selected sketch:
    // It doesn't try any more to edit a selected sketch but always tries to create
    // a new sketch.
    // See https://forum.freecad.org/viewtopic.php?f=3&t=44070

    Gui::SelectionFilter FaceFilter("SELECT Part::Feature SUBELEMENT Face COUNT 1");
    Gui::SelectionFilter PlaneFilter("SELECT App::Plane COUNT 1", activeBody);
    Gui::SelectionFilter PlaneFilter2("SELECT PartDesign::Plane COUNT 1", activeBody);
    Gui::SelectionFilter SketchFilter("SELECT Part::Part2DObject COUNT 1", activeBody);

    if (PlaneFilter2.match()) {
        PlaneFilter = PlaneFilter2;
    }

    return std::make_tuple(FaceFilter, PlaneFilter, SketchFilter);
}

class SupportFaceValidator
{
public:
    explicit SupportFaceValidator(Gui::SelectionObject faceSelection)
        : faceSelection(faceSelection)
    {}

    void handleSelectedBody(PartDesign::Body* activeBody)
    {
        App::DocumentObject* object = faceSelection.getObject();
        std::vector<std::string> elements = faceSelection.getSubNames();

        // In case the selected face belongs to the body then it means its
        // Display Mode Body is set to Tip. But the body face is not allowed
        // to be used as support because otherwise it would cause a cyclic
        // dependency. So, instead we use the tip object as reference.
        // https://forum.freecad.org/viewtopic.php?f=3&t=37448
        if (object == activeBody) {
            App::DocumentObject* tip = activeBody->Tip.getValue();
            if (tip && tip->isDerivedFrom<Part::Feature>() && elements.size() == 1) {
                Gui::SelectionChanges msg;
                msg.pDocName = faceSelection.getDocName();
                msg.pObjectName = tip->getNameInDocument();
                msg.pSubName = elements[0].c_str();
                msg.TypeName = tip->getTypeId().getName();
                msg.pTypeName = msg.TypeName.c_str();

                faceSelection = Gui::SelectionObject {msg};

                // automatically switch to 'Through' mode
                setThroughModeOfBody(activeBody);
            }
        }
    }

    void throwIfInvalid()
    {
        App::DocumentObject* object = faceSelection.getObject();
        std::vector<std::string> elements = faceSelection.getSubNames();

        Part::Feature* partobject = dynamic_cast<Part::Feature*>(object);
        if (!partobject) {
            throw WrongSelectionException();
        }

        if (elements.size() != 1) {
            throw WrongSelectionException();
        }

        // get the selected sub shape (a Face)
        const Part::TopoShape& shape = partobject->Shape.getValue();
        Part::TopoShape subshape(shape.getSubShape(elements[0].c_str()));
        if (subshape.isNull()) {
            throw WrongSupportException();
        }

        if (!subshape.isPlanar(Attacher::AttachEnginePlane::planarPrecision())) {
            throw SupportNotPlanarException();
        }
    }

    std::string getSupport() const
    {
        return faceSelection.getAsPropertyLinkSubString();
    }

    App::DocumentObject* getObject() const
    {
        return faceSelection.getObject();
    }

private:
    void setThroughModeOfBody(PartDesign::Body* activeBody)
    {
        // automatically switch to 'Through' mode
        PartDesignGui::ViewProviderBody* vpBody = dynamic_cast<PartDesignGui::ViewProviderBody*>(
            Gui::Application::Instance->getViewProvider(activeBody)
        );
        if (vpBody) {
            vpBody->DisplayModeBody.setValue("Through");
        }
    }

private:
    mutable Gui::SelectionObject faceSelection;
};

class SupportPlaneValidator
{
public:
    explicit SupportPlaneValidator(Gui::SelectionObject faceSelection)
        : faceSelection(faceSelection)
    {}

    std::string getSupport() const
    {
        return faceSelection.getAsPropertyLinkSubString();
    }

    App::DocumentObject* getObject() const
    {
        return faceSelection.getObject();
    }

private:
    mutable Gui::SelectionObject faceSelection;
};

class SketchPreselection
{
public:
    SketchPreselection(
        Gui::Document* guidocument,
        PartDesign::Body* activeBody,
        std::tuple<Gui::SelectionFilter, Gui::SelectionFilter, Gui::SelectionFilter> filter
    )
        : guidocument(guidocument)
        , activeBody(activeBody)
        , faceFilter(std::get<0>(filter))
        , planeFilter(std::get<1>(filter))
        , sketchFilter(std::get<2>(filter))
    {}

    bool matches()
    {
        return faceFilter.match() || planeFilter.match() || sketchFilter.match();
    }

    // True only when a single planar face or datum plane is selected (not a sketch).
    // Used for the fast-path that skips the attachment dialog.
    bool isSingleFaceOrPlane()
    {
        return (faceFilter.match() || planeFilter.match()) && !sketchFilter.match();
    }

    std::string getSupport() const
    {
        return supportString;
    }

    void createSupport()
    {
        createBodyOrThrow();

        // get the selected object
        App::DocumentObject* selectedObject {};

        if (faceFilter.match()) {
            Gui::SelectionObject faceSelObject = faceFilter.Result[0][0];
            useBodyOfFace(faceSelObject.getObject());
            SupportFaceValidator validator {faceSelObject};
            validator.handleSelectedBody(activeBody);
            validator.throwIfInvalid();

            selectedObject = validator.getObject();
            supportString = validator.getSupport();
        }
        else if (planeFilter.match()) {
            SupportPlaneValidator validator(planeFilter.Result[0][0]);
            selectedObject = validator.getObject();
            supportString = validator.getSupport();
        }
        else {
            // For a sketch, the support is the object itself with no sub-element.
            Gui::SelectionObject sketchSelObject = sketchFilter.Result[0][0];
            selectedObject = sketchSelObject.getObject();
            supportString = sketchSelObject.getAsPropertyLinkSubString();
        }

        handleIfSupportOutOfBody(selectedObject);
    }

    void createSketchOnSupport(const std::string& supportString)
    {
        PartDesignGui::setEdit(createSketchObject(supportString), activeBody);
    }

    /// Creates the sketch on the face or plane and returns it, leaving it to the caller
    /// to open it. Joins a pending command, so that a body made for the sketch and the
    /// sketch itself undo together.
    App::DocumentObject* createSketchObject(const std::string& supportString)
    {
        // create Sketch on Face or Plane
        App::Document* appdocument = guidocument->getDocument();
        std::string FeatName = appdocument->getUniqueObjectName("Sketch");

        if (!guidocument->hasPendingCommand()) {
            guidocument->openCommand(QT_TRANSLATE_NOOP("Command", "Sketch on Face"));
        }
        FCMD_OBJ_CMD(activeBody, "newObject('Sketcher::SketchObject','" << FeatName << "')");
        auto Feat = activeBody->getDocument()->getObject(FeatName.c_str());
        FCMD_OBJ_CMD(Feat, "Label = 'Sketch'");
        FCMD_OBJ_CMD(Feat, "AttachmentSupport = " << supportString);
        if (sketchFilter.match()) {
            FCMD_OBJ_CMD(
                Feat,
                "MapMode = '" << Attacher::AttachEngine::getModeName(Attacher::mmObjectXY) << "'"
            );
        }
        else {  // For Face or Plane
            FCMD_OBJ_CMD(
                Feat,
                "MapMode = '" << Attacher::AttachEngine::getModeName(Attacher::mmFlatFace) << "'"
            );
        }
        Gui::Command::updateActive();
        // After the recompute, so that the sketch is on its plane before its face is
        // projected onto it.
        SketcherGui::autoProjectSupportEdges(Feat);
        return Feat;
    }

private:
    /// Fusion puts a sketch on a face into the face's own component, so a face of another
    /// body makes that body the active one rather than being brought across to this one
    void useBodyOfFace(App::DocumentObject* object)
    {
        auto* body = dynamic_cast<PartDesign::Body*>(object);
        if (!body) {
            body = PartDesign::Body::findBodyOf(object);
        }
        if (body && body != activeBody) {
            if (auto* active = PartDesignGui::makeBodyActive(body, body->getDocument())) {
                activeBody = active;
            }
        }
    }

    void createBodyOrThrow()
    {
        if (!activeBody) {
            activeBody = PartDesignGui::getBody(/* messageIfNot = */ true);
            if (activeBody) {
                tryAddNewBodyToActivePart();
            }
            else {
                throw RejectException();
            }
        }
    }

    void tryAddNewBodyToActivePart()
    {
        App::Part* activePart = PartDesignGui::getActivePart();
        if (activePart) {
            activePart->addObject(activeBody);
        }
    }

    void handleIfSupportOutOfBody(App::DocumentObject* selectedObject)
    {
        if (!activeBody->hasObject(selectedObject)) {
            if (!selectedObject->isDerivedFrom(App::Plane::getClassTypeId())) {
                // Geometry outside any body (a face of another body has switched bodies
                // by now) comes in as a dependent shape binder, without asking. It joins
                // the sketch's command, so one undo takes both away.
                if (!guidocument->hasPendingCommand()) {
                    guidocument->openCommand(QT_TRANSLATE_NOOP("Command", "Sketch on Face"));
                }
                auto copy = makeCopy(selectedObject, /*independent =*/false);
                supportString = supportFromCopy(copy);
            }
        }
    }

    App::DocumentObject* makeCopy(App::DocumentObject* selectedObject, bool independent)
    {
        std::string sub;
        if (faceFilter.match()) {
            sub = faceFilter.Result[0][0].getSubNames()[0];
        }
        auto copy = PartDesignGui::TaskFeaturePick::makeCopy(selectedObject, sub, independent);

        addToBodyOrPart(copy);

        return copy;
    }

    std::string supportFromCopy(App::DocumentObject* copy)
    {
        std::string supportString;
        if (planeFilter.match()) {
            supportString = Gui::Command::getObjectCmd(copy, "(", ",'')");
        }
        else {
            // it is ensured that only a single face is selected, hence it must always be Face1 of
            // the shapebinder
            supportString = Gui::Command::getObjectCmd(copy, "(", ",'Face1')");
        }
        return supportString;
    }

    void addToBodyOrPart(App::DocumentObject* object)
    {
        auto activePart = PartDesignGui::getPartFor(activeBody, false);
        if (activeBody) {
            activeBody->addObject(object);
        }
        else if (activePart) {
            activePart->addObject(object);
        }
    }

private:
    Gui::Document* guidocument;
    PartDesign::Body* activeBody;
    Gui::SelectionFilter faceFilter;
    Gui::SelectionFilter planeFilter;
    Gui::SelectionFilter sketchFilter;
    std::string supportString;
};

class PlaneFinder
{
public:
    PlaneFinder(App::Document* appdocument, PartDesign::Body* activeBody)
        : appdocument(appdocument)
        , activeBody(activeBody)
    {}

    std::vector<App::DocumentObject*> getPlanes() const
    {
        return planes;
    }

    std::vector<PartDesignGui::TaskFeaturePick::featureStatus> getStatus() const
    {
        return status;
    }

    unsigned countValidPlanes() const
    {
        return validPlaneCount;
    }

    void findBasePlanes()
    {
        try {
            tryFindBasePlanes();
        }
        catch (const Base::Exception& ex) {
            Base::Console().error("%s\n", ex.what());
        }
    }

    void findDatumPlanes()
    {
        App::GeoFeatureGroupExtension* geoGroup = getGroupExtensionOfBody();
        const std::vector<Base::Type> types
            = {PartDesign::Plane::getClassTypeId(), App::Plane::getClassTypeId()};
        auto datumPlanes = appdocument->getObjectsOfType(types);

        for (auto plane : datumPlanes) {
            if (std::find(planes.begin(), planes.end(), plane) != planes.end()) {
                continue;  // Skip if already in planes (for base planes)
            }

            planes.push_back(plane);
            // Check whether this plane belongs to the active body
            if (activeBody->hasObject(plane, true)) {
                if (!activeBody->isAfterInsertPoint(plane)) {
                    validPlaneCount++;
                    status.push_back(PartDesignGui::TaskFeaturePick::validFeature);
                }
                else {
                    status.push_back(PartDesignGui::TaskFeaturePick::afterTip);
                }
            }
            else {
                PartDesign::Body* planeBody = PartDesign::Body::findBodyOf(plane);
                if (planeBody) {
                    if ((geoGroup && geoGroup->hasObject(planeBody, true))
                        || !App::GeoFeatureGroupExtension::getGroupOfObject(planeBody)) {
                        status.push_back(PartDesignGui::TaskFeaturePick::otherBody);
                    }
                    else {
                        status.push_back(PartDesignGui::TaskFeaturePick::otherPart);
                    }
                }
                else {
                    if ((geoGroup && geoGroup->hasObject(plane, true))
                        || App::GeoFeatureGroupExtension::getGroupOfObject(plane)) {
                        status.push_back(PartDesignGui::TaskFeaturePick::otherPart);
                    }
                    else {
                        status.push_back(PartDesignGui::TaskFeaturePick::notInBody);
                    }
                }
            }
        }
    }

    void findShapeBinderPlanes()
    {

        // Collect also shape binders consisting of a single planar face
        auto shapeBinders(appdocument->getObjectsOfType(PartDesign::ShapeBinder::getClassTypeId()));
        auto binders(appdocument->getObjectsOfType(PartDesign::SubShapeBinder::getClassTypeId()));
        shapeBinders.insert(shapeBinders.end(), binders.begin(), binders.end());
        for (auto binder : shapeBinders) {
            // Check whether this plane belongs to the active body
            if (activeBody->hasObject(binder)) {
                Part::TopoShape shape = static_cast<Part::Feature*>(binder)->Shape.getShape();
                if (shape.isPlanar()) {
                    if (!activeBody->isAfterInsertPoint(binder)) {
                        validPlaneCount++;
                        planes.push_back(binder);
                        status.push_back(PartDesignGui::TaskFeaturePick::validFeature);
                    }
                }
            }
        }
    }

private:
    void tryFindBasePlanes()
    {
        auto* origin = activeBody->getOrigin();
        for (auto plane : origin->planes()) {
            planes.push_back(plane);
            status.push_back(PartDesignGui::TaskFeaturePick::basePlane);
            validPlaneCount++;
        }
    }

    App::GeoFeatureGroupExtension* getGroupExtensionOfBody() const
    {
        App::GeoFeatureGroupExtension* geoGroup {nullptr};
        if (activeBody) {
            auto group(App::GeoFeatureGroupExtension::getGroupOfObject(activeBody));
            if (group) {
                geoGroup = group->getExtensionByType<App::GeoFeatureGroupExtension>();
            }
        }

        return geoGroup;
    }

private:
    App::Document* appdocument;
    PartDesign::Body* activeBody;
    unsigned validPlaneCount = 0;
    std::vector<App::DocumentObject*> planes;
    std::vector<PartDesignGui::TaskFeaturePick::featureStatus> status;
};

class SketchRequestSelection
{
public:
    SketchRequestSelection(
        Gui::Document* guidocument,
        PartDesign::Body* activeBody,
        bool useAttachmentDialog
    )
        : guidocument(guidocument)
        , activeBody(activeBody)
        , useAttachmentDialog(useAttachmentDialog)
    {}

    void findSupport()
    {
        try {
            // Start command early, so undo will undo any Body creation
            guidocument->openCommand(QT_TRANSLATE_NOOP("Command", "New Sketch"));
            tryFindSupport();
        }
        catch (const RejectException&) {
            guidocument->abortCommand();
            throw;
        }
        catch (const MissingPlanesException&) {
            guidocument->abortCommand();
            throw;
        }
    }

private:
    void tryFindSupport()
    {
        createBodyOrThrow();

        if (useAttachmentDialog) {
            createSketchAndShowAttachment();
        }
        else {
            pickPlaneInView();
        }
    }

    void createBodyOrThrow()
    {
        if (!activeBody) {
            App::Document* appdocument = guidocument->getDocument();
            activeBody = PartDesignGui::makeBody(appdocument);
            if (activeBody) {
                tryAddNewBodyToActivePart();
            }
            else {
                throw RejectException();
            }
        }
    }

    void tryAddNewBodyToActivePart()
    {
        App::Part* activePart = PartDesignGui::getActivePart();
        if (activePart) {
            activePart->addObject(activeBody);
        }
    }

    void setOriginTemporaryVisibility()
    {
        auto* origin = activeBody->getOrigin();
        auto* vpo = dynamic_cast<Gui::ViewProviderCoordinateSystem*>(
            Gui::Application::Instance->getViewProvider(origin)
        );
        if (vpo) {
            vpo->setTemporaryVisibility(Gui::DatumElement::Planes | Gui::DatumElement::Axes);
            vpo->setPlaneLabelVisibility(true);
        }
    }

    void createSketchAndShowAttachment()
    {
        setOriginTemporaryVisibility();

        // Capture selection before clearing it to pre-populate the attachment dialog.
        // This mirrors UnifiedDatumCommand: use attacher to find the best fit mode.
        App::PropertyLinkSubList support;
        Gui::Selection().getAsPropertyLinkSubList(support);
        support.removeValue(activeBody);

        // Don't pre-populate when the selection contains sketches. A sketch selected
        // from prior work should not automatically become the attachment reference —
        // the user can choose a face or plane in the dialog.
        bool hasSketch = std::ranges::any_of(support.getValues(), [](App::DocumentObject* obj) {
            return obj && obj->isDerivedFrom<Part::Part2DObject>();
        });

        // Create sketch
        App::Document* doc = activeBody->getDocument();
        std::string FeatName = doc->getUniqueObjectName("Sketch");
        FCMD_OBJ_CMD(activeBody, "newObject('Sketcher::SketchObject','" << FeatName << "')");
        auto sketch = doc->getObject(FeatName.c_str());
        FCMD_OBJ_CMD(sketch, "Label = 'Sketch'");

        if (!hasSketch && support.getSize() > 0) {
            if (auto* pcAttach = sketch->getExtensionByType<Part::AttachExtension>()) {
                pcAttach->attacher().setReferences(support);
                Attacher::SuggestResult sugr;
                pcAttach->attacher().suggestMapModes(sugr);
                if (sugr.message == Attacher::SuggestResult::srOK) {
                    FCMD_OBJ_CMD(sketch, "AttachmentSupport = " << support.getPyReprString());
                    FCMD_OBJ_CMD(
                        sketch,
                        "MapMode = '" << Attacher::AttachEngine::getModeName(sugr.bestFitMode) << "'"
                    );
                    Gui::Command::updateActive();
                }
            }
        }

        PartDesign::Body* partDesignBody = activeBody;
        auto onAccept = [partDesignBody, sketch]() {
            resetOriginVisibility(partDesignBody);

            Gui::Selection().clearSelection();

            SketcherGui::autoProjectSupportEdges(sketch);
            PartDesignGui::setEdit(sketch, partDesignBody);
        };
        auto onReject = [partDesignBody]() {
            resetOriginVisibility(partDesignBody);
        };

        Gui::Selection().clearSelection();

        // Open attachment dialog
        auto* vps = dynamic_cast<SketcherGui::ViewProviderSketch*>(
            Gui::Application::Instance->getViewProvider(sketch)
        );
        vps->showAttachmentEditor(onAccept, onReject, true);
    }

    /// Fusion's way: no dialog, just click the face or plane to sketch on. The sketch is
    /// only made once something planar has been picked, so a cancel leaves nothing but
    /// the undo of a body that was created for it.
    void pickPlaneInView()
    {
        checkForShownDialog();
        setOriginTemporaryVisibility();
        Gui::Selection().clearSelection();

        Gui::Document* document = guidocument;
        PartDesign::Body* body = activeBody;
        std::string documentName = document->getDocument()->getName();
        std::string bodyName = body->getNameInDocument();

        auto onPick = [document, body]() -> App::DocumentObject* {
            SketchPreselection picked {document, body, sketchFilters(body)};
            if (!picked.isSingleFaceOrPlane()) {
                return nullptr;
            }
            try {
                picked.createSupport();
                return picked.createSketchObject(picked.getSupport());
            }
            catch (const RejectException&) {
                // The user turned down the copy/cross-reference question.
            }
            catch (const WrongSelectionException&) {
            }
            catch (const WrongSupportException&) {
            }
            catch (const SupportNotPlanarException&) {
            }
            return nullptr;
        };

        auto onDone = [documentName, bodyName](App::DocumentObject* sketch) {
            Gui::Document* document
                = Gui::Application::Instance->getDocument(documentName.c_str());
            if (!document) {
                return;  // the document went away, and took the picker with it
            }
            auto* body = dynamic_cast<PartDesign::Body*>(
                document->getDocument()->getObject(bodyName.c_str())
            );
            if (body) {
                resetOriginVisibility(body);
            }
            if (sketch) {
                document->commitCommand();
                // A face of another body puts the sketch there, not in the body picked for
                PartDesignGui::setEdit(sketch, PartDesign::Body::findBodyOf(sketch));
            }
            else if (document->hasPendingCommand()) {
                document->abortCommand();
            }
        };

        Gui::Control().showDialog(
            new TaskDlgSketchPlanePick(body, onPick, onDone),
            document->getDocument()
        );
    }

    static void resetOriginVisibility(PartDesign::Body* partDesignBody)
    {
        auto* origin = partDesignBody->getOrigin();
        auto* vpo = dynamic_cast<Gui::ViewProviderCoordinateSystem*>(
            Gui::Application::Instance->getViewProvider(origin)
        );
        if (vpo) {
            vpo->resetTemporaryVisibility();
            vpo->resetTemporarySize();
            vpo->setPlaneLabelVisibility(false);
        }
    }

    void findAndSelectPlane()
    {
        App::Document* appdocument = guidocument->getDocument();
        PlaneFinder planeFinder {appdocument, activeBody};

        planeFinder.findBasePlanes();
        planeFinder.findDatumPlanes();
        planeFinder.findShapeBinderPlanes();

        std::vector<App::DocumentObject*> planes = planeFinder.getPlanes();
        std::vector<PartDesignGui::TaskFeaturePick::featureStatus> status = planeFinder.getStatus();
        unsigned validPlaneCount = planeFinder.countValidPlanes();

        for (auto& plane : planes) {
            auto* planeViewProvider
                = Gui::Application::Instance->getViewProvider<Gui::ViewProviderPlane>(plane);

            // skip updating planes from coordinate systems
            if (!planeViewProvider || !planeViewProvider->getRole().empty()) {
                continue;
            }

            planeViewProvider->setLabelVisibility(true);
            planeViewProvider->setTemporaryScale(
                Gui::ViewParams::instance()->getDatumTemporaryScaleFactor()
            );
        }

        //
        // Lambda definitions
        //
        App::Document* documentOfBody = appdocument;
        PartDesign::Body* partDesignBody = activeBody;

        auto restorePlaneVisibility = [planes]() {
            for (auto& plane : planes) {
                auto* planeViewProvider
                    = Gui::Application::Instance->getViewProvider<Gui::ViewProviderPlane>(plane);
                if (!planeViewProvider) {
                    continue;
                }

                planeViewProvider->resetTemporarySize();
                planeViewProvider->setLabelVisibility(false);
            }
        };

        // Determines if user made a valid selection in dialog
        auto acceptFunction =
            [restorePlaneVisibility](const std::vector<App::DocumentObject*>& features) -> bool {
            restorePlaneVisibility();
            return !features.empty();
        };

        // Called by dialog when user hits "OK" and accepter returns true
        auto processFunction = [documentOfBody,
                                partDesignBody](const std::vector<App::DocumentObject*>& features) {
            SketchRequestSelection::createSketch(documentOfBody, partDesignBody, features);
        };

        // Called by dialog for "Cancel", or "OK" if accepter returns false
        std::string docname = documentOfBody->getName();
        auto rejectFunction = [docname, restorePlaneVisibility]() {
            restorePlaneVisibility();
            Gui::Document* document = Gui::Application::Instance->getDocument(docname.c_str());
            if (document) {
                document->abortCommand();
            }
        };

        //
        // End of lambda definitions
        //

        if (validPlaneCount == 0) {
            throw MissingPlanesException();
        }
        else if (validPlaneCount == 1) {
            processFunction(planes);
        }
        else if (validPlaneCount > 1) {
            checkForShownDialog();
            Gui::Selection().clearSelection();

            // Show dialog and let user pick plane
            Gui::Control().showDialog(new PartDesignGui::TaskDlgFeaturePick(
                planes,
                status,
                acceptFunction,
                processFunction,
                true,
                rejectFunction
            ));
        }
    }

    void checkForShownDialog()
    {
        App::Document* appdocument = guidocument->getDocument();
        Gui::TaskView::TaskDialog* dlg = Gui::Control().activeDialog(appdocument);
        PartDesignGui::TaskDlgFeaturePick* pickDlg
            = qobject_cast<PartDesignGui::TaskDlgFeaturePick*>(dlg);
        if (dlg && !pickDlg) {
            QMessageBox msgBox(Gui::getMainWindow());
            msgBox.setText(QObject::tr("A dialog is already open in the task panel"));
            msgBox.setInformativeText(QObject::tr("Close this dialog?"));
            msgBox.setStandardButtons(QMessageBox::Yes | QMessageBox::No);
            msgBox.setDefaultButton(QMessageBox::Yes);
            int ret = msgBox.exec();
            if (ret == QMessageBox::Yes) {
                Gui::Control().closeDialog();
            }
            else {
                throw RejectException();
            }
        }

        if (dlg) {
            Gui::Control().closeDialog();
        }
    }

    static void createSketch(
        App::Document* documentOfBody,
        PartDesign::Body* partDesignBody,
        const std::vector<App::DocumentObject*>& features
    )
    {
        // may happen when the user switched to an empty document while the
        // dialog is open
        if (features.empty()) {
            return;
        }
        std::string FeatName = documentOfBody->getUniqueObjectName("Sketch");
        auto* plane = static_cast<App::Plane*>(features.front());
        auto* lcs = plane->getLCS();

        std::string supportString;
        if (lcs) {
            supportString = Gui::Command::getObjectCmd(lcs, "(") + ",['"
                + plane->getNameInDocument() + "'])";
        }
        else {
            supportString = Gui::Command::getObjectCmd(plane, "(", ",[''])");
        }

        App::Document* doc = partDesignBody->getDocument();
        if (!doc->hasPendingTransaction()) {
            doc->openTransaction(QT_TRANSLATE_NOOP("Command", "New Sketch"));
        }

        FCMD_OBJ_CMD(partDesignBody, "newObject('Sketcher::SketchObject','" << FeatName << "')");
        auto Feat = doc->getObject(FeatName.c_str());
        FCMD_OBJ_CMD(Feat, "Label = 'Sketch'");
        FCMD_OBJ_CMD(Feat, "AttachmentSupport = " << supportString);
        FCMD_OBJ_CMD(
            Feat,
            "MapMode = '" << Attacher::AttachEngine::getModeName(Attacher::mmFlatFace) << "'"
        );
        Gui::Command::updateActive();  // Make sure the AttachmentSupport's Placement property is updated
        PartDesignGui::setEdit(Feat, partDesignBody);
    }

private:
    Gui::Document* guidocument;
    PartDesign::Body* activeBody;
    bool useAttachmentDialog;
};

}  // namespace

SketchWorkflow::SketchWorkflow(Gui::Document* document)
    : guidocument(document)
{
    appdocument = guidocument->getDocument();
}

void SketchWorkflow::createSketch()
{
    try {
        tryCreateSketch();
    }
    catch (const RejectException&) {
    }
    catch (const WrongSelectionException&) {
        QMessageBox::warning(
            Gui::getMainWindow(),
            QObject::tr("Several sub-elements selected"),
            QObject::tr("Select a single face as support for a sketch!")
        );
    }
    catch (const WrongSupportException&) {
        QMessageBox::warning(
            Gui::getMainWindow(),
            QObject::tr("No support face selected"),
            QObject::tr("Select a face as support for a sketch!")
        );
    }
    catch (const SupportNotPlanarException&) {
        QMessageBox::warning(
            Gui::getMainWindow(),
            QObject::tr("No planar support"),
            QObject::tr("Need a planar face as support for a sketch!")
        );
    }
    catch (const MissingPlanesException&) {
        QMessageBox::warning(
            Gui::getMainWindow(),
            QObject::tr("No valid planes in this document"),
            QObject::tr("Create a plane first or select a face to sketch on")
        );
    }
}

void SketchWorkflow::tryCreateSketch()
{
    auto result = shouldCreateBody();
    auto shouldMakeBody = std::get<0>(result);
    activeBody = std::get<1>(result);
    if (shouldAbort(shouldMakeBody)) {
        return;
    }

    bool useAttachment = App::GetApplication()
                             .GetParameterGroupByPath(
                                 "User parameter:BaseApp/Preferences/Mod/PartDesign"
                             )
                             ->GetBool("NewSketchUseAttachmentDialog", false);

    bool shiftHeld = QApplication::queryKeyboardModifiers() & Qt::ShiftModifier;

    auto filters = getFilters();
    SketchPreselection sketchOnFace {guidocument, activeBody, filters};

    // Fast path: single face or datum plane, preference off, Shift not held.
    // If the face turns out to be non-planar or otherwise invalid, fall through
    // instead of showing an error.
    // A selected sketch, multiple references, Shift, or preference on all go through
    // the attachment dialog; with nothing selected the user picks a face or plane in
    // the 3D view instead.
    if (!useAttachment && !shiftHeld && sketchOnFace.isSingleFaceOrPlane()) {
        try {
            sketchOnFace.createSupport();
            sketchOnFace.createSketchOnSupport(sketchOnFace.getSupport());
            return;
        }
        catch (const WrongSupportException&) {
            // Fall through to attachment dialog
        }
        catch (const WrongSelectionException&) {
            // Fall through to attachment dialog
        }
        catch (const SupportNotPlanarException&) {
            // Fall through to attachment dialog
        }
    }

    SketchRequestSelection requestSelection {guidocument, activeBody, useAttachment || shiftHeld};
    requestSelection.findSupport();
}

std::tuple<bool, PartDesign::Body*> SketchWorkflow::shouldCreateBody()
{
    auto shouldMakeBody {false};

    // We need either an active Body, or for there to be no Body
    // objects (in which case, just make one) to make a new sketch.
    // If we are inside a link, we need to use its placement.
    // A sketch goes into the body of the face, plane or sketch it is put on
    PartDesignGui::activateBodyOfSelection();
    App::DocumentObject* topParent;
    PartDesign::Body* pdBody
        = PartDesignGui::getBody(/* messageIfNot = */ false, true, true, &topParent);
    if (pdBody && topParent->isLink()) {
        auto* xLink = dynamic_cast<App::Link*>(topParent);
        pdBody->Placement.setValue(xLink->Placement.getValue());
    }
    if (!pdBody) {
        if (appdocument->countObjectsOfType<PartDesign::Body>() == 0) {
            shouldMakeBody = true;
        }
        else {
            PartDesignGui::DlgActiveBody dia(Gui::getMainWindow(), appdocument);
            if (dia.exec() == QDialog::Accepted) {
                pdBody = dia.getActiveBody();
            }
        }
    }

    return std::make_tuple(shouldMakeBody, pdBody);
}

bool SketchWorkflow::shouldAbort(bool shouldMakeBody) const
{
    return !shouldMakeBody && !activeBody;
}

std::tuple<Gui::SelectionFilter, Gui::SelectionFilter, Gui::SelectionFilter> SketchWorkflow::getFilters() const
{
    return sketchFilters(activeBody);
}
