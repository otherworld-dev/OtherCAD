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

#include "DlgChangeParameters.h"

#include <QComboBox>
#include <QDialogButtonBox>
#include <QFormLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTimer>
#include <QTreeWidget>
#include <QTreeWidgetItemIterator>
#include <QVBoxLayout>

#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Expression.h>
#include <App/Property.h>
#include <App/VarSet.h>
#include <Base/Exception.h>
#include <Base/Quantity.h>

#include <Gui/Application.h>
#include <Gui/BitmapFactory.h>
#include <Gui/ViewProvider.h>

using namespace Gui::Dialog;
namespace Params = Gui::ModelParameters;

namespace
{
/// What a row of the tree is
enum class Row
{
    Heading,
    Object,
    User,
    Model
};

constexpr int rowRole = Qt::UserRole;
/// A user parameter's name, or a model value's index in modelValues
constexpr int idRole = Qt::UserRole + 1;
/// Names the row across a refresh
constexpr int keyRole = Qt::UserRole + 2;

QString unitText(const Base::Unit& unit)
{
    if (unit == Base::Unit::One) {
        return {};
    }
    double factor {};
    std::string text;
    Base::Quantity(1.0, unit).getUserString(factor, text);
    return QString::fromStdString(text);
}

/// Fills a value's unit, expression and value columns
void fillValue(QTreeWidgetItem* item, App::DocumentObject* object, const App::ObjectIdentifier& path)
{
    Base::Quantity value;
    if (!Params::valueOf(path, value)) {
        return;
    }
    const QString valueText = QString::fromStdString(value.getUserString());
    item->setText(DlgChangeParameters::UnitColumn, unitText(value.getUnit()));
    item->setText(DlgChangeParameters::ValueColumn, valueText);
    if (auto expr = object->getExpression(path).expression) {
        item->setText(
            DlgChangeParameters::ExpressionColumn,
            QString::fromStdString(Params::displayText(object, *expr))
        );
    }
    else {
        // A plain value is its own expression, ready to be typed over
        item->setText(DlgChangeParameters::ExpressionColumn, valueText);
    }
}

bool isEditableColumn(Row row, int column)
{
    switch (row) {
        case Row::User:
            return column == DlgChangeParameters::NameColumn
                || column == DlgChangeParameters::ExpressionColumn
                || column == DlgChangeParameters::CommentColumn;
        case Row::Model:
            return column == DlgChangeParameters::ExpressionColumn;
        default:
            return false;
    }
}

Row rowOf(const QTreeWidgetItem* item)
{
    return item ? static_cast<Row>(item->data(0, rowRole).toInt()) : Row::Heading;
}
}  // namespace

DlgChangeParameters::DlgChangeParameters(App::Document* doc, QWidget* parent)
    : QDialog(parent)
    , document(doc)
    , tree(new QTreeWidget(this))
    , addButton(new QPushButton(tr("Add"), this))
    , deleteButton(new QPushButton(tr("Delete"), this))
    , status(new QLabel(this))
{
    setObjectName(QStringLiteral("ChangeParametersDialog"));
    setWindowTitle(tr("Parameters"));
    resize(760, 480);

    tree->setObjectName(QStringLiteral("ParameterTree"));
    tree->setHeaderLabels({tr("Parameter"), tr("Unit"), tr("Expression"), tr("Value"), tr("Comments")});
    tree->setAlternatingRowColors(true);
    tree->setUniformRowHeights(true);
    // Only some columns can be edited, so editing starts here rather than from the triggers
    tree->setEditTriggers(QAbstractItemView::NoEditTriggers);

    addButton->setObjectName(QStringLiteral("AddParameterButton"));
    addButton->setIcon(BitmapFactory().iconFromTheme("list-add"));
    addButton->setToolTip(tr("Add a user parameter"));
    deleteButton->setObjectName(QStringLiteral("DeleteParameterButton"));
    deleteButton->setIcon(BitmapFactory().iconFromTheme("list-remove"));
    deleteButton->setToolTip(tr("Delete the selected user parameter"));
    status->setObjectName(QStringLiteral("ParameterStatus"));
    status->setWordWrap(true);
    status->setTextInteractionFlags(Qt::TextSelectableByMouse);

    auto* close = new QDialogButtonBox(QDialogButtonBox::Close, this);
    auto* buttons = new QHBoxLayout;
    buttons->addWidget(addButton);
    buttons->addWidget(deleteButton);
    buttons->addWidget(status, 1);
    buttons->addWidget(close);
    auto* layout = new QVBoxLayout(this);
    layout->addWidget(tree);
    layout->addLayout(buttons);

    connect(close, &QDialogButtonBox::rejected, this, &QDialog::reject);
    connect(addButton, &QPushButton::clicked, this, &DlgChangeParameters::addParameter);
    connect(deleteButton, &QPushButton::clicked, this, &DlgChangeParameters::deleteParameter);
    connect(tree, &QTreeWidget::itemChanged, this, &DlgChangeParameters::onItemChanged);
    connect(tree, &QTreeWidget::currentItemChanged, this, &DlgChangeParameters::updateButtons);
    connect(tree, &QTreeWidget::itemDoubleClicked, this, [this](QTreeWidgetItem* item, int column) {
        if (isEditableColumn(rowOf(item), column) && (item->flags() & Qt::ItemIsEditable)) {
            tree->editItem(item, column);
        }
    });

    refresh();
    tree->header()->resizeSections(QHeaderView::ResizeToContents);
}

