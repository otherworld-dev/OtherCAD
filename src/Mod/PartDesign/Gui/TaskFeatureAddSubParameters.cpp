// SPDX-License-Identifier: LGPL-2.1-or-later

#include <QComboBox>
#include <QLabel>

#include <Gui/CommandT.h>
#include <Mod/PartDesign/App/FeatureAddSub.h>

#include "TaskFeatureAddSubParameters.h"

using namespace PartDesignGui;

TaskFeatureAddSubParameters::TaskFeatureAddSubParameters(
    ViewProvider* vp,
    QWidget* parent,
    const std::string& pixmapname,
    const QString& parname
)
    : TaskFeatureParameters(vp, parent, pixmapname, parname)
{}

void TaskFeatureAddSubParameters::setupOperation(QLabel* label, QComboBox* combo)
{
    // Upstream offers this control on subtractive features only, listing the two
    // operations one of those can perform. Every OtherCAD feature can perform all
    // four, so each panel carries its own operation combo covering Join, Cut,
    // Intersect and New body, and showing upstream's alongside it would put two
    // operation controls in the same dialog disagreeing about the choices.
    //
    // The widgets stay in the .ui files rather than being torn out of seven
    // panels: upstream maintains this control now, and the sensible end state is
    // for our combo to be folded into it rather than kept beside it. This is the
    // one place that has to change when that happens.
    label->setVisible(false);
    combo->setVisible(false);
}

void TaskFeatureAddSubParameters::apply()
{
    auto feature = getObject<PartDesign::FeatureAddSub>();
    if (feature && feature->getAddSubType() == PartDesign::FeatureAddSub::Type::Subtractive
        && !feature->Operation.isReadOnly()) {
        FCMD_OBJ_CMD(feature, "Operation = \"" << feature->Operation.getValueAsString() << "\"");
    }
}

#include "moc_TaskFeatureAddSubParameters.cpp"
