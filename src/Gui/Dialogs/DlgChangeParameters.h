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

#include <functional>
#include <vector>

#include <QDialog>

#include <Gui/ModelParameters.h>

class QLabel;
class QPushButton;
class QTreeWidget;
class QTreeWidgetItem;

namespace App
{
class Document;
}

namespace Gui::Dialog
{

/// Fusion's Change Parameters: the document's user parameters, which can be added,
/// renamed, edited and deleted, and the model's own dimensions, which can be edited in the
/// same place. Every edit is one undo step and recomputes the model.
class GuiExport DlgChangeParameters: public QDialog
{
    Q_OBJECT

public:
    /// The tree's columns
    enum Column
    {
        NameColumn,
        UnitColumn,
        ExpressionColumn,
        ValueColumn,
        CommentColumn
    };

    explicit DlgChangeParameters(App::Document* doc, QWidget* parent = nullptr);
    ~DlgChangeParameters() override;

private:
    /// Rebuilds the tree from the document, keeping the current row and what is expanded
    void refresh();
    void addParameter();
    void deleteParameter();
    void onItemChanged(QTreeWidgetItem* item, int column);
    void updateButtons();
    /// Runs edit as one undo step named name and recomputes; reports a failure in the
    /// status line and undoes whatever edit did
    bool change(const char* name, const std::function<void()>& edit);
    void setStatus(const QString& message);

    App::Document* document;
    QTreeWidget* tree;
    QTreeWidgetItem* userRoot = nullptr;
    QTreeWidgetItem* modelRoot = nullptr;
    QPushButton* addButton;
    QPushButton* deleteButton;
    QLabel* status;
    std::vector<ModelParameters::ModelValue> modelValues;
    /// Set while the tree is filled, when its changes are not edits
    bool filling = false;
};

}  // namespace Gui::Dialog
