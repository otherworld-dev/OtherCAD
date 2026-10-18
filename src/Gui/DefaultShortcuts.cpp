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


#include <string>
#include <string_view>
#include <unordered_map>

#include "DefaultShortcuts.h"
#include "ShortcutManager.h"


using namespace Gui;

namespace
{
/**
 * Fusion reaches its tools with a bare letter, where FreeCAD reserves those for
 * the sketch constraints and gives the tools a G or K prefix. The letters go to
 * the tools here, and the constraints that held them move into the K prefix
 * their siblings already use.
 *
 * Modelling and sketching can share a letter because only one of the two is ever
 * enabled: a sketch constraint needs a sketch open, and a modelling command needs
 * one closed. The shortcut framework hands the key to whichever is live.
 *
 * A Fusion letter also has to win against every longer chord it happens to
 * prefix (S against "S, B"/"S, F"/"S, G"/"S, D", and so on) instead of waiting
 * ShortcutTimeout for one of those chords to complete. `ShortcutManager::
 * checkShortcut` resolves that by priority: giving every entry here
 * `otherCadPriority` below is what lets its exact match fire immediately, ahead
 * of any enabled longer sequence with a lower priority. Modelling commands
 * that must stay off while a sketch is open (PartDesign's tools,
 * `Std_Placement`, `Std_Measure`) are guarded in their own `isActive()`
 * instead of here.
 *
 * That win has a price, and this is the whole of it: a chord that begins with
 * a Fusion letter stops completing while that letter's own command is enabled.
 * The letter fires, the chord never gets its second keystroke. Which chords are
 * shadowed therefore follows the letter's `isActive()`:
 *
 *   - always, because `Std_CommandPalette` is never disabled -
 *     S: S,A S,B S,C S,D S,E S,F S,G S,H S,I S,P S,R S,S
 *   - whenever something is selected, which is when `Std_SetAppearance` is on -
 *     A: A,R A,T A,X
 *   - while no sketch is open, when the modelling letters are on -
 *     Q: Q,P Q,S / E: E,L E,Q E,X / F: F,R / H: H,A H,S /
 *     M: M,A M,I M,T M,V / I: I,C I,D I,E I,P I,S
 *   - inside a sketch, when the sketching letters are on -
 *     L: L,E L,K L,V / R: R,B R,E R,F R,O / C: C,C C,I C,L C,M C,V C,W /
 *     D: D,E D,H D,I D,L D,N D,V / T: T,E T,P T,R T,T T,U / O: O,S /
 *     P: P,A P,C P,F P,G P,I P,J P,L P,M P,N P,O P,P P,S P,T P,V P,X /
 *     X: X,S
 *
 * (The list is the state of the tree when the letters were bound; it is
 * `grep -rhoE 'sAccel *= *"[^"]+"|"Accel" *: *"[^"]+"' src/` filtered to the
 * letters above. It goes stale as workbenches gain commands, and nothing
 * enforces it.)
 *
 * Most of those chords belong to workbenches a Fusion user never loads, and all
 * of them stay reachable from their menu, their toolbar and the command palette.
 * The four that were worth moving are Part's selection filters, which used to be
 * "X, S"/"E, S"/"F, S"/"C, S" - two of them dead in any document, all four dead
 * inside a sketch - and now sit behind the free U prefix as "U, V"/"U, E"/
 * "U, F"/"U, C" (Mod/Part/Gui/CommandFilter.cpp).
 *
 * A user who wants a shadowed chord back does not have to give up the letter:
 * raising that chord's command above `otherCadPriority` (100) in
 * Preferences -> Keyboard restores the wait, because `checkShortcut` only
 * flushes the letter when its priority beats every other candidate's.
 *
 * Circle's bare "C" also used to collide head-on with the Coincident
 * constraint's default accelerator, which is a different problem: two
 * commands claiming the exact same key rather than one waiting on a longer
 * chord. That pair is not listed here - `CmdSketcherConstrainCoincidentUnified`
 * and `CmdSketcherConstrainCoincident` (CommandConstraints.cpp) instead give
 * each other mutually exclusive "K, K"/"K, Q" accelerators directly, swapping
 * which one is which based on the UnifiedCoincident preference, so only one of
 * them is ever bound to a given sequence and neither needs a priority boost
 * from this table to resolve a chord it isn't in.
 */
const std::unordered_map<std::string_view, const char*> shortcuts = {
    // Modelling, live while no sketch is open.
    {"PartDesign_PressPull", "Q"},
    {"PartDesign_Extrude", "E"},
    {"PartDesign_Fillet", "F"},
    {"PartDesign_Hole", "H"},
    {"Std_Placement", "M"},
    {"Std_Measure", "I"},
    {"Std_SetAppearance", "A"},
    {"Std_CommandPalette", "S"},
    // Fusion's J is its one Joint command; the fixed joint's panel changes the type.
    {"Assembly_CreateJointFixed", "J"},

    // Sketching, live only inside a sketch. L is the polyline, which carries on from the
    // end of each segment the way Fusion's Line does; the single line keeps "G, L".
    {"Sketcher_CreatePolyline", "L"},
    {"Sketcher_CompCreateRectangles", "R"},
    {"Sketcher_CreateCircle", "C"},
    {"Sketcher_Dimension", "D"},
    {"Sketcher_Trimming", "T"},
    {"Sketcher_Offset", "O"},
    {"Sketcher_CompExternal", "P"},
    {"Sketcher_ToggleConstruction", "X"},

    // The constraints the sketch letters displaced. Each keeps a letter that
    // says what it does, now behind the K that the other dimensions use.
    {"Sketcher_ConstrainDistanceX", "K, H"},
    // Radiam rather than the RadDia drop-down it stands in for: the drop-down only
    // builds an action while SeparatedDimensioningTools is on, so in the default
    // mode "K, C" was bound to nothing. Radiam does the same job (radius on an
    // arc, diameter on a circle) and is in the Sketcher menu in every mode.
    {"Sketcher_ConstrainRadiam", "K, C"},
    {"Sketcher_ConstrainTangent", "K, T"},
    {"Sketcher_ConstrainPointOnObject", "K, N"},
    {"Sketcher_ConstrainParallel", "K, P"},
    {"Sketcher_ConstrainSymmetric", "K, M"},
};

/// High enough to beat the commands that never asked for an order of their own,
/// low enough to leave room for a user who wants something else on top.
constexpr int otherCadPriority = 100;
}  // namespace


const char* Gui::defaultShortcutFor(const char* command)
{
    if (!command || !*command) {
        return nullptr;
    }

    const auto found = shortcuts.find(std::string_view(command));
    return found == shortcuts.end() ? nullptr : found->second;
}

void Gui::applyDefaultShortcutPriorities()
{
    ShortcutManager* manager = ShortcutManager::instance();
    for (const auto& [command, accel] : shortcuts) {
        const std::string name(command);
        if (manager->getPriority(name.c_str()) == 0) {
            manager->setPriority(name.c_str(), otherCadPriority);
        }
    }
}
