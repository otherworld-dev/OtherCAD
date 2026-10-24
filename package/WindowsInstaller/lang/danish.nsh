/*
OtherCAD Installer Language File
Language: Danish
*/

!insertmacro LANGFILE_EXT "Danish"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Installed for Current User)"

${LangFileString} TEXT_WELCOME "Denne guide vil installere OtherCAD på din computer.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compiling Python scripts..."

${LangFileString} TEXT_FINISH_DESKTOP "Create desktop shortcut"
${LangFileString} TEXT_FINISH_WEBSITE "Visit github.com/otherworld-dev/OtherCAD for the latest news, support and tips"

#${LangFileString} FileTypeTitle "OtherCAD-Dokument"

#${LangFileString} SecAllUsersTitle "Installer til alle brugere?"
${LangFileString} SecFileAssocTitle "Fil-associationer"
${LangFileString} SecDesktopTitle "Skrivebordsikon"

${LangFileString} SecCoreDescription "Filerne til OtherCAD."
#${LangFileString} SecAllUsersDescription "Installer OtherCAD til alle brugere, eller kun den aktuelle bruger."
${LangFileString} SecFileAssocDescription "Opret association mellem OtherCAD og .FCStd filer."
${LangFileString} SecDesktopDescription "Et OtherCAD ikon på skrivebordet"
#${LangFileString} SecDictionaries "Ordbøger"
#${LangFileString} SecDictionariesDescription "Spell-checker dictionaries that can be downloaded and installed."

#${LangFileString} PathName 'Sti til filen $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Kunne ikke finde $\"xxx.exe$\".'

#${LangFileString} DictionariesFailed 'Download of dictionary for language $\"$R3$\" failed.'

#${LangFileString} ConfigInfo "Den følgende konfiguration af OtherCAD vil tage et stykke tid."

#${LangFileString} RunConfigureFailed "Mislykket forsog på at afvikle konfigurations-scriptet"
${LangFileString} InstallRunning "Installationsprogrammet kører allerede!"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} er allerede installeret!$\r$\n\
				Dou you nevertheles want to install OtherCAD over the existing version?"
${LangFileString} NewerInstalled "You are trying to install an older version of OtherCAD than what you have installed.$\r$\n\
				  If you really want this, you must uninstall the existing OtherCAD $OldVersionNumber before."

#${LangFileString} FinishPageMessage "Tillykke!! OtherCAD er installeret.$\r$\n\
#					$\r$\n\
#					(Når OtherCAD startes første gang, kan det tage noget tid.)"
${LangFileString} FinishPageRun "Start OtherCAD"

${LangFileString} UnNotInRegistryLabel "Kunne ikke finde OtherCAD i registreringsdatabsen.$\r$\n\
					Genvejene på skrivebordet og i Start-menuen bliver ikke fjernet"
${LangFileString} UnInstallRunning "Du ma afslutte OtherCAD forst!"
${LangFileString} UnNotAdminLabel "Du skal have administrator-rettigheder for at afinstallere OtherCAD!"
${LangFileString} UnReallyRemoveLabel "Er du sikker på, at du vil slette OtherCAD og alle tilhørende komponenter?"
${LangFileString} UnOtherCADPreferencesTitle 'OtherCAD$\'s user preferences'

#${LangFileString} SecUnProgDescription 'Afinstallerer programmet $\"xxx$\".'
${LangFileString} SecUnPreferencesDescription 'Sletter OtherCAD$\'s konfigurations mappe$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						for alle brugere.'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Afinstallerer OtherCAD og alle dets komponenter."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
