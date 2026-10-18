/*
OtherCAD Installer Language File
Language: Swedish
*/

!insertmacro LANGFILE_EXT "Swedish"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Installerad för aktuell användare)"

${LangFileString} TEXT_WELCOME "Denna guide tar dig igenom installationen av $(^NameDA), $\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Kompilerar Pythonskript..."

${LangFileString} TEXT_FINISH_DESKTOP "Skapa skrivbordsgenväg"
${LangFileString} TEXT_FINISH_WEBSITE "Besök github.com/otherworld-dev/OtherCAD för de senaste nyheterna, support och tips"

#${LangFileString} FileTypeTitle "OtherCAD-dokument"

#${LangFileString} SecAllUsersTitle "Installera för alla användare?"
${LangFileString} SecFileAssocTitle "Filassociationer"
${LangFileString} SecDesktopTitle "Skrivbordsikon"

${LangFileString} SecCoreDescription "OtherCAD-filerna."
#${LangFileString} SecAllUsersDescription "Installera OtherCAD för alla användare, eller enbart för den aktuella användaren."
${LangFileString} SecFileAssocDescription "Filer med ändelsen .FCStd kommer att automatiskt öppnas i OtherCAD."
${LangFileString} SecDesktopDescription "En OtherCAD-ikon på skrivbordet."
#${LangFileString} SecDictionaries "Ordböcker"
#${LangFileString} SecDictionariesDescription "Stavningskontrollens ordböcker som kan laddas ned och installeras."

#${LangFileString} PathName 'Sökväg till filen $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Filen $\"xxx.exe$\" finns inte i den angivna sökvägen.'

#${LangFileString} DictionariesFailed 'Nedladdning av ordbok för språk $\"$R3$\" misslyckades.'

#${LangFileString} ConfigInfo "Följande konfigurering av OtherCAD kommer att ta en stund."

#${LangFileString} RunConfigureFailed "Kunde inte köra konfigurationsskriptet"
${LangFileString} InstallRunning "Installationsprogrammet körs redan!"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} är redan installerad!$\r$\n\
				Vill du ändå installera OtherCAD över den nuvarande versionen?"
${LangFileString} NewerInstalled "Du försöker att installera en äldre version av OtherCAD än vad du har installerad.$\r$\n\
				  Om du verkligen vill detta måste du avinstallera den befintliga OtherCAD $OldVersionNumber innan."

#${LangFileString} FinishPageMessage "Gratulerar! OtherCAD har installerats framgångsrikt.$\r$\n\
#					$\r$\n\
#					(Den första starten av OtherCAD kan ta en stund.)"
${LangFileString} FinishPageRun "Kör OtherCAD"

${LangFileString} UnNotInRegistryLabel "Kan inte hitta OtherCAD i registret.$\r$\n\
					Genvägar på skrivbordet och i startmenyn kommer inte att tas bort."
${LangFileString} UnInstallRunning "Du måste stänga OtherCAD först!"
${LangFileString} UnNotAdminLabel "Du måste ha administratörsbehörighet för att avinstallera OtherCAD!"
${LangFileString} UnReallyRemoveLabel "Är du säker på att du verkligen vill fullständigt ta bort OtherCAD och alla dess komponenter?"
${LangFileString} UnOtherCADPreferencesTitle 'OtherCAD-användarinställningar'

#${LangFileString} SecUnProgDescription "Avinstallerar xxx."
${LangFileString} SecUnPreferencesDescription 'Raderar OtherCAD-konfiguration$\r$\n\
						(katalog $\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						för dig eller för alla användare (om du är admin).'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Avinstallera OtherCAD och alla dess komponenter."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
