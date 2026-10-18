// SPDX-License-Identifier: LGPL-2.1-or-later
/***************************************************************************
 *   Copyright (c) 2026 OtherCAD contributors                               *
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

#include <cmath>

#include <Inventor/nodes/SoCamera.h>
#include <QApplication>
#include <QWidget>

#include "Navigation/NavigationStyle.h"
#include "View3DInventorViewer.h"


using namespace Gui;

namespace
{
/// How far the pointer travels before the right button is navigating rather than
/// clicking. Small enough that an orbit does not feel stuck at the start, and
/// larger than the jitter of a right click on a trackpad, whose release the
/// context menu and the Sketcher's tools are both waiting for.
constexpr int clickTravel = 4;

/// The same distance in the device pixels events are measured in, so that the
/// threshold is the same reach of the hand on a scaled display as on a plain one.
int clickTravelOn(const View3DInventorViewer* viewer)
{
    const QWidget* widget = viewer ? viewer->getGLWidget() : nullptr;
    const double ratio = widget ? widget->devicePixelRatioF() : 1.0;
    return static_cast<int>(std::lround(clickTravel * ratio));
}

bool hasLeftTheClick(const SbVec2s& from, const SbVec2s& to, int travel)
{
    const int across = to[0] - from[0];
    const int down = to[1] - from[1];
    return across * across + down * down > travel * travel;
}
}  // namespace

// ----------------------------------------------------------------------------------

/* TRANSLATOR Gui::FusionNavigationStyle */

/**
 * Mirrors the default "Fusion" mouse preset of Autodesk Fusion:
 * the middle button pans, Shift + middle orbits, and the wheel or
 * Ctrl + Shift + middle zooms. Selection stays on the left button.
 *
 * A laptop trackpad or a two-button mouse has no middle button to press, which
 * would leave the view stuck, so the right button carries the same three moves:
 * on its own it orbits, with Shift it pans and with Ctrl it zooms. A right
 * click that does not drag still opens the context menu.
 */

TYPESYSTEM_SOURCE(Gui::FusionNavigationStyle, Gui::UserNavigationStyle)

FusionNavigationStyle::FusionNavigationStyle() = default;

FusionNavigationStyle::~FusionNavigationStyle() = default;

const char* FusionNavigationStyle::mouseButtons(ViewerMode mode)
{
    switch (mode) {
        case NavigationStyle::SELECTION:
            return QT_TR_NOOP("Press left mouse button");
        case NavigationStyle::PANNING:
            return QT_TR_NOOP("Press middle mouse button\nor press Shift and right mouse button");
        case NavigationStyle::DRAGGING:
            return QT_TR_NOOP("Press Shift and middle mouse button\nor press right mouse button");
        case NavigationStyle::ZOOMING:
            return QT_TR_NOOP(
                "Scroll mouse wheel\nor press Ctrl, Shift and middle mouse button"
                "\nor press Ctrl and right mouse button"
            );
        default:
            // The preferences dialog only ever asks for the four modes above, so
            // this is the catch-all rather than a line anyone reads today.
            return QT_TR_NOOP(
                "Select with the left mouse button, orbit with the right one or with Shift and "
                "the middle one, pan with the middle one or with Shift and the right one, and "
                "zoom with the wheel or with Ctrl and the right one."
            );
    }
}

