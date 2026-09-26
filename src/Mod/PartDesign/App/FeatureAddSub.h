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


#pragma once

#include "FeatureRefine.h"

#include <App/PropertyStandard.h>

#include <QCoreApplication>

/// Base class of all additive features in PartDesign
namespace PartDesign
{

class PartDesignExport FeatureAddSub: public PartDesign::FeatureRefine
{
    Q_DECLARE_TR_FUNCTIONS(PartDesign::FeatureAddSub)
    PROPERTY_HEADER_WITH_OVERRIDE(PartDesign::FeatureAddSub);

public:
    enum class Type
    {
        Additive = 0,
        Subtractive
    };

    /// Values of the Operation property, must stay in sync with OperationEnums
    enum class OperationType
    {
        Join = 0,
        Cut,
        Intersect,
        NewBody
    };

    FeatureAddSub();

    void onChanged(const App::Property*) override;

    Type getAddSubType();
    OperationType getOperationType() const;

    /// Whether the feature shape has to be combined with the preceding solid at all
    bool combinesWithBase() const;
    /// With New body the solid starts another body, so a preceding solid passes through
    /// unchanged. Sets Shape to base and returns true when that applies.
    bool keepBaseForNewBody(const Part::TopoShape& base);
    /// Part::OpCodes maker matching Operation; throws for operations without a boolean
    const char* getBooleanOpCode() const;
    /// Upstream's name for getBooleanOpCode(), so FreeCAD's feature classes merge cleanly
    const char* getBooleanMaker() const;

    short mustExecute() const override;

    virtual void getAddSubShape(Part::TopoShape& addShape, Part::TopoShape& subShape);

    void updatePreviewShape() override;

    void setupObject() override;

    App::PropertyEnumeration Operation;
    Part::PropertyPartShape AddSubShape;

    static const char* OperationEnums[];

protected:
    void onDocumentRestored() override;

    /// Re-read Operation from a document whose enumeration is not FuCadUp's
    void migrateForeignOperation();

    /// Seed Operation with Join and Cut respectively. Unlike upstream these leave
    /// every operation on offer, because one FuCadUp tool does both.
    void defineAdditive();
    void defineSubtractive();

    Type addSubType {Type::Additive};

private:
    /// False until something outside the constructor assigns Operation, which for a document
    /// being loaded means the property was present in the file.
    bool operationInitialized {false};
};

using FeatureAddSubPython = App::FeaturePythonT<FeatureAddSub>;

class FeatureAdditivePython: public FeatureAddSubPython
{
    PROPERTY_HEADER_WITH_OVERRIDE(PartDesign::FeatureAdditivePython);

public:
    FeatureAdditivePython();
    ~FeatureAdditivePython() override;
};

class FeatureSubtractivePython: public FeatureAddSubPython
{
    PROPERTY_HEADER_WITH_OVERRIDE(PartDesign::FeatureSubtractivePython);

public:
    FeatureSubtractivePython();
    ~FeatureSubtractivePython() override;
};

}  // namespace PartDesign
