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

#include "ModelParameters.h"

#include <algorithm>
#include <cstring>
#include <map>
#include <regex>
#include <set>
#include <string_view>
#include <tuple>

#include <QCoreApplication>
#include <QStringList>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/ExpressionParser.h>
#include <App/Property.h>
#include <App/PropertyUnits.h>
#include <App/VarSet.h>
#include <Base/Exception.h>
#include <Base/Tools.h>

using namespace Gui;

namespace
{
QString tr(const char* text)
{
    return QCoreApplication::translate("Gui::ModelParameters", text);
}

/// The group a user parameter's property goes in
constexpr const char* propertyGroup = "Parameters";
/// The property type of each kind of user parameter. A length is a signed distance, since
/// an offset or a position can be negative.
const char* propertyType(ModelParameters::Kind kind)
{
    switch (kind) {
        case ModelParameters::Kind::Length:
            return "App::PropertyDistance";
        case ModelParameters::Kind::Angle:
            return "App::PropertyAngle";
        case ModelParameters::Kind::Unitless:
            break;
    }
    return "App::PropertyFloat";
}

QString unitName(const Base::Unit& unit)
{
    if (unit == Base::Unit::One) {
        return tr("no unit");
    }
    std::string type = unit.getTypeString();
    if (type.empty()) {
        type = unit.getString();
    }
    return QString::fromStdString(type).toLower();
}

/// The property named by path, as a property that can be set
App::Property* propertyOf(const App::ObjectIdentifier& path)
{
    App::DocumentObject* object = path.getDocumentObject();
    if (!object) {
        return nullptr;
    }
    return object->getPropertyByName(path.getPropertyName().c_str());
}

/// A value's object and path, the same however an expression wrote them
using ValueKey = std::pair<const App::DocumentObject*, std::string>;

ValueKey keyOf(const App::ObjectIdentifier& path)
{
    return {path.getDocumentObject(), path.getPropertyName() + path.getSubPathStr()};
}

bool isConstraintList(const App::Property* prop)
{
    return prop->getTypeId().getName() == std::string_view("Sketcher::PropertyConstraintList");
}

/// Whether obj is a modelling feature whose sizes belong in the list, as Fusion lists each
/// feature's distances and angles: a Part Design feature or a Part primitive
bool isSizedFeature(const App::DocumentObject* obj)
{
    const Base::Type type = obj->getTypeId();
    static const Base::Type datum = Base::Type::fromName("Part::Datum");
    static const Base::Type primitive = Base::Type::fromName("Part::Primitive");
    if (!datum.isBad() && type.isDerivedFrom(datum)) {
        // A datum's sizes only draw it
        return false;
    }
    if (!primitive.isBad() && type.isDerivedFrom(primitive)) {
        return true;
    }
    const std::string_view name = type.getName();
    return name.starts_with("PartDesign::") && name != "PartDesign::Body";
}

/// Whether a parameter name could be mistaken for a spreadsheet cell, such as A1
bool looksLikeCell(const std::string& name)
{
    static const std::regex cell("[A-Z]{1,2}[0-9]+");
    return std::regex_match(name, cell);
}

/// Writes each bare user parameter name in text as a path to the parameter
std::string qualify(const App::DocumentObject* owner, const std::string& text)
{
    App::VarSet* params = ModelParameters::find(owner->getDocument());
    if (!params || params == owner) {
        return text;
    }

    const auto tokens = App::ExpressionParser::tokenize(text);
    const std::string prefix = std::string(params->getNameInDocument()) + ".";
    std::string result;
    std::size_t copied = 0;
    for (std::size_t i = 0; i < tokens.size(); ++i) {
        const auto& [token, start, word] = tokens[i];
        if (!params->getDynamicPropertyByName(word.c_str())) {
            continue;
        }
        // Already part of a path, as in Pad.Length or Parameters.Length
        bool afterDot = i > 0 && std::get<2>(tokens[i - 1]) == ".";
        bool beforeDot = i + 1 < tokens.size() && std::get<2>(tokens[i + 1]) == ".";
        if (afterDot || beforeDot || start < 0) {
            continue;
        }
        auto position = static_cast<std::size_t>(start);
        if (position < copied || text.compare(position, word.size(), word) != 0) {
            continue;
        }
        result += text.substr(copied, position - copied);
        result += prefix + word;
        copied = position + word.size();
    }
    result += text.substr(copied);
    return result;
}
}  // namespace

