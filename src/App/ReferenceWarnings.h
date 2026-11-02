// SPDX-License-Identifier: LGPL-2.1-or-later

#pragma once

#include <string>
#include <vector>

#include <FCGlobal.h>

namespace App
{
class DocumentObject;

/**
 * Warnings about the element references of a feature that still builds.
 *
 * A link to an edge or face of another shape keeps the name the topological naming code
 * gave that element. When a recompute leaves no element by that name, the code looks for
 * one of the same geometry in the same place, or failing that one with the same corners,
 * and moves the link onto it. The feature then builds without a word, but on an element
 * the user may never have picked. Those moves are noted here, so that the GUI can show
 * them the way Fusion shows a feature with a warning.
 *
 * Elements renumbered by an earlier edit but found under their own name are not moves:
 * that is the naming code doing its job. A link to an element that no longer exists is
 * reported too, which only shows for a feature that builds without it.
 *
 * A move is reported for as long as the link still points at the element it was moved
 * to, and until clearReferenceWarnings() is called, which the GUI does once the feature
 * has been edited. The notes are kept in memory only.
 */

/// One line per reference of @a obj that was moved onto another element or has gone.
AppExport std::vector<std::string> getReferenceWarnings(const DocumentObject* obj);

/// Forgets the moved references of @a obj, once the user has had the chance to check them.
AppExport void clearReferenceWarnings(const DocumentObject* obj);

}  // namespace App