DlgChangeParameters::~DlgChangeParameters() = default;

void DlgChangeParameters::refresh()
{
    filling = true;
    QString current;
    if (QTreeWidgetItem* item = tree->currentItem()) {
        current = item->data(0, keyRole).toString();
    }
    tree->clear();
    userRoot = nullptr;
    modelRoot = nullptr;

    auto heading = [this](const QString& text, const QString& key) {
        auto* item = new QTreeWidgetItem(tree, {text});
        QFont font = item->font(0);
        font.setBold(true);
        item->setFont(0, font);
        item->setData(0, rowRole, static_cast<int>(Row::Heading));
        item->setData(0, keyRole, key);
        item->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        return item;
    };

    userRoot = heading(tr("User Parameters"), QStringLiteral("user"));
    App::VarSet* set = Params::find(document);
    for (App::Property* prop : Params::userParameters(document)) {
        const QString name = QString::fromLatin1(prop->getName());
        auto* item = new QTreeWidgetItem(userRoot, {name});
        item->setData(0, rowRole, static_cast<int>(Row::User));
        item->setData(0, idRole, name);
        item->setData(0, keyRole, QStringLiteral("user:") + name);
        item->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
        fillValue(item, set, App::ObjectIdentifier(*prop));
        item->setText(CommentColumn, QString::fromUtf8(prop->getDocumentation()));
    }

    modelRoot = heading(tr("Model Parameters"), QStringLiteral("model"));
    modelValues = Params::modelValues(document);
    App::DocumentObject* last = nullptr;
    QTreeWidgetItem* objectItem = nullptr;
    for (std::size_t i = 0; i < modelValues.size(); ++i) {
        const Params::ModelValue& value = modelValues[i];
        if (value.object != last) {
            last = value.object;
            objectItem = new QTreeWidgetItem(modelRoot, {QString::fromUtf8(last->Label.getValue())});
            objectItem->setData(0, rowRole, static_cast<int>(Row::Object));
            objectItem->setData(
                0,
                keyRole,
                QStringLiteral("object:") + QString::fromLatin1(last->getNameInDocument())
            );
            if (ViewProvider* vp = Application::Instance->getViewProvider(last)) {
                objectItem->setIcon(0, vp->getIcon());
            }
            objectItem->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        }
        auto* item = new QTreeWidgetItem(objectItem, {QString::fromStdString(value.name)});
        item->setData(0, rowRole, static_cast<int>(Row::Model));
        item->setData(0, idRole, static_cast<int>(i));
        item->setData(
            0,
            keyRole,
            QStringLiteral("model:%1:%2")
                .arg(QString::fromLatin1(last->getNameInDocument()), QString::fromStdString(value.name))
        );
        Qt::ItemFlags flags = Qt::ItemIsEnabled | Qt::ItemIsSelectable;
        if (value.editable) {
            flags |= Qt::ItemIsEditable;
        }
        else {
            item->setToolTip(
                ExpressionColumn,
                tr("This value is set by the model and cannot be changed here")
            );
            item->setForeground(ExpressionColumn, palette().brush(QPalette::Disabled, QPalette::Text));
        }
        item->setFlags(flags);
        fillValue(item, value.object, value.path);
    }

    for (QTreeWidgetItem* root : {userRoot, modelRoot}) {
        root->setFirstColumnSpanned(true);
    }
    tree->expandAll();

    for (QTreeWidgetItemIterator it(tree); *it; ++it) {
        if ((*it)->data(0, keyRole).toString() == current) {
            tree->setCurrentItem(*it);
            break;
        }
    }
    filling = false;
    updateButtons();
}

void DlgChangeParameters::updateButtons()
{
    deleteButton->setEnabled(rowOf(tree->currentItem()) == Row::User);
}

void DlgChangeParameters::setStatus(const QString& message)
{
    status->setText(message);
}

bool DlgChangeParameters::change(const char* name, const std::function<void()>& edit)
{
    document->openTransaction(name);
    try {
        edit();
        document->commitTransaction();
    }
    catch (const Base::Exception& error) {
        document->abortTransaction();
        setStatus(QString::fromUtf8(error.what()));
        return false;
    }
    catch (const std::exception&) {
        // Such as a value of the wrong type for the property
        document->abortTransaction();
        setStatus(tr("This value cannot be set here"));
        return false;
    }
    // Recomputed after the commit, as a typed value in the property editor is; the model
    // showing an error is the user's to see and undo, not a reason to refuse the edit
    document->recompute();
    setStatus({});
    return true;
}