const char* const ModelParameters::objectName = "Parameters";

App::VarSet* ModelParameters::find(const App::Document* doc)
{
    if (!doc) {
        return nullptr;
    }
    if (auto* named = dynamic_cast<App::VarSet*>(doc->getObject(objectName))) {
        return named;
    }
    // Made as Parameters001 when something else already had the name
    const std::size_t length = std::strlen(objectName);
    for (App::DocumentObject* obj : doc->getObjectsOfType(App::VarSet::getClassTypeId())) {
        const char* name = obj->getNameInDocument();
        if (name && std::strncmp(name, objectName, length) == 0) {
            return static_cast<App::VarSet*>(obj);
        }
    }
    return nullptr;
}

App::VarSet* ModelParameters::findOrCreate(App::Document* doc)
{
    if (App::VarSet* params = find(doc)) {
        return params;
    }
    return static_cast<App::VarSet*>(doc->addObject("App::VarSet", objectName));
}

std::vector<App::Property*> ModelParameters::userParameters(const App::Document* doc)
{
    std::vector<App::Property*> params;
    if (App::VarSet* set = find(doc)) {
        std::vector<std::string> names = set->getDynamicPropertyNames();
        std::ranges::sort(names, [](const std::string& a, const std::string& b) {
            return QString::fromStdString(a).compare(QString::fromStdString(b), Qt::CaseInsensitive)
                < 0;
        });
        for (const auto& name : names) {
            if (App::Property* prop = set->getDynamicPropertyByName(name.c_str())) {
                params.push_back(prop);
            }
        }
    }
    return params;
}

QString ModelParameters::checkName(const App::Document* doc, const std::string& name)
{
    if (name.empty()) {
        return tr("A parameter needs a name");
    }
    if (Base::Tools::getIdentifier(name) != name || looksLikeCell(name)
        || !App::ExpressionParser::isTokenAnIndentifier(name)) {
        return tr("%1 cannot name a parameter: use letters, digits and underscores, starting "
                  "with a letter, and not a unit, constant or function name")
            .arg(QString::fromStdString(name));
    }
    App::VarSet* params = find(doc);
    if (params && params->getPropertyByName(name.c_str())) {
        return tr("There is already a parameter called %1").arg(QString::fromStdString(name));
    }
    return {};
}

App::Property* ModelParameters::addUserParameter(
    App::Document* doc,
    const std::string& name,
    Kind kind,
    const std::string& text,
    const std::string& comment
)
{
    QString problem = checkName(doc, name);
    if (!problem.isEmpty()) {
        throw Base::NameError(problem.toStdString());
    }
    const bool made = !find(doc);
    App::VarSet* params = findOrCreate(doc);
    // Cleans up by hand too, as aborting the caller's transaction undoes nothing in a
    // document without undo
    auto undo = [&](App::Property* prop) {
        if (prop) {
            const std::string added = prop->getName();
            params->removeDynamicProperty(added.c_str());
        }
        if (made) {
            doc->removeObject(params->getNameInDocument());
        }
    };
    // Checked again against the set's own properties, such as Label
    problem = checkName(doc, name);
    if (!problem.isEmpty()) {
        undo(nullptr);
        throw Base::NameError(problem.toStdString());
    }
    App::Property* prop
        = params->addDynamicProperty(propertyType(kind), name.c_str(), propertyGroup, comment.c_str());
    if (!prop) {
        undo(nullptr);
        throw Base::RuntimeError(tr("The parameter could not be added").toStdString());
    }
    try {
        // Qualified, or argument-dependent lookup finds std::apply too
        ModelParameters::apply(App::ObjectIdentifier(*prop), text);
    }
    catch (...) {
        undo(prop);
        throw;
    }
    return prop;
}

