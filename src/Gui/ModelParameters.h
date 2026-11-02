// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
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

#include <memory>
#include <string>
#include <vector>

#include <QString>

#include <App/ObjectIdentifier.h>
#include <Base/Quantity.h>
#include <Base/Unit.h>

#include <FCGlobal.h>

namespace App
{
class Document;
class DocumentObject;
class Expression;
class Property;
class VarSet;
}  // namespace App

/// A document's parameters, the way Fusion's Change Parameters dialog sees them.
///
/// User parameters are the properties of one variable set per document, named
/// "Parameters" and made when the first parameter is added. Model parameters are the
/// model's own values that matter to a design: named sketch dimensions, and any value
/// that an expression drives or that drives another one.
namespace Gui::ModelParameters
{

/// The internal name of a document's parameters object
GuiExport extern const char* const objectName;

/// What a user parameter measures, which decides its property type
enum class Kind
{
    Length,
    Angle,
    Unitless
};

/// The document's parameters object, or null before its first parameter
GuiExport App::VarSet* find(const App::Document* doc);
/// As find(), making the object when there is none; the caller holds a transaction
GuiExport App::VarSet* findOrCreate(App::Document* doc);
/// The user parameters, in the order they were added
GuiExport std::vector<App::Property*> userParameters(const App::Document* doc);

/// Why name cannot name a new user parameter of doc, or an empty string when it can
GuiExport QString checkName(const App::Document* doc, const std::string& name);

/// Adds a user parameter set from text, the way apply() sets one. The caller holds a
/// transaction and aborts it if this throws.
GuiExport App::Property* addUserParameter(
    App::Document* doc,
    const std::string& name,
    Kind kind,
    const std::string& text,
    const std::string& comment
);

/// Renames a user parameter, rewriting every expression that uses it. The caller holds a
/// transaction.
GuiExport void renameUserParameter(App::Document* doc, const std::string& from, const std::string& to);
/// Deletes a user parameter. Throws Base::Exception, naming them, while expressions use it.
GuiExport void removeUserParameter(App::Document* doc, const std::string& name);

/// The objects whose expressions use prop
GuiExport std::vector<App::DocumentObject*> usersOf(const App::Property* prop);

/// Parses text typed for a value of owner. A leading "=" is dropped, as FreeCAD's own
/// fields take one, and a bare user parameter name stands for that parameter, even where
/// owner has a property of the same name: in Fusion parameter names are global.
GuiExport std::unique_ptr<App::Expression> parse(
    const App::DocumentObject* owner,
    const std::string& text
);
/// expr as typed for a value of owner: the inverse of parse(), so user parameters go by
/// their bare names
GuiExport std::string displayText(const App::DocumentObject* owner, const App::Expression& expr);
/// Whether expr refers to nothing, so it gives a value rather than a formula
GuiExport bool isConstant(const App::Expression& expr);
/// What expr gives for a value in unit. A unitless result is taken in unit; another unit
/// throws.
GuiExport Base::Quantity evaluate(const App::Expression& expr, const Base::Unit& unit);

/// The unit of the value at path; unitless for a plain number
GuiExport Base::Unit unitOf(const App::ObjectIdentifier& path);
/// The value at path, or nothing when it is not a number
GuiExport bool valueOf(const App::ObjectIdentifier& path, Base::Quantity& value);

/// Sets the value at path from text typed for it. Text that refers to nothing sets the
/// value and drops any expression; anything else binds the value to that expression.
/// Throws Base::Exception when the text does not fit the value.
GuiExport void apply(const App::ObjectIdentifier& path, const std::string& text);

/// One of the model's own values
struct GuiExport ModelValue
{
    App::DocumentObject* object = nullptr;
    App::ObjectIdentifier path;
    /// The constraint's name, or the property path
    std::string name;
    /// False for one that cannot be set, such as a reference dimension
    bool editable = true;
};

/// The model's named dimensions, its features' sizes and its expression-linked values,
/// object by object
GuiExport std::vector<ModelValue> modelValues(const App::Document* doc);

}  // namespace Gui::ModelParameters