void DlgChangeParameters::addParameter()
{
    QDialog form(this);
    form.setObjectName(QStringLiteral("AddParameterDialog"));
    form.setWindowTitle(tr("Add User Parameter"));

    auto* name = new QLineEdit(&form);
    name->setObjectName(QStringLiteral("ParameterName"));
    auto* unit = new QComboBox(&form);
    unit->setObjectName(QStringLiteral("ParameterUnit"));
    unit->addItem(tr("Length"), static_cast<int>(Params::Kind::Length));
    unit->addItem(tr("Angle"), static_cast<int>(Params::Kind::Angle));
    unit->addItem(tr("No unit"), static_cast<int>(Params::Kind::Unitless));
    auto* expression = new QLineEdit(&form);
    expression->setObjectName(QStringLiteral("ParameterExpression"));
    expression->setPlaceholderText(tr("A value, such as 10 mm, or an expression"));
    auto* comment = new QLineEdit(&form);
    comment->setObjectName(QStringLiteral("ParameterComment"));
    auto* problem = new QLabel(&form);
    problem->setObjectName(QStringLiteral("AddParameterStatus"));
    problem->setWordWrap(true);
    auto* buttons = new QDialogButtonBox(QDialogButtonBox::Ok | QDialogButtonBox::Cancel, &form);

    auto* layout = new QFormLayout(&form);
    layout->addRow(tr("Name"), name);
    layout->addRow(tr("Unit"), unit);
    layout->addRow(tr("Expression"), expression);
    layout->addRow(tr("Comment"), comment);
    layout->addRow(problem);
    layout->addRow(buttons);

    QString added;
    connect(buttons, &QDialogButtonBox::rejected, &form, &QDialog::reject);
    connect(buttons, &QDialogButtonBox::accepted, &form, [&]() {
        const std::string text = expression->text().trimmed().isEmpty()
            ? std::string("0")
            : expression->text().toStdString();
        const std::string newName = name->text().trimmed().toStdString();
        const auto kind = static_cast<Params::Kind>(unit->currentData().toInt());
        bool ok = change(QT_TRANSLATE_NOOP("Command", "Add parameter"), [&]() {
            Params::addUserParameter(document, newName, kind, text, comment->text().toStdString());
        });
        if (!ok) {
            // Said in the form, which is what the user is looking at
            problem->setText(status->text());
            setStatus({});
            return;
        }
        added = QString::fromStdString(newName);
        form.accept();
    });

    if (form.exec() != QDialog::Accepted) {
        return;
    }
    refresh();
    for (int i = 0; userRoot && i < userRoot->childCount(); ++i) {
        if (userRoot->child(i)->text(NameColumn) == added) {
            tree->setCurrentItem(userRoot->child(i));
        }
    }
}

void DlgChangeParameters::deleteParameter()
{
    QTreeWidgetItem* item = tree->currentItem();
    if (rowOf(item) != Row::User) {
        return;
    }
    const std::string name = item->data(0, idRole).toString().toStdString();
    if (change(QT_TRANSLATE_NOOP("Command", "Delete parameter"), [&]() {
            Params::removeUserParameter(document, name);
        })) {
        refresh();
    }
}

void DlgChangeParameters::onItemChanged(QTreeWidgetItem* item, int column)
{
    const Row row = rowOf(item);
    if (filling || !isEditableColumn(row, column)) {
        return;
    }
    const std::string text = item->text(column).toStdString();

    if (row == Row::User) {
        const std::string name = item->data(0, idRole).toString().toStdString();
        App::VarSet* set = Params::find(document);
        App::Property* prop = set ? set->getDynamicPropertyByName(name.c_str()) : nullptr;
        if (!prop) {
            QTimer::singleShot(0, this, &DlgChangeParameters::refresh);
            return;
        }
        switch (column) {
            case NameColumn:
                change(QT_TRANSLATE_NOOP("Command", "Rename parameter"), [&]() {
                    Params::renameUserParameter(
                        document,
                        name,
                        item->text(column).trimmed().toStdString()
                    );
                });
                break;
            case ExpressionColumn:
                change(QT_TRANSLATE_NOOP("Command", "Change parameter"), [&]() {
                    Params::apply(App::ObjectIdentifier(*prop), text);
                });
                break;
            case CommentColumn:
                change(QT_TRANSLATE_NOOP("Command", "Change parameter comment"), [&]() {
                    set->changeDynamicProperty(prop, prop->getGroup(), text.c_str());
                });
                break;
            default:
                break;
        }
    }
    else {
        const auto index = static_cast<std::size_t>(item->data(0, idRole).toInt());
        if (index < modelValues.size()) {
            const Params::ModelValue value = modelValues[index];
            change(QT_TRANSLATE_NOOP("Command", "Change parameter"), [&]() {
                Params::apply(value.path, text);
            });
        }
    }
    // Rebuilt once the editor has closed: values that depend on this one change too, and a
    // refused edit goes back to what the model holds
    QTimer::singleShot(0, this, &DlgChangeParameters::refresh);
}

#include "moc_DlgChangeParameters.cpp"