std::vector<App::DocumentObject*> ModelParameters::usersOf(const App::Property* prop)
{
    std::vector<App::DocumentObject*> users;
    auto* owner = dynamic_cast<App::DocumentObject*>(prop->getContainer());
    if (!owner || !owner->getDocument()) {
        return users;
    }
    for (App::DocumentObject* obj : owner->getDocument()->getObjects()) {
        bool uses = false;
        for (const auto& [path, expr] : obj->ExpressionEngine.getExpressions()) {
            for (const auto& [id, hidden] : expr->getIdentifiers()) {
                try {
                    App::ObjectIdentifier target = id.canonicalPath();
                    if (target.getDocumentObject() == owner
                        && target.getPropertyName() == prop->getName()) {
                        uses = true;
                    }
                }
                catch (const Base::Exception&) {
                    // A broken reference uses nothing
                }
            }
        }
        if (uses) {
            users.push_back(obj);
        }
    }
    return users;
}

void ModelParameters::renameUserParameter(
    App::Document* doc,
    const std::string& from,
    const std::string& to
)
{
    App::VarSet* params = find(doc);
    App::Property* prop = params ? params->getDynamicPropertyByName(from.c_str()) : nullptr;
    if (!prop) {
        throw Base::RuntimeError(tr("This parameter no longer exists").toStdString());
    }
    if (from == to) {
        return;
    }
    QString problem = checkName(doc, to);
    if (!problem.isEmpty()) {
        throw Base::NameError(problem.toStdString());
    }
    // Expressions name the parameter by path, so each one is rewritten to the new name
    std::map<App::ObjectIdentifier, App::ObjectIdentifier> paths;
    paths.emplace(App::ObjectIdentifier(params, from), App::ObjectIdentifier(params, to));
    doc->renameObjectIdentifiers(paths);
    if (!params->renameDynamicProperty(prop, to.c_str())) {
        throw Base::RuntimeError(tr("The parameter could not be renamed").toStdString());
    }
}

void ModelParameters::removeUserParameter(App::Document* doc, const std::string& name)
{
    App::VarSet* params = find(doc);
    App::Property* prop = params ? params->getDynamicPropertyByName(name.c_str()) : nullptr;
    if (!prop) {
        throw Base::RuntimeError(tr("This parameter no longer exists").toStdString());
    }
    std::vector<App::DocumentObject*> users = usersOf(prop);
    if (!users.empty()) {
        QStringList labels;
        for (App::DocumentObject* user : users) {
            labels << QString::fromUtf8(user->Label.getValue());
        }
        throw Base::RuntimeError(
            tr("%1 is used by %2, so it cannot be deleted")
                .arg(QString::fromStdString(name), labels.join(QStringLiteral(", ")))
                .toStdString()
        );
    }
    params->ExpressionEngine.setValue(App::ObjectIdentifier(*prop), std::shared_ptr<App::Expression>());
    params->removeDynamicProperty(name.c_str());
}

std::string ModelParameters::displayText(const App::DocumentObject* owner, const App::Expression& expr)
{
    const std::string text = expr.toString();
    App::VarSet* params = owner ? find(owner->getDocument()) : nullptr;
    if (!params || params == owner) {
        return text;
    }
    // Drops the "Parameters." that qualify() wrote in front of each user parameter
    const auto tokens = App::ExpressionParser::tokenize(text);
    const std::string setName = params->getNameInDocument();
    std::string result;
    std::size_t copied = 0;
    for (std::size_t i = 0; i + 2 < tokens.size(); ++i) {
        const auto& [token, start, word] = tokens[i];
        if (word != setName || start < 0 || std::get<2>(tokens[i + 1]) != "."
            || !params->getDynamicPropertyByName(std::get<2>(tokens[i + 2]).c_str())) {
            continue;
        }
        bool afterPath = i > 0
            && (std::get<2>(tokens[i - 1]) == "." || std::get<2>(tokens[i - 1]) == "#");
        auto position = static_cast<std::size_t>(start);
        auto end = static_cast<std::size_t>(std::get<1>(tokens[i + 2]));
        if (afterPath || position < copied || end < position) {
            continue;
        }
        result += text.substr(copied, position - copied);
        copied = end;
        i += 1;
    }
    result += text.substr(copied);
    return result;
}

