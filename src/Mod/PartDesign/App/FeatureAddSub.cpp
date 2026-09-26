// SPDX-License-Identifier: LGPL-2.1-or-later

/***************************************************************************
 *   Copyright (c) 2011 Juergen Riegel <FreeCAD@juergen-riegel.net>        *
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


#include <cstring>
#include <string>
#include <vector>

#include <Standard_Failure.hxx>


#include <App/FeaturePythonPyImp.h>
#include <Base/Exception.h>
#include <Mod/Part/App/modelRefine.h>
#include <Mod/Part/App/TopoShapeOpCode.h>
#include <GProp_GProps.hxx>
#include <BRepGProp.hxx>

#include "FeatureAddSub.h"
#include "FeaturePy.h"

#include <Mod/Part/App/Tools.h>


using namespace PartDesign;

namespace PartDesign
{

extern bool getPDRefineModelParameter();

PROPERTY_SOURCE(PartDesign::FeatureAddSub, PartDesign::FeatureRefine)

const char* FeatureAddSub::OperationEnums[] = {"Join", "Cut", "Intersect", "NewBody", nullptr};

FeatureAddSub::FeatureAddSub()
{
    ADD_PROPERTY(AddSubShape, (TopoDS_Shape()));
    ADD_PROPERTY_TYPE(
        Operation,
        (0L),
        "Base",
        App::Prop_None,
        "Boolean operation used to combine this feature with the preceding solid"
    );
    Operation.setEnums(OperationEnums);
}

void FeatureAddSub::onChanged(const App::Property* property)
{
    if (property == &Operation) {
        operationInitialized = true;
    }
    Feature::onChanged(property);
}

namespace
{
/// Upstream FreeCAD narrows Operation to what one feature class can do: {"Union"} for an
/// additive feature, {"Subtraction", "Common"} for a subtractive one. Those lists are
/// custom enumerations, so a FreeCAD document stores the value names alongside the index
/// it saves, and the index alone means something else here, where every feature offers
/// all four operations. Such a document is therefore read by name.
FeatureAddSub::OperationType operationFromName(const char* name)
{
    if (name) {
        if (strcmp(name, "Subtraction") == 0 || strcmp(name, "Cut") == 0) {
            return FeatureAddSub::OperationType::Cut;
        }
        if (strcmp(name, "Common") == 0 || strcmp(name, "Intersect") == 0) {
            return FeatureAddSub::OperationType::Intersect;
        }
        if (strcmp(name, "NewBody") == 0) {
            return FeatureAddSub::OperationType::NewBody;
        }
    }

    // "Union", "Join", and anything unrecognised: adding material is the safe reading,
    // and it is what index 0 means in every list involved.
    return FeatureAddSub::OperationType::Join;
}
}  // namespace

void FeatureAddSub::setupObject()
{
    FeatureRefine::setupObject();

    Operation.setValue(
        static_cast<long>(addSubType == Type::Subtractive ? OperationType::Cut : OperationType::Join)
    );
}

void FeatureAddSub::onDocumentRestored()
{
    // Documents written before the Operation property existed have to derive it from the
    // add/sub nature the concrete feature class was hardcoded to.
    if (!operationInitialized) {
        Operation.setValue(
            static_cast<long>(addSubType == Type::Subtractive ? OperationType::Cut : OperationType::Join)
        );
    }
    else {
        migrateForeignOperation();
    }

    FeatureRefine::onDocumentRestored();
}

void FeatureAddSub::migrateForeignOperation()
{
    // Only a custom enumeration travels with the document, and ours is a plain static
    // list, so a file written here restores the list the constructor already set and
    // leaves this alone. Anything else was written by a build that numbers the operations
    // differently.
    const std::vector<std::string> restored = Operation.getEnumVector();

    std::vector<std::string> ours;
    for (const char** value = OperationEnums; *value; ++value) {
        ours.emplace_back(*value);
    }

    if (restored == ours) {
        return;
    }

    const OperationType operation = restored.empty()
        ? (addSubType == Type::Subtractive ? OperationType::Cut : OperationType::Join)
        : operationFromName(Operation.getValueAsString());

    // Put our own list back before the value, because setting the list keeps the old
    // name and that name is not in it.
    Operation.setEnums(OperationEnums);
    Operation.setValue(static_cast<long>(operation));
}

FeatureAddSub::OperationType FeatureAddSub::getOperationType() const
{
    return static_cast<OperationType>(Operation.getValue());
}

bool FeatureAddSub::combinesWithBase() const
{
    return getOperationType() != OperationType::NewBody;
}

bool FeatureAddSub::keepBaseForNewBody(const TopoShape& base)
{
    // The GUI moves the feature into a body of its own (PartDesignNewBody.py), where it has
    // no base. Until then the body it was made in must not lose what came before it.
    if (combinesWithBase() || base.isNull()) {
        return false;
    }
    rawShape = base;
    Shape.setValue(base);
    return true;
}

const char* FeatureAddSub::getBooleanOpCode() const
{
    switch (getOperationType()) {
        case OperationType::Join:
            return Part::OpCodes::Fuse;
        case OperationType::Cut:
            return Part::OpCodes::Cut;
        case OperationType::Intersect:
            return Part::OpCodes::Common;
        case OperationType::NewBody:
        default:
            throw Base::ValueError("Unhandled value of the Operation property");
    }
}

void FeatureAddSub::defineAdditive()
{
    addSubType = Type::Additive;
}

void FeatureAddSub::defineSubtractive()
{
    addSubType = Type::Subtractive;
}

const char* FeatureAddSub::getBooleanMaker() const
{
    return getBooleanOpCode();
}

FeatureAddSub::Type FeatureAddSub::getAddSubType()
{
    switch (getOperationType()) {
        case OperationType::Join:
        case OperationType::NewBody:
            return Type::Additive;
        case OperationType::Cut:
        case OperationType::Intersect:
            return Type::Subtractive;
        default:
            throw Base::ValueError("Unhandled value of the Operation property");
    }
}

short FeatureAddSub::mustExecute() const
{
    if (Refine.isTouched() || Operation.isTouched()) {
        return 1;
    }
    return PartDesign::Feature::mustExecute();
}

void FeatureAddSub::getAddSubShape(Part::TopoShape& addShape, Part::TopoShape& subShape)
{
    if (getAddSubType() == Type::Additive) {
        addShape = AddSubShape.getShape();
    }
    else {
        subShape = AddSubShape.getShape();
    }
}

void FeatureAddSub::updatePreviewShape()
{
    const auto notifyWarning = [](const QString& message) {
        Base::Console().translatedUserWarning(
            "Preview",
            tr("Failure while computing removed volume preview: %1").arg(message).toUtf8()
        );
    };

    // for subtractive shapes we want to also showcase removed volume, not only the tool
    if (getAddSubType() == Type::Subtractive) {
        TopoShape base = getBaseTopoShape(true).moved(getLocation().Inverted());
        const TopoShape& tool = AddSubShape.getShape();

        if (!tool.isEmpty()) {
            try {
                TopoShape common;
                common.makeElementBoolean(
                    Part::OpCodes::Common,
                    {base, tool},
                    "Preview",
                    Precision::Confusion()
                );

                GProp_GProps propsBefore, propsAfter;
                BRepGProp::VolumeProperties(base.getShape(), propsBefore);

                TopoShape cut;
                cut.makeElementBoolean(
                    Part::OpCodes::Cut,
                    {base, tool},
                    "PreviewCheck",
                    Precision::Confusion()
                );

                // Check whether the selected operation removes material from the base.
                const bool keepCommon = getOperationType() == OperationType::Intersect;
                const TopoShape& result = keepCommon ? common : cut;
                BRepGProp::VolumeProperties(result.getShape(), propsAfter);

                const double removed = propsBefore.Mass() - propsAfter.Mass();

                if (removed <= Precision::Confusion()) {
                    notifyWarning(
                        tr("Resulting shape is empty. That may indicate that no material will be "
                           "removed or a problem with the model.")
                    );
                }
                // Common keeps the overlap, so its removed-volume preview is outside the tool.
                PreviewShape.setValue(keepCommon ? cut : common);
                return;
            }
            catch (Standard_Failure& e) {
                notifyWarning(QString::fromUtf8(e.GetMessageString()));
            }
            catch (Base::Exception& e) {
                notifyWarning(QString::fromStdString(e.what()));
            }
            PreviewShape.setValue(base);
            return;
        }
    }

    PreviewShape.setValue(AddSubShape.getShape());
}

}  // namespace PartDesign

namespace App
{
/// @cond DOXERR
PROPERTY_SOURCE_TEMPLATE(PartDesign::FeatureAddSubPython, PartDesign::FeatureAddSub)
template<>
const char* PartDesign::FeatureAddSubPython::getViewProviderName() const
{
    return "PartDesignGui::ViewProviderPython";
}
template<>
PyObject* PartDesign::FeatureAddSubPython::getPyObject()
{
    if (PythonObject.is(Py::_None())) {
        // ref counter is set to 1
        PythonObject = Py::Object(new FeaturePythonPyT<PartDesign::FeaturePy>(this), true);
    }
    return Py::new_reference_to(PythonObject);
}
/// @endcond

// explicit template instantiation
template class PartDesignExport FeaturePythonT<PartDesign::FeatureAddSub>;
}  // namespace App


namespace PartDesign
{

PROPERTY_SOURCE(PartDesign::FeatureAdditivePython, PartDesign::FeatureAddSubPython)

FeatureAdditivePython::FeatureAdditivePython()
{
    defineAdditive();
}

FeatureAdditivePython::~FeatureAdditivePython() = default;


PROPERTY_SOURCE(PartDesign::FeatureSubtractivePython, PartDesign::FeatureAddSubPython)

FeatureSubtractivePython::FeatureSubtractivePython()
{
    defineSubtractive();
}

FeatureSubtractivePython::~FeatureSubtractivePython() = default;

}  // namespace PartDesign
