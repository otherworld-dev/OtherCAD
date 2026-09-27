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

#include <vector>

#include <QString>
#include <QStringList>
#include <QWidget>

#include <FCGlobal.h>

class QLineEdit;
class QPoint;
class QToolButton;
class QVBoxLayout;

namespace Gui
{
namespace Ribbon
{

/**
 * The palette Fusion opens on S: a popup at the cursor holding the commands the
 * user pinned, the ones they ran last, and a search field over every command
 * the application has registered.
 *
 * It is a popup rather than a dialog, so it closes as soon as the user clicks
 * or types past it, and the command a tile runs is invoked once the popup has
 * closed: a command that opens its own dialog must not do so under a widget
 * that holds the mouse and keyboard grab.
 * @author FuCad contributors
 */
class GuiExport CommandPalette: public QWidget
{
    Q_OBJECT

public:
    /// The one and only instance, created on first use.
    static CommandPalette* instance();
    static void destruct();

    /**
     * Notes that \a command ran so that the Recent section can offer it again.
     * Called for every command the application invokes, including those the
     * palette itself started, and works before the palette has ever been shown.
     */
    static void noteCommandUsed(const char* command);

    /// Notes that \a command, one that changes the document, ran at the user's request,
    /// which makes it the one Repeat runs again.
    static void noteRepeatable(const char* command);
    /// The command Repeat runs again, or an empty string before there is one
    static QString lastRepeatable();

    /// Shows the palette at the mouse cursor with the caret in the search field.
    void popUp();

protected:
    void keyPressEvent(QKeyEvent* event) override;
    /**
     * Lets the arrow keys drive the tile grid before the search field sees them,
     * which it would otherwise swallow to move its own caret.
     */
    bool eventFilter(QObject* watched, QEvent* event) override;

private:
    CommandPalette();
    ~CommandPalette() override = default;

    void buildLayout();
    /// Fills the body with either the pinned and recent sections or the search results.
    void rebuild();
    void clearBody();
    /**
     * Appends \a caption over a grid of tiles for \a commands, dropping the ones
     * that are not registered. Does nothing when none of them resolve.
     */
    void addSection(const QString& caption, const QStringList& commands);
    QToolButton* createTile(const QString& command, QWidget* parent);

    /// The commands whose name, title or tooltip contain every word of \a query.
    static QStringList search(const QString& query);

    /// Closes the palette and then runs \a command.
    void launchCommand(const QString& command);
    void showTileMenu(const QString& command, const QPoint& where);
    void togglePinned(const QString& command);

    /**
     * Handles the grid movement keys of \a event and answers whether it did.
     * Down steps into the grid; Up, Left, Right, Home and End only move a tile
     * once the cursor is in it, so that a query can still be edited normally.
     */
    bool navigate(const QKeyEvent* event);
    /// Moves the keyboard cursor by \a rows and \a columns of the tile grid.
    void moveCurrentTile(int rows, int columns);
    /// Highlights the tile at \a index; an index outside the grid is ignored.
    void setCurrentTile(int index);
    /// The visual row the tile at \a index sits in.
    int rowOfTile(int index) const;
    /// Runs the tile under the cursor, or the first one while it sits nowhere.
    void activateCurrentTile();
    /// Takes the keyboard cursor out of the grid again.
    void clearCurrentTile();
    /// The first enabled tile at or after \a index walking by \a step, or -1.
    int enabledTileNear(int index, int step) const;

    static CommandPalette* _instance;

    QLineEdit* searchField;
    QWidget* body;
    QVBoxLayout* bodyLayout;
    /// Every tile of the body, in reading order across all of its sections.
    std::vector<QToolButton*> tiles;
    /// Index into tiles of the first tile of each visual row, ascending.
    std::vector<int> tileRows;
    /// The tile the arrow keys sit on, -1 while they sit nowhere.
    int currentTile {-1};

    Q_DISABLE_COPY(CommandPalette)
};

}  // namespace Ribbon
}  // namespace Gui
