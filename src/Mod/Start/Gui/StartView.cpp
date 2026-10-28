// SPDX-License-Identifier: LGPL-2.1-or-later
/****************************************************************************
 *                                                                          *
 *   Copyright (c) 2024 The FreeCAD Project Association AISBL               *
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


#include <QApplication>
#include <QCheckBox>
#include <QFrame>
#include <QGridLayout>
#include <QLabel>
#include <QLineEdit>
#include <QListView>
#include <QMdiSubWindow>
#include <QMessageBox>
#include <QPushButton>
#include <QScrollArea>
#include <QTimer>
#include <QWidget>
#include <QStackedWidget>
#include <QShowEvent>
#include <QTime>

#include "StartView.h"
#include "FileCardDelegate.h"
#include "FileCardView.h"
#include "FirstStartWidget.h"
#include "FlowLayout.h"
#include "NewFileButton.h"
#include <App/Document.h>
#include <App/DocumentObject.h>
#include <App/Application.h>
#include <Base/Interpreter.h>
#include <Base/Tools.h>
#include <Gui/Action.h>
#include <Gui/Application.h>
#include <Gui/Command.h>
#include <Gui/Document.h>
#include <Gui/MainWindow.h>
#include <Gui/ModuleIO.h>
#include <Gui/View3DInventor.h>
#include <Gui/View3DInventorViewer.h>
#include <gsl/pointers>
#include <string>

using namespace StartGui;

TYPESYSTEM_SOURCE_ABSTRACT(StartGui::StartView, Gui::MDIView)  // NOLINT


StartView::StartView(QWidget* parent)
    : Gui::MDIView(nullptr, parent)
    , _contents(new QStackedWidget(parent))
{
    setObjectName(QLatin1String("StartView"));
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    auto cardSpacing = static_cast<int>(hGrp->GetInt("FileCardSpacing", 16));  // NOLINT
    auto showExamples = hGrp->GetBool("ShowExamples", true);

    // Verify that the folder specified in preferences is available before showing it
    std::string customFolder(hGrp->GetASCII("CustomFolder", ""));
    bool showCustomFolder = !customFolder.empty();

    // First start page
    auto firstStartScrollArea = gsl::owner<QScrollArea*>(new QScrollArea());
    auto firstStartScrollWidget = gsl::owner<QWidget*>(new QWidget(firstStartScrollArea));
    firstStartScrollArea->setWidget(firstStartScrollWidget);
    firstStartScrollArea->setWidgetResizable(true);

    auto firstStartRegion = gsl::owner<QHBoxLayout*>(new QHBoxLayout(firstStartScrollWidget));
    firstStartRegion->setAlignment(Qt::AlignCenter);
    auto firstStartWidget = gsl::owner<FirstStartWidget*>(new FirstStartWidget(this));
    connect(firstStartWidget, &FirstStartWidget::dismissed, this, &StartView::firstStartWidgetDismissed);
    firstStartRegion->addWidget(firstStartWidget);
    _contents->addWidget(firstStartScrollArea);

    // Documents page: the ways to start on the left, the files to open on the right
    auto documentsWidget = gsl::owner<QWidget*>(new QWidget());
    documentsWidget->setObjectName(QStringLiteral("StartDocumentsPage"));
    _contents->addWidget(documentsWidget);
    auto documentsMainLayout = gsl::owner<QHBoxLayout*>(new QHBoxLayout(documentsWidget));
    documentsMainLayout->setContentsMargins({});
    documentsMainLayout->setSpacing(0);
    documentsMainLayout->addWidget(createSidebar());

    auto documentsScrollArea = gsl::owner<QScrollArea*>(new QScrollArea());
    documentsScrollArea->setObjectName(QStringLiteral("StartMainScrollArea"));
    documentsScrollArea->setFrameShape(QFrame::NoFrame);
    documentsScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarPolicy::ScrollBarAsNeeded);
    documentsScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarPolicy::ScrollBarAlwaysOff);
    documentsMainLayout->addWidget(documentsScrollArea, 1);
    auto documentsScrollWidget = gsl::owner<QWidget*>(new QWidget(documentsScrollArea));
    documentsScrollWidget->setObjectName(QStringLiteral("StartMain"));
    documentsScrollArea->setWidget(documentsScrollWidget);
    documentsScrollArea->setWidgetResizable(true);
    auto documentsContentLayout = gsl::owner<QVBoxLayout*>(new QVBoxLayout(documentsScrollWidget));
    documentsContentLayout->setSizeConstraint(QLayout::SizeConstraint::SetMinAndMaxSize);
    // The card grids keep a card spacing all round, so everything else is inset by the same
    // amount to line up with the cards
    constexpr int pageMargin = 20;
    documentsContentLayout
        ->setContentsMargins(pageMargin, pageMargin + cardSpacing, pageMargin, pageMargin);
    constexpr int sectionSpacing = 12;
    documentsContentLayout->setSpacing(sectionSpacing);

    // Greeting, and the filter that narrows every list of files below it
    auto greetingRow = gsl::owner<QHBoxLayout*>(new QHBoxLayout());
    greetingRow->setContentsMargins(cardSpacing, 0, cardSpacing, 0);
    auto greetingText = gsl::owner<QVBoxLayout*>(new QVBoxLayout());
    greetingText->setSpacing(2);
    _greetingLabel = gsl::owner<QLabel*>(new QLabel());
    _greetingLabel->setObjectName(QStringLiteral("StartGreeting"));
    QFont greetingFont = _greetingLabel->font();
    constexpr double greetingScale = 1.7;
    greetingFont.setPointSizeF(greetingFont.pointSizeF() * greetingScale);
    greetingFont.setWeight(QFont::DemiBold);
    _greetingLabel->setFont(greetingFont);
    _subtitleLabel = gsl::owner<QLabel*>(new QLabel());
    _subtitleLabel->setObjectName(QStringLiteral("StartSubtitle"));
    greetingText->addWidget(_greetingLabel);
    greetingText->addWidget(_subtitleLabel);
    greetingRow->addLayout(greetingText);
    greetingRow->addStretch();
    _filterEdit = gsl::owner<QLineEdit*>(new QLineEdit());
    _filterEdit->setObjectName(QStringLiteral("StartFilter"));
    _filterEdit->setClearButtonEnabled(true);
    constexpr int filterWidth = 240;
    _filterEdit->setFixedWidth(filterWidth);
    connect(_filterEdit, &QLineEdit::textChanged, this, &StartView::filterChanged);
    greetingRow->addWidget(_filterEdit, 0, Qt::AlignBottom);
    documentsContentLayout->addLayout(greetingRow);
    documentsContentLayout->addSpacing(sectionSpacing);

    auto recentFilesListWidget = gsl::owner<FileCardView*>(new FileCardView(_contents));
    _recentSection = createFileSection(
        recentFilesListWidget,
        &_recentFilesProxy,
        &_recentFilesLabel,
        &_recentFilesCount,
        cardSpacing
    );
    documentsContentLayout->addWidget(_recentSection);

    // Shortcuts, as key caps
    _shortcutsSection = gsl::owner<QWidget*>(new QWidget());
    _shortcutsSection->setObjectName(QStringLiteral("StartShortcuts"));
    auto shortcutsLayout = gsl::owner<QVBoxLayout*>(new QVBoxLayout(_shortcutsSection));
    shortcutsLayout->setContentsMargins(cardSpacing, 0, cardSpacing, cardSpacing);
    shortcutsLayout->setSpacing(sectionSpacing);
    _fusionControlsLabel = gsl::owner<QLabel*>(new QLabel());
    _fusionControlsLabel->setObjectName(QStringLiteral("StartSectionHeading"));
    shortcutsLayout->addWidget(_fusionControlsLabel);
    auto chipsWidget = gsl::owner<QWidget*>(new QWidget());
    constexpr int chipSpacing = 8;
    _shortcutChips = gsl::owner<FlowLayout*>(new FlowLayout(chipsWidget, 0, chipSpacing, chipSpacing));
    shortcutsLayout->addWidget(chipsWidget);
    documentsContentLayout->addWidget(_shortcutsSection);

    FileCardView* customFolderListWidget {};
    if (showCustomFolder) {
        customFolderListWidget = gsl::owner<FileCardView*>(new FileCardView(_contents));
        _customFolderSection = createFileSection(
            customFolderListWidget,
            &_customFolderProxy,
            &_customFolderLabel,
            &_customFolderCount,
            cardSpacing
        );
        documentsContentLayout->addWidget(_customFolderSection);
    }

    FileCardView* examplesListWidget {};
    if (showExamples) {
        examplesListWidget = gsl::owner<FileCardView*>(new FileCardView(_contents));
        _examplesSection = createFileSection(
            examplesListWidget,
            &_examplesProxy,
            &_examplesLabel,
            &_examplesCount,
            cardSpacing
        );
        documentsContentLayout->addWidget(_examplesSection);
    }

    // Shown when the filter matches nothing at all
    _noMatchesLabel = gsl::owner<QLabel*>(new QLabel());
    _noMatchesLabel->setObjectName(QStringLiteral("StartNoMatches"));
    _noMatchesLabel->setContentsMargins(cardSpacing, 0, cardSpacing, 0);
    _noMatchesLabel->hide();
    documentsContentLayout->addWidget(_noMatchesLabel);

    documentsContentLayout->addStretch();

    setCentralWidget(_contents);

    // Set startup widget according to the first start parameter
    auto firstStart = hGrp->GetBool("FirstStart2024", true);
    _contents->setCurrentWidget(firstStart ? firstStartScrollArea : documentsWidget);
    if (customFolderListWidget) {
        configureCustomFolderListWidget(customFolderListWidget);
    }
    if (examplesListWidget) {
        configureExamplesListWidget(examplesListWidget);
    }
    configureRecentFilesListWidget(recentFilesListWidget, _recentFilesLabel);

    QTimer::singleShot(2000, this, [this, recentFilesListWidget]() {
        auto updateFun = [this, recentFilesListWidget]() {
            configureRecentFilesListWidget(recentFilesListWidget, _recentFilesLabel);
        };
        auto recentFiles = Gui::getMainWindow()->findChild<Gui::RecentFilesAction*>();
        if (recentFiles != nullptr) {
            connect(recentFiles, &Gui::RecentFilesAction::recentFilesListModified, this, updateFun);
        }
    });

    // The counts follow the models, which fill in from worker threads
    for (auto proxy : {&_recentFilesProxy, &_examplesProxy, &_customFolderProxy}) {
        connect(proxy, &QAbstractItemModel::rowsInserted, this, &StartView::updateFileSections);
        connect(proxy, &QAbstractItemModel::rowsRemoved, this, &StartView::updateFileSections);
        connect(proxy, &QAbstractItemModel::modelReset, this, &StartView::updateFileSections);
        connect(proxy, &QAbstractItemModel::layoutChanged, this, &StartView::updateFileSections);
    }

    isInitialized = true;

    retranslateUi();
    updateFileSections();

    // NOLINTBEGIN
    _saveddoc = App::GetApplication().signalFinishSaveDocument.connect(
        [this](const App::Document& doc, const std::string&) {
            _recentFilesModel.modifiedFile(QString::fromStdString(doc.FileName.getStrValue()));
        }
    );
    // NOLINTEND
}

QWidget* StartView::createSidebar()
{
    auto sidebar = gsl::owner<QFrame*>(new QFrame());
    sidebar->setObjectName(QStringLiteral("StartSidebar"));
    constexpr int sidebarWidth = 264;
    sidebar->setFixedWidth(sidebarWidth);
    auto layout = gsl::owner<QVBoxLayout*>(new QVBoxLayout(sidebar));
    constexpr int sideMargin = 14;
    constexpr int topMargin = 22;
    layout->setContentsMargins(sideMargin, topMargin, sideMargin, sideMargin);
    layout->setSpacing(2);

    // Logo, name and version
    auto brandRow = gsl::owner<QHBoxLayout*>(new QHBoxLayout());
    constexpr int brandIndent = 8;
    brandRow->setContentsMargins(brandIndent, 0, 0, 0);
    constexpr int brandSpacing = 10;
    brandRow->setSpacing(brandSpacing);
    auto logo = gsl::owner<QLabel*>(new QLabel());
    constexpr int logoSize = 36;
    logo->setPixmap(QIcon(QStringLiteral(":/icons/othercad.svg")).pixmap(logoSize, logoSize));
    logo->setFixedSize(logoSize, logoSize);
    brandRow->addWidget(logo);
    auto brandText = gsl::owner<QVBoxLayout*>(new QVBoxLayout());
    brandText->setSpacing(0);
    _brandLabel = gsl::owner<QLabel*>(new QLabel());
    _brandLabel->setObjectName(QStringLiteral("StartBrandName"));
    QFont brandFont = _brandLabel->font();
    constexpr double brandScale = 1.3;
    brandFont.setPointSizeF(brandFont.pointSizeF() * brandScale);
    brandFont.setWeight(QFont::DemiBold);
    _brandLabel->setFont(brandFont);
    auto version = gsl::owner<QLabel*>(new QLabel(versionText()));
    version->setObjectName(QStringLiteral("StartBrandVersion"));
    brandText->addWidget(_brandLabel);
    brandText->addWidget(version);
    brandRow->addLayout(brandText);
    brandRow->addStretch();
    layout->addLayout(brandRow);
    constexpr int brandGap = 18;
    layout->addSpacing(brandGap);

    // The usual way in gets the big button, the others are listed under it
    _newDesignButton = gsl::owner<QPushButton*>(new QPushButton());
    _newDesignButton->setObjectName(QStringLiteral("StartPrimaryButton"));
    _newDesignButton->setCursor(Qt::PointingHandCursor);
    connect(_newDesignButton, &QPushButton::clicked, this, &StartView::newPartDesignFile);
    layout->addWidget(_newDesignButton);
    layout->addSpacing(4);

    configureNewFileButtons(layout);

    layout->addStretch();

    _openFirstStart = gsl::owner<QPushButton*>(new QPushButton());
    _openFirstStart->setObjectName(QStringLiteral("StartLinkButton"));
    _openFirstStart->setFlat(true);
    _openFirstStart->setCursor(Qt::PointingHandCursor);
    _openFirstStart->setIcon(QIcon(QLatin1String(":/icons/preferences-general.svg")));
    connect(_openFirstStart, &QPushButton::clicked, this, &StartView::openFirstStartClicked);
    layout->addWidget(_openFirstStart, 0, Qt::AlignLeft);

    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    _showOnStartupCheckBox = gsl::owner<QCheckBox*>(new QCheckBox());
    _showOnStartupCheckBox->setObjectName(QStringLiteral("StartShowOnStartup"));
    _showOnStartupCheckBox->setChecked(hGrp->GetBool("ShowOnStartup", true));
    connect(_showOnStartupCheckBox, &QCheckBox::toggled, this, &StartView::showOnStartupChanged);
    auto checkRow = gsl::owner<QHBoxLayout*>(new QHBoxLayout());
    checkRow->setContentsMargins(brandIndent, 4, 0, 0);
    checkRow->addWidget(_showOnStartupCheckBox);
    layout->addLayout(checkRow);

    return sidebar;
}

QWidget* StartView::createFileSection(
    FileCardView* view,
    QSortFilterProxyModel* proxy,
    QLabel** heading,
    QLabel** count,
    int cardSpacing
)
{
    auto section = gsl::owner<QWidget*>(new QWidget());
    auto layout = gsl::owner<QVBoxLayout*>(new QVBoxLayout(section));
    layout->setContentsMargins({});
    layout->setSpacing(0);

    auto headRow = gsl::owner<QHBoxLayout*>(new QHBoxLayout());
    headRow->setContentsMargins(cardSpacing, 0, cardSpacing, 0);
    constexpr int headSpacing = 8;
    headRow->setSpacing(headSpacing);
    *heading = gsl::owner<QLabel*>(new QLabel());
    (*heading)->setObjectName(QStringLiteral("StartSectionHeading"));
    *count = gsl::owner<QLabel*>(new QLabel());
    (*count)->setObjectName(QStringLiteral("StartSectionCount"));
    headRow->addWidget(*heading);
    headRow->addWidget(*count);
    headRow->addStretch();
    layout->addLayout(headRow);

    proxy->setFilterRole(static_cast<int>(Start::DisplayedFilesModelRoles::baseName));
    proxy->setFilterCaseSensitivity(Qt::CaseInsensitive);
    connect(view, &QListView::clicked, this, &StartView::fileCardSelected);
    layout->addWidget(view);
    return section;
}

QString StartView::versionText()
{
    auto& config = App::Application::Config();
    QStringList parts;
    for (const char* key :
         {"BuildVersionMajor", "BuildVersionMinor", "BuildVersionPoint", "BuildVersionBuild"}) {
        auto it = config.find(key);
        if (it == config.end() || it->second.empty()) {
            break;
        }
        parts << QString::fromStdString(it->second);
    }
    return parts.join(QLatin1Char('.'));
}

void StartView::configureNewFileButtons(QVBoxLayout* layout)
{
    _openFileButton = gsl::owner<NewFileButton*>(new NewFileButton(
        {tr("Open"), tr("CAD files and 3D models"), QLatin1String(":/icons/document-open.svg")}
    ));
    layout->addWidget(_openFileButton);

    _createHeading = gsl::owner<QLabel*>(new QLabel());
    _createHeading->setObjectName(QStringLiteral("StartSidebarHeading"));
    constexpr int headingIndent = 8;
    constexpr int headingTop = 14;
    _createHeading->setContentsMargins(headingIndent, headingTop, 0, 4);
    layout->addWidget(_createHeading);

    auto assembly = gsl::owner<NewFileButton*>(new NewFileButton(
        {tr("Assembly"),
         tr("Parts and the joints between them"),
         QLatin1String(":/icons/AssemblyWorkbench.svg")}
    ));
    auto draft = gsl::owner<NewFileButton*>(new NewFileButton(
        {tr("2D Draft"),
         tr("A drawing, viewed from the top"),
         QLatin1String(":/icons/DraftWorkbench.svg")}
    ));
    auto arch = gsl::owner<NewFileButton*>(new NewFileButton(
        {tr("BIM/Architecture"),
         tr("Buildings, viewed at room scale"),
         QLatin1String(":/icons/BIMWorkbench.svg")}
    ));
    auto newEmptyFile = gsl::owner<NewFileButton*>(new NewFileButton(
        {tr("Empty File"), tr("A blank OtherCAD document"), QLatin1String(":/icons/document-new.svg")}
    ));

    // TODO: Ensure all of the required WBs are actually available
    layout->addWidget(assembly);
    layout->addWidget(draft);
    layout->addWidget(arch);
    layout->addWidget(newEmptyFile);

    connect(newEmptyFile, &QPushButton::clicked, this, &StartView::newEmptyFile);
    connect(_openFileButton, &QPushButton::clicked, this, &StartView::openExistingFile);
    connect(assembly, &QPushButton::clicked, this, &StartView::newAssemblyFile);
    connect(draft, &QPushButton::clicked, this, &StartView::newDraftFile);
    connect(arch, &QPushButton::clicked, this, &StartView::newArchFile);
}

void StartView::filterChanged(const QString& text)
{
    for (auto proxy : {&_recentFilesProxy, &_examplesProxy, &_customFolderProxy}) {
        proxy->setFilterFixedString(text);
    }
    updateFileSections();
}

void StartView::updateFileSections()
{
    if (!isInitialized) {
        return;
    }
    const bool filtering = !_filterEdit->text().isEmpty();
    bool anyMatches = false;
    auto update = [&](QWidget* section, QSortFilterProxyModel& proxy, QLabel* count, bool wanted) {
        if (!section) {
            return;
        }
        const int rows = proxy.rowCount();
        count->setText(rows > 0 ? QString::number(rows) : QString());
        anyMatches = anyMatches || rows > 0;
        // A section the filter empties goes away rather than leaving a heading over nothing
        section->setVisible(wanted && (rows > 0 || !filtering));
        if (auto view = section->findChild<QListView*>()) {
            view->updateGeometry();
        }
    };
    update(_recentSection, _recentFilesProxy, _recentFilesCount, _hasRecentFiles);
    update(_customFolderSection, _customFolderProxy, _customFolderCount, true);
    update(_examplesSection, _examplesProxy, _examplesCount, true);
    _shortcutsSection->setVisible(!filtering);
    _noMatchesLabel->setVisible(filtering && !anyMatches);
}

void StartView::rebuildShortcutChips()
{
    while (auto item = _shortcutChips->takeAt(0)) {
        delete item->widget();
        delete item;
    }
    const std::vector<std::pair<QString, QString>> shortcuts {
        {QStringLiteral("S"), tr("Command palette")},
        {QStringLiteral("E"), tr("Extrude")},
        {QStringLiteral("Q"), tr("Press pull")},
        {QStringLiteral("H"), tr("Hole")},
        {QStringLiteral("F"), tr("Fillet")},
        {QStringLiteral("D"), tr("Dimension")},
        {tr("Right-click"), tr("Marking menu")},
        {QString(), tr("Drag the timeline to roll the history back and forward")},
    };
    for (const auto& [key, action] : shortcuts) {
        auto chip = gsl::owner<QFrame*>(new QFrame());
        chip->setObjectName(QStringLiteral("StartShortcutChip"));
        auto chipLayout = gsl::owner<QHBoxLayout*>(new QHBoxLayout(chip));
        constexpr int chipPadding = 8;
        chipLayout->setContentsMargins(
            chipPadding,
            chipPadding / 2 + 1,
            chipPadding + 2,
            chipPadding / 2 + 1
        );
        chipLayout->setSpacing(chipPadding);
        if (!key.isEmpty()) {
            auto keyLabel = gsl::owner<QLabel*>(new QLabel(key));
            keyLabel->setObjectName(QStringLiteral("StartShortcutKey"));
            keyLabel->setAlignment(Qt::AlignCenter);
            chipLayout->addWidget(keyLabel);
        }
        auto actionLabel = gsl::owner<QLabel*>(new QLabel(action));
        actionLabel->setObjectName(QStringLiteral("StartShortcutAction"));
        chipLayout->addWidget(actionLabel);
        _shortcutChips->addWidget(chip);
    }
}

QString StartView::greetingFor(const QTime& time)
{
    constexpr int noon = 12;
    constexpr int evening = 18;
    constexpr int earlyMorning = 5;
    if (time.hour() >= earlyMorning && time.hour() < noon) {
        return tr("Good morning");
    }
    if (time.hour() >= noon && time.hour() < evening) {
        return tr("Good afternoon");
    }
    return tr("Good evening");
}

void StartView::configureFileCardWidget(
    QListView* fileCardWidget,
    QSortFilterProxyModel* proxy,
    QAbstractItemModel* model,
    bool showAge
)
{
    proxy->setSourceModel(model);
    fileCardWidget->setModel(proxy);
    auto delegate = gsl::owner<FileCardDelegate*>(new FileCardDelegate(fileCardWidget));
    delegate->setShowAge(showAge);
    fileCardWidget->setItemDelegate(delegate);
}


void StartView::configureRecentFilesListWidget(QListView* recentFilesListWidget, QLabel* recentFilesLabel)
{
    Q_UNUSED(recentFilesLabel);
    _recentFilesModel.loadRecentFiles();
    if (recentFilesListWidget->model() != &_recentFilesProxy) {
        configureFileCardWidget(recentFilesListWidget, &_recentFilesProxy, &_recentFilesModel, true);
    }

    auto recentFilesGroup = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/RecentFiles"
    );
    _hasRecentFiles = recentFilesGroup->GetInt("RecentFiles", 0) != 0;
    updateFileSections();
}


void StartView::configureExamplesListWidget(QListView* examplesListWidget)
{
    _examplesModel.loadExamples();
    configureFileCardWidget(examplesListWidget, &_examplesProxy, &_examplesModel, false);
}


void StartView::configureCustomFolderListWidget(QListView* customFolderListWidget)
{
    _customFolderModel.loadCustomFolder();
    configureFileCardWidget(customFolderListWidget, &_customFolderProxy, &_customFolderModel, false);
}


void StartView::newEmptyFile()
{
    Gui::Application::Instance->commandManager().runCommandByName("Std_New");
    postStart(PostStartBehavior::switchWorkbench);
}

void StartView::newPartDesignFile()
{
    Gui::Application::Instance->commandManager().runCommandByName("Std_New");
    Gui::Application::Instance->activateWorkbench("PartDesignWorkbench");
    Gui::Application::Instance->commandManager().runCommandByName("PartDesign_Body");
    postStart(PostStartBehavior::doNotSwitchWorkbench);
}

void StartView::openExistingFile()
{
    auto originalDocument = Gui::Application::Instance->activeDocument();
    Gui::Application::Instance->commandManager().runCommandByName("Std_Open");
    Gui::Application::checkForRecomputes();
    if (Gui::Application::Instance->activeDocument() != originalDocument) {
        // Only run this if the user chose a new document to open (that is, they didn't cancel the
        // open file dialog)
        postStart(PostStartBehavior::switchWorkbench);
    }
}

void StartView::newAssemblyFile()
{
    Gui::Application::Instance->commandManager().runCommandByName("Std_New");
    Gui::Application::Instance->activateWorkbench("AssemblyWorkbench");
    Gui::Application::Instance->commandManager().runCommandByName("Assembly_CreateAssembly");
    Gui::Application::Instance->commandManager().runCommandByName("Std_Refresh");
    postStart(PostStartBehavior::doNotSwitchWorkbench);
}

void StartView::newDraftFile()
{
    Gui::Application::Instance->commandManager().runCommandByName("Std_New");
    Gui::Application::Instance->activateWorkbench("DraftWorkbench");
    Gui::Application::Instance->commandManager().runCommandByName("Std_ViewTop");
    postStart(PostStartBehavior::doNotSwitchWorkbench);
}

void StartView::newArchFile()
{
    Gui::Application::Instance->commandManager().runCommandByName("Std_New");
    try {
        Gui::Application::Instance->activateWorkbench("BIMWorkbench");
    }
    catch (...) {
        Gui::Application::Instance->activateWorkbench("ArchWorkbench");
    }

    // Set the camera zoom level to 10 m, which is more appropriate for architectural projects
    Gui::Command::doCommand(
        Gui::Command::Gui,
        "Gui.activeDocument().activeView().viewDefaultOrientation(None, 10000.0)"
    );
    postStart(PostStartBehavior::doNotSwitchWorkbench);
}

bool StartView::onHasMsg(const char* pMsg) const
{
    if (strcmp("AllowsOverlayOnHover", pMsg) == 0) {
        return false;
    }

    return MDIView::onHasMsg(pMsg);
}

void StartView::postStart(PostStartBehavior behavior)
{
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );

    if (behavior == PostStartBehavior::switchWorkbench) {
        auto wb = hGrp->GetASCII("AutoloadModule", "");
        if (wb == "$LastModule") {
            wb = App::GetApplication()
                     .GetParameterGroupByPath("User parameter:BaseApp/Preferences/General")
                     ->GetASCII("LastModule", "");
        }
        if (!wb.empty()) {
            Gui::Application::Instance->activateWorkbench(wb.c_str());
        }
    }
    if (hGrp->GetBool("closeStart", false)) {
        for (QWidget* w = this; w != nullptr; w = w->parentWidget()) {
            if (auto mdiSub = qobject_cast<QMdiSubWindow*>(w)) {
                mdiSub->close();
                return;
            }
        }
    }
}


void StartView::fileCardSelected(const QModelIndex& index)
{
    try {
        auto filename = index.data(static_cast<int>(Start::DisplayedFilesModelRoles::path)).toString();
        Gui::ModuleIO::verifyAndOpenFile(filename);
    }
    catch (Base::PyException& e) {
        Base::Console().error(e.getMessage().c_str());
    }
    catch (Base::Exception& e) {
        Base::Console().error(e.getMessage().c_str());
    }
    catch (...) {
        Base::Console().error("An unknown error occurred");
    }
}

void StartView::showOnStartupChanged(bool checked)
{
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    hGrp->SetBool("ShowOnStartup", checked);
}

void StartView::openFirstStartClicked()
{
    _contents->setCurrentIndex(0);
}

void StartView::firstStartWidgetDismissed()
{
    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    hGrp->SetBool("FirstStart2024", false);
    _contents->setCurrentIndex(1);
}

void StartView::changeEvent(QEvent* event)
{
    if (!isInitialized) {
        return;
    }

    _openFirstStart->setEnabled(true);
    Gui::Document* doc = Gui::Application::Instance->activeDocument();
    if (doc) {
        if (auto view = dynamic_cast<Gui::View3DInventor*>(doc->getActiveView())) {
            Gui::View3DInventorViewer* viewer = view->getViewer();
            if (viewer->isEditing()) {
                _openFirstStart->setEnabled(false);
            }
        }
    }

    if (event->type() == QEvent::LanguageChange) {
        this->retranslateUi();
    }

    Gui::MDIView::changeEvent(event);
}

void StartView::showEvent(QShowEvent* event)
{
    // The page can stay open all day, so the greeting is worked out again whenever it shows
    if (_greetingLabel) {
        _greetingLabel->setText(greetingFor(QTime::currentTime()));
    }
    if (auto mainWindow = Gui::getMainWindow()) {
        if (auto mdiArea = mainWindow->findChild<QMdiArea*>()) {
            connect(
                mdiArea,
                &QMdiArea::subWindowActivated,
                this,
                &StartView::onMdiSubWindowActivated,
                Qt::UniqueConnection
            );
        }
    }
    Gui::MDIView::showEvent(event);
}

void StartView::onMdiSubWindowActivated(QMdiSubWindow* subWindow)
{
    // check if start view is activated subwindow if yes, then enable updates
    // so we can once again receive paint events
    bool isOurWindow = subWindow && subWindow->isAncestorOf(this);
    setListViewUpdatesEnabled(isOurWindow);
}

void StartView::setListViewUpdatesEnabled(bool enabled)
{
    // disable updates on all QListView widgets when inactive to prevent unnecessary paint events
    QList<QListView*> listViews = findChildren<QListView*>();
    for (QListView* listView : listViews) {
        listView->setUpdatesEnabled(enabled);
        if (listView->viewport()) {
            listView->viewport()->setUpdatesEnabled(enabled);
        }
    }
}

void StartView::recentFileAdded(const QString& filename)
{
    _recentFilesModel.recentFileAdded(filename);
}

void StartView::retranslateUi()
{
    QString title = QCoreApplication::translate("Workbench", "Start");
    setWindowTitle(title);

    // The wordmark is two-tone: the suffix takes the brand teal, the deep one on a light theme
    const bool lightTheme = palette().color(QPalette::Window).lightness() > 128;  // NOLINT
    const QString teal = lightTheme ? QStringLiteral("#0d9488") : QStringLiteral("#22d3c4");
    _brandLabel->setText(QStringLiteral("Other<span style=\"color:%1\">CAD</span>").arg(teal));

    _greetingLabel->setText(greetingFor(QTime::currentTime()));
    _subtitleLabel->setText(tr("Pick up where you left off, or start something new."));
    _filterEdit->setPlaceholderText(tr("Filter files"));
    _noMatchesLabel->setText(tr("No files match the filter."));

    _newDesignButton->setText(tr("New design"));
    _newDesignButton->setToolTip(tr("Creates a parametric body, ready to sketch on"));
    _createHeading->setText(tr("CREATE"));

    if (_examplesLabel) {
        _examplesLabel->setText(tr("Examples"));
    }
    _recentFilesLabel->setText(tr("Recent"));
    _fusionControlsLabel->setText(tr("Shortcuts"));
    rebuildShortcutChips();

    auto hGrp = App::GetApplication().GetParameterGroupByPath(
        "User parameter:BaseApp/Preferences/Mod/Start"
    );
    std::string customFolder(hGrp->GetASCII("CustomFolder", ""));
    if (!customFolder.empty() && _customFolderLabel) {
        if (hGrp->GetBool("ShortCustomFolder", true)) {
            _customFolderLabel->setToolTip(QString::fromUtf8(customFolder.c_str()));
            customFolder = customFolder.substr(customFolder.find_last_of("/\\") + 1);
        }
        _customFolderLabel->setText(QString::fromUtf8(customFolder.c_str()));
    }

    _openFirstStart->setText(tr("First start setup"));
    _showOnStartupCheckBox->setText(tr("Show this page on startup"));
}