std::unique_ptr<App::Expression> ModelParameters::parse(
    const App::DocumentObject* owner,
    const std::string& text
)
{
    std::string typed = text;
    // Trimmed by hand: Base::Tools has no std::string trim
    auto first = typed.find_first_not_of(" \t");
    auto last = typed.find_last_not_of(" \t");
    typed = first == std::string::npos ? std::string() : typed.substr(first, last - first + 1);
    if (!typed.empty() && typed.front() == '=') {
        typed.erase(0, 1);
    }
    if (typed.find_first_not_of(" \t") == std::string::npos) {
        throw Base::ValueError(tr("Type a value or an expression").toStdString());
    }
    return App::ExpressionParser::parse(owner, qualify(owner, typed).c_str());
}

bool ModelParameters::isConstant(const App::Expression& expr)
{
    return expr.getIdentifiers().empty();
}

Base::Quantity ModelParameters::evaluate(const App::Expression& expr, const Base::Unit& unit)
{
    std::unique_ptr<App::Expression> result(expr.eval());
    auto* number = freecad_cast<App::NumberExpression*>(result.get());
    if (!number) {
        throw Base::TypeError(tr("The expression does not give a number").toStdString());
    }
    Base::Quantity value = number->getQuantity();
    if (value.isDimensionless()) {
        value.setUnit(unit);
        return value;
    }
    if (value.getUnit() != unit) {
        throw Base::UnitsMismatchError(
            tr("The expression gives a value in %1, but this one is in %2")
                .arg(unitName(value.getUnit()), unitName(unit))
                .toStdString()
        );
    }
    return value;
}

bool ModelParameters::valueOf(const App::ObjectIdentifier& path, Base::Quantity& value)
{
    App::any any;
    try {
        any = path.getValue(true);
    }
    catch (const Base::Exception&) {
        return false;
    }
    if (any.type() == typeid(Base::Quantity)) {
        value = App::any_cast<Base::Quantity>(any);
    }
    else if (any.type() == typeid(double)) {
        value = Base::Quantity(App::any_cast<double>(any));
    }
    else if (any.type() == typeid(float)) {
        value = Base::Quantity(App::any_cast<float>(any));
    }
    else if (any.type() == typeid(long)) {
        value = Base::Quantity(static_cast<double>(App::any_cast<long>(any)));
    }
    else if (any.type() == typeid(int)) {
        value = Base::Quantity(App::any_cast<int>(any));
    }
    else {
        return false;
    }
    return true;
}

Base::Unit ModelParameters::unitOf(const App::ObjectIdentifier& path)
{
    Base::Quantity value;
    if (!valueOf(path, value)) {
        return Base::Unit::One;
    }
    return value.getUnit();
}

void ModelParameters::apply(const App::ObjectIdentifier& path, const std::string& text)
{
    App::DocumentObject* object = path.getDocumentObject();
    App::Property* prop = propertyOf(path);
    if (!object || !prop) {
        throw Base::RuntimeError(tr("This value no longer exists").toStdString());
    }

    const Base::Unit unit = unitOf(path);
    std::shared_ptr<App::Expression> expr(parse(object, text));
    if (isConstant(*expr)) {
        Base::Quantity value = evaluate(*expr, unit);
        if (object->getExpression(path).expression) {
            object->ExpressionEngine.setValue(path, std::shared_ptr<App::Expression>());
        }
        prop->setPathValue(path, App::any(value));
        return;
    }

    std::string error = object->ExpressionEngine.validateExpression(path, expr);
    if (!error.empty()) {
        throw Base::RuntimeError(error);
    }
    // Turns away a result in the wrong unit now, rather than at the next recompute
    evaluate(*expr, unit);
    object->ExpressionEngine.setValue(path, expr);
}

