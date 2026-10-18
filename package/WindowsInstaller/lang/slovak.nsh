/*
OtherCAD Installer Language File
Language: Slovak
*/

!insertmacro LANGFILE_EXT "Slovak"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Inštalované pre súčasného užívateľa)"

${LangFileString} TEXT_WELCOME "Tento sprievodca Vám pomáha inštalovať OtherCAD.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Kompilácia Python skriptov..."

${LangFileString} TEXT_FINISH_DESKTOP "Vytvoriť skratku pre pracovnú plochu"
${LangFileString} TEXT_FINISH_WEBSITE "Navštívte github.com/otherworld-dev/OtherCAD pre posledné novinky, podporu a tipy"

#${LangFileString} FileTypeTitle "OtherCAD dokument"

#${LangFileString} SecAllUsersTitle "Inštalovať pre všetkých užívateľov?"
${LangFileString} SecFileAssocTitle "Asociácie súborov"
${LangFileString} SecDesktopTitle "Ikona pracovnej plochy"

${LangFileString} SecCoreDescription "Súbory OtherCADu."
#${LangFileString} SecAllUsersDescription "Inštalovať OtherCAD pre všetkých užívateľov alebo len pre súčasného užívateľa."
${LangFileString} SecFileAssocDescription "Súbory s rozšírením .FCStd sa automaticky otvárajú v OtherCADe."
${LangFileString} SecDesktopDescription "Ikona OtherCADa na pracovnej ploche."
#${LangFileString} SecDictionaries "Slovníky"
#${LangFileString} SecDictionariesDescription "Slovníky pre kontrolu pravopisu ktoré možno načítať a inštalovať."

#${LangFileString} PathName 'Cesta na súbor $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Súbor $\"xxx.exe$\" nie je na špecifikovanej ceste.'

#${LangFileString} DictionariesFailed 'Načítanie slovníka pre jazyk $\"$R3$\" zlyhalo.'

#${LangFileString} ConfigInfo "Nasledujúca konfigurácia OtherCADu trochu potrvá."

#${LangFileString} RunConfigureFailed "Nedal sa spustiť konfiguračný skript"
${LangFileString} InstallRunning "Inštalačný program už beží!"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} je už inštalovaný!$\r$\n\
				Napriek tomu chcete inštalovať OtherCAD ponad existujúcu verziu?"
${LangFileString} NewerInstalled "Pokúšate sa inštalovať verziu OtherCADu ktorá je staršia ako tá ktorá je inštalovaná.$\r$\n\
				  Keď to naozaj chcete, odinštalujte najprv existujúci OtherCAD $OldVersionNumber."

#${LangFileString} FinishPageMessage "Gratulácia! OtherCAD bol úspešne inštalovaný.$\r$\n\
#					$\r$\n\
#					(Prvý OtherCAD štart môže trvať niekoľko sekúnd.)"
${LangFileString} FinishPageRun "Spustiť OtherCAD"

${LangFileString} UnNotInRegistryLabel "Nemôžem nájsť OtherCAD v registre.$\r$\n\
					Skratky na pracovnej ploche a v štartovacom Menu sa nedajú odstrániť."
${LangFileString} UnInstallRunning "Najprv treba zavrieť OtherCAD!"
${LangFileString} UnNotAdminLabel "Pre odinštaláciu OtherCAD potrebujete administrátorské práva!"
${LangFileString} UnReallyRemoveLabel "Ste si istý, že chcete kompletne odinštalovať OtherCAD a všetky jeho súčiastky?"
${LangFileString} UnOtherCADPreferencesTitle 'OtherCADove užívateľské nastavenia'

#${LangFileString} SecUnProgDescription "Odinštaluje xxx."
${LangFileString} SecUnPreferencesDescription 'Odstráni konfiguračný adresár OtherCADu $\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						pre všetkých užívateľov (keď máte administrátorské práva).'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Odinštaluj OtherCAD a všetky jeho súčiastky."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