SbBool FusionNavigationStyle::processSoEvent(const SoEvent* const ev)
{
    // Events when in "ready-to-seek" mode are ignored, except those
    // which influence the seek mode itself -- these are handled further
    // up the inheritance hierarchy.
    if (this->isSeekMode()) {
        return inherited::processSoEvent(ev);
    }
    // Switch off viewing mode (Bug #0000911)
    if (!this->isSeekMode() && !this->isAnimating() && this->isViewing()) {
        this->setViewing(false);  // by default disable viewing mode to render the scene
    }

    const SoType type(ev->getTypeId());

    const SbViewportRegion& vp = viewer->getSoRenderManager()->getViewportRegion();
    const SbVec2s pos(ev->getPosition());
    const SbVec2f posn = normalizePixelPos(pos);

    const SbVec2f prevnormalized = this->lastmouseposition;
    this->lastmouseposition = posn;

    // Set to true if any event processing happened. Note that it is not
    // necessary to restrict ourselves to only do one "action" for an
    // event, we only need this flag to see if any processing happened
    // at all.
    SbBool processed = false;
    bool triedSelectionDrag = false;

    const ViewerMode curmode = this->currentmode;
    ViewerMode newmode = curmode;

    // Mismatches in state of the modifier keys happens if the user
    // presses or releases them outside the viewer window.
    syncModifierKeys(ev);

    // give the nodes in the foreground root the chance to handle events (e.g color bar)
    if (!viewer->isEditing()) {
        processed = handleEventInForeground(ev);
        if (processed) {
            return true;
        }
    }

    // Keyboard handling
    if (type.isDerivedFrom(SoKeyboardEvent::getClassTypeId())) {
        const auto event = static_cast<const SoKeyboardEvent*>(ev);
        processed = processKeyboardEvent(event);
    }

    // Mouse Button / Spaceball Button handling
    if (type.isDerivedFrom(SoMouseButtonEvent::getClassTypeId())) {
        const auto* const event = (const SoMouseButtonEvent*)ev;
        const int button = event->getButton();
        const SbBool press = event->getState() == SoButtonEvent::DOWN ? true : false;

        switch (button) {
            case SoMouseButtonEvent::BUTTON1:
                this->lockrecenter = true;
                this->button1down = press;
                updateSelectionStartPosition(press, pos);
                if (press && (this->currentmode == NavigationStyle::SEEK_WAIT_MODE)) {
                    newmode = NavigationStyle::SEEK_MODE;
                    this->seekToPoint(pos);  // implicitly calls interactiveCountInc()
                    processed = true;
                }
                else if (
                    press
                    && (this->currentmode == NavigationStyle::PANNING
                        || this->currentmode == NavigationStyle::ZOOMING)
                ) {
                    newmode = NavigationStyle::DRAGGING;
                    saveCursorPosition(ev);
                    this->centerTime = ev->getTime();
                    processed = true;
                }
                else if (!press && (this->currentmode == NavigationStyle::DRAGGING)) {
                    processed = true;
                }
                else if (viewer->isEditing() && (this->currentmode == NavigationStyle::SPINNING)) {
                    processed = true;
                }
                else {
                    processed = processClickEvent(event);
                }
                break;
            case SoMouseButtonEvent::BUTTON2:
                // If we are in edit mode then simply ignore the RMB events
                // to pass the event to the base class.
                this->lockrecenter = true;

                if (press) {
                    this->rightPressPosition = pos;
                }

                // Don't show the context menu after dragging, panning or zooming
                if (!press && (hasDragged || hasPanned || hasZoomed)) {
                    processed = true;
                }
                else if (!press && !viewer->isEditing()) {
                    // Pressing the button is what starts an orbit, so the mode is
                    // already DRAGGING by the time a plain click is let go of;
                    // the flags above are what tell a click from a drag.
                    if (this->currentmode != NavigationStyle::ZOOMING
                        && this->currentmode != NavigationStyle::PANNING) {
                        if (this->isPopupMenuEnabled()) {
                            this->openPopupMenu(event->getPosition());
                        }
                    }
                }
                // Alternative way of rotating & zooming
                if (press
                    && (this->currentmode == NavigationStyle::PANNING
                        || this->currentmode == NavigationStyle::ZOOMING)) {
                    newmode = NavigationStyle::DRAGGING;
                    saveCursorPosition(ev);
                    this->centerTime = ev->getTime();
                    processed = true;
                }
                this->button2down = press;
                break;
            case SoMouseButtonEvent::BUTTON3:
                if (press) {
                    this->centerTime = ev->getTime();
                    setupPanningPlane(getCamera());
                    this->lockrecenter = false;
                }
                else {
                    SbTime tmp = (ev->getTime() - this->centerTime);
                    float dci = (float)QApplication::doubleClickInterval() / 1000.0f;
                    // is it just a middle click?
                    if (tmp.getValue() < dci && !this->lockrecenter) {
                        lookAtPoint(pos);
                        processed = true;
                    }
                }
                this->button3down = press;
                break;
            default:
                break;
        }
    }

    // Mouse Movement handling
    if (type.isDerivedFrom(SoLocation2Event::getClassTypeId())) {
        this->lockrecenter = true;
        const auto* const event = (const SoLocation2Event*)ev;
        if (this->currentmode == NavigationStyle::SELECTION && this->button1down) {
            triedSelectionDrag = true;
            processed = handleSelectionDragMotion(event, newmode, this->ctrldown);
        }
        else if (this->currentmode == NavigationStyle::ZOOMING) {
            this->zoomByCursor(posn, prevnormalized);
            processed = true;
        }
        else if (this->currentmode == NavigationStyle::PANNING) {
            float ratio = vp.getViewportAspectRatio();
            panCamera(
                viewer->getSoRenderManager()->getCamera(),
                ratio,
                this->panningplane,
                posn,
                prevnormalized
            );
            processed = true;
        }
        else if (this->currentmode == NavigationStyle::DRAGGING) {
            this->addToLog(event->getPosition(), event->getTime());
            this->spin(posn);
            moveCursorPosition();
            // spin() only counts as a drag once it has two positions to turn the
            // camera between, and the right button has a context menu waiting on
            // the answer. Getting here with it down already took a drag's worth
            // of travel, so this is one too.
            if (this->button2down) {
                hasDragged = true;
            }
            processed = true;
        }
    }

    // Spaceball & Joystick handling
    if (type.isDerivedFrom(SoMotion3Event::getClassTypeId())) {
        const auto* const event = static_cast<const SoMotion3Event*>(ev);
        if (event) {
            this->processMotionEvent(event);
        }
        processed = true;
    }

    enum
    {
        BUTTON1DOWN = 1 << 0,
        BUTTON3DOWN = 1 << 1,
        CTRLDOWN = 1 << 2,
        SHIFTDOWN = 1 << 3,
        BUTTON2DOWN = 1 << 4
    };
    unsigned int combo = (this->button1down ? BUTTON1DOWN : 0)
        | (this->button2down ? BUTTON2DOWN : 0) | (this->button3down ? BUTTON3DOWN : 0)
        | (this->ctrldown ? CTRLDOWN : 0) | (this->shiftdown ? SHIFTDOWN : 0);

    // Whether the right button has gone far enough from where it went down to
    // be navigating rather than clicking. Once a mode has been entered it stays
    // entered, so coming back to the middle of the drag does not stop it.
    const bool rightHasTravelled = this->button2down
        && hasLeftTheClick(this->rightPressPosition, pos, clickTravelOn(viewer));

    switch (combo) {
        case 0:
            if (curmode == NavigationStyle::SPINNING) {
                break;
            }
            newmode = NavigationStyle::IDLE;
            // The left mouse button has been released right now
            if (this->lockButton1) {
                this->lockButton1 = false;
                if (curmode != NavigationStyle::SELECTION) {
                    processed = true;
                }
            }
            break;
        case BUTTON1DOWN:
        case CTRLDOWN | BUTTON1DOWN:
            if (newmode == NavigationStyle::INTERACT) {
                break;
            }
            // make sure not to change the selection when stopping spinning
            if (curmode == NavigationStyle::SPINNING
                || (this->lockButton1 && curmode != NavigationStyle::SELECTION)) {
                newmode = NavigationStyle::IDLE;
            }
            else {
                newmode = NavigationStyle::SELECTION;
            }
            break;
        case BUTTON3DOWN:
            // Middle button alone pans, as in Fusion
            newmode = NavigationStyle::PANNING;
            break;
        case SHIFTDOWN | BUTTON3DOWN:
            // Shift + middle button orbits
            if (newmode != NavigationStyle::DRAGGING) {
                saveCursorPosition(ev);
            }
            newmode = NavigationStyle::DRAGGING;
            break;
        case CTRLDOWN | SHIFTDOWN | BUTTON3DOWN:
            // Ctrl + Shift + middle button zooms
            newmode = NavigationStyle::ZOOMING;
            break;
        case BUTTON2DOWN:
            // The right button orbits for the mice and trackpads that have no
            // middle button to hold, but not until the pointer has left the
            // click behind. Entering the mode on the press would show the
            // rotation centre and the orbit cursor on every right click, and
            // the jitter of one would swallow the release the context menu and
            // the Sketcher's tools are waiting for.
            if (curmode != NavigationStyle::DRAGGING && !rightHasTravelled) {
                break;
            }
            if (newmode != NavigationStyle::DRAGGING) {
                saveCursorPosition(ev);
            }
            newmode = NavigationStyle::DRAGGING;
            break;
        case SHIFTDOWN | BUTTON2DOWN:
            // Shift + right button pans, as Shift does on the middle button
            if (curmode != NavigationStyle::PANNING && !rightHasTravelled) {
                break;
            }
            newmode = NavigationStyle::PANNING;
            break;
        case CTRLDOWN | BUTTON2DOWN:
            // Ctrl + right button zooms
            if (curmode != NavigationStyle::ZOOMING && !rightHasTravelled) {
                break;
            }
            newmode = NavigationStyle::ZOOMING;
            break;

        default:
            // Reset mode to IDLE when a navigation button is released while a modifier is
            // still held. Without this an orbit or zoom would keep going after the mouse
            // button is up.
            if ((curmode == NavigationStyle::PANNING || curmode == NavigationStyle::ZOOMING
                 || curmode == NavigationStyle::DRAGGING)
                && !this->button2down && !this->button3down) {
                newmode = NavigationStyle::IDLE;
            }
            break;
    }

    // If the selection button is pressed together with another button
    // and the other button is released, don't switch to selection mode.
    // Process when selection button is pressed together with other buttons that could trigger
    // different actions.
    if (this->button1down && (this->button2down || this->button3down)) {
        this->lockButton1 = true;
        processed = true;
    }

    // Prevent interrupting rubber-band selection in sketcher
    if (viewer->isEditing() && curmode == NavigationStyle::SELECTION
        && newmode != NavigationStyle::IDLE) {
        newmode = NavigationStyle::SELECTION;
        processed = false;
    }

    // Reset flags when newmode is IDLE and the buttons are released
    if (newmode == IDLE && !button1down && !button2down && !button3down) {
        hasPanned = false;
        hasDragged = false;
        hasZoomed = false;
    }

    if (newmode != curmode) {
        this->setViewingMode(newmode);
    }

    // If not handled in this class, pass on upwards in the inheritance
    // hierarchy.
    if (!processed && !triedSelectionDrag) {
        processed = inherited::processSoEvent(ev);
    }

    return processed;
}