std::vector<ModelParameters::ModelValue> ModelParameters::modelValues(const App::Document* doc)
{
    std::vector<ModelValue> values;
    if (!doc) {
        return values;
    }
    App::VarSet* params = find(doc);

    // Every value an expression anywhere in the document reads
    std::map<ValueKey, App::ObjectIdentifier> read;
    for (App::DocumentObject* obj : doc->getObjects()) {
        for (const auto& [path, expr] : obj->ExpressionEngine.getExpressions()) {
            for (const auto& [id, hidden] : expr->getIdentifiers()) {
                try {
                    App::ObjectIdentifier target = id.canonicalPath();
                    App::DocumentObject* owner = target.getDocumentObject();
                    if (owner && owner->getDocument() == doc && propertyOf(target)) {
                        read.emplace(keyOf(target), target);
                    }
                }
                catch (const Base::Exception&) {
                    // A broken reference names nothing to list
                }
            }
        }
    }

    for (App::DocumentObject* obj : doc->getObjects()) {
        if (obj == params || obj->getTypeId().getName().starts_with("Spreadsheet::")) {
            // User parameters are listed on their own, and a spreadsheet's aliases are
            // edited in the sheet
            continue;
        }

        std::vector<App::ObjectIdentifier> paths;
        std::set<std::string> seen;
        auto add = [&](const App::ObjectIdentifier& path) {
            if (seen.insert(keyOf(path).second).second) {
                paths.push_back(path);
            }
        };

        std::vector<App::Property*> properties;
        obj->getPropertyList(properties);
        for (App::Property* prop : properties) {
            if (!isConstraintList(prop)) {
                continue;
            }
            std::vector<App::ObjectIdentifier> named;
            prop->getPaths(named);
            for (const auto& path : named) {
                Base::Quantity value;
                // A named coincidence or tangency has nothing to edit
                if (valueOf(path, value) && !value.isDimensionless()) {
                    add(path);
                }
            }
        }
        if (isSizedFeature(obj)) {
            for (App::Property* prop : properties) {
                // A size the feature does not use now is read-only, as Length2 is for a
                // one-sided Pad
                if (prop->getTypeId().isDerivedFrom(App::PropertyQuantity::getClassTypeId())
                    && !prop->testStatus(App::Property::Hidden) && !prop->isReadOnly()
                    && (obj->getPropertyType(prop) & App::Prop_Hidden) == 0) {
                    add(App::ObjectIdentifier(*prop));
                }
            }
        }
        std::vector<App::ObjectIdentifier> linked;
        for (const auto& [path, expr] : obj->ExpressionEngine.getExpressions()) {
            linked.push_back(path);
        }
        for (const auto& [key, path] : read) {
            if (key.first == obj) {
                linked.push_back(path);
            }
        }
        std::ranges::sort(linked, [](const auto& a, const auto& b) {
            return a.toString() < b.toString();
        });
        for (const auto& path : linked) {
            add(path);
        }

        for (const auto& path : paths) {
            Base::Quantity value;
            App::Property* prop = propertyOf(path);
            if (!prop || !valueOf(path, value)) {
                continue;
            }
            ModelValue entry;
            entry.object = obj;
            entry.path = path;
            const std::string sub = path.getSubPathStr();
            // A named dimension goes by its name alone, as it does in the sketch
            entry.name = isConstraintList(prop) && sub.starts_with('.')
                ? sub.substr(1)
                : path.getPropertyName() + sub;
            entry.editable = !prop->isReadOnly();
            if (entry.editable) {
                try {
                    std::shared_ptr<App::Expression> probe(App::ExpressionParser::parse(obj, "0"));
                    entry.editable = obj->ExpressionEngine.validateExpression(path, probe).empty();
                }
                catch (const Base::Exception&) {
                    entry.editable = false;
                }
            }
            values.push_back(std::move(entry));
        }
    }
    return values;
}
