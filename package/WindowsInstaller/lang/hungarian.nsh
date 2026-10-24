/*
OtherCAD Installer Language File
Language: Hungarian
*/

!insertmacro LANGFILE_EXT "Hungarian"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Telepítve az aktuális felhasználónak)"

${LangFileString} TEXT_WELCOME "A varázsló segítségével tudja telepíteni a OtherCAD-et.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Python parancsfájlok fordítása..."

${LangFileString} TEXT_FINISH_DESKTOP "Indítóikon létrehozása Asztalon"
${LangFileString} TEXT_FINISH_WEBSITE "Látogasson el a github.com/otherworld-dev/OtherCAD oldalra az aktuális hírekért, támogatásért és tippekért"

#${LangFileString} FileTypeTitle "OtherCAD-dokumentum"

#${LangFileString} SecAllUsersTitle "Telepítés minden felhasználónak"
${LangFileString} SecFileAssocTitle "Fájltársítások"
${LangFileString} SecDesktopTitle "Parancsikon Asztalra"

${LangFileString} SecCoreDescription "A OtherCAD futtatásához szükséges fájlok."
#${LangFileString} SecAllUsersDescription "Minden felhasználónak telepítsem vagy csak az aktuálisnak?"
${LangFileString} SecFileAssocDescription "A .FCStd kiterjesztéssel rendelkező fájlok megnyitása automatikusan a OtherCAD-el történjen."
${LangFileString} SecDesktopDescription "OtherCAD-ikon elhelyezése az Asztalon."
#${LangFileString} SecDictionaries "Szótárak"
#${LangFileString} SecDictionariesDescription "Helyesírás-ellenőrző szótárak, amiket letölthet és telepíthet."

#${LangFileString} PathName 'A $\"xxx.exe$\" fájl elérési útja'
#${LangFileString} InvalidFolder 'Nem találom a $\"xxx.exe$\" fájlt, a megadott helyen.'

#${LangFileString} DictionariesFailed 'Szótár letöltése a(z) $\"$R3$\" nyelvhez sikertelen.'

#${LangFileString} ConfigInfo "A OtherCAD telepítés utáni beállítása hosszú időt vehet igénybe."

#${LangFileString} RunConfigureFailed "Nem tudom végrehajtani a configure parancsfájlt!"
${LangFileString} InstallRunning "A telepítő már fut!"
${LangFileString} AlreadyInstalled "A OtherCAD ${APP_SERIES_KEY2} már teleptve van!$\r$\n\
				Dou you nevertheles want to install OtherCAD over the existing version?"
${LangFileString} NewerInstalled "A jelenleg telepítettnél régebbi OtherCAD verziót próbál telepíteni.$\r$\n\
				  Ha valóban ezt akarja, először el kell távolítania a meglévő OtherCAD $OldVersionNumber változatot."

#${LangFileString} FinishPageMessage "Gratulálok! Sikeresen telepítette a OtherCAD-et.$\r$\n\
#					$\r$\n\
#					(A program első indítása egy kis időt vehet igénybe...)"
${LangFileString} FinishPageRun "OtherCAD indítása"

${LangFileString} UnNotInRegistryLabel "Nem találom a OtherCAD-et a regisztriben.$\r$\n\
					Az Asztalon és a Start Menüben található parancsikonok nem lesznek eltávolítva!."
${LangFileString} UnInstallRunning "Először be kell zárnia a OtherCAD-et!"
${LangFileString} UnNotAdminLabel "A OtherCAD eltávolításhoz rendszergazdai jogokkal kell rendelkeznie!"
${LangFileString} UnReallyRemoveLabel "Biztosan abban, hogy el akarja távolítani a OtherCAD-t, minden tartozékával együtt?"
${LangFileString} UnOtherCADPreferencesTitle 'OtherCAD felhasználói beállítások'

#${LangFileString} SecUnProgDescription "xxx eltávolítása."
${LangFileString} SecUnPreferencesDescription 'A  OtherCAD beállítások mappa törlése$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						minden felhasználónál.'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "A OtherCAD és minden komponensének eltávolítása."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
