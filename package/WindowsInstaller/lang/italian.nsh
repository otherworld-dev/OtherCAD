/*
OtherCAD Installer Language File
Language: Italian
*/

!insertmacro LANGFILE_EXT "Italian"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Installed for Current User)"

${LangFileString} TEXT_WELCOME "Verrete guidati nell'installazione di $(^NameDA)$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compilazione degli script Python in corso..."

${LangFileString} TEXT_FINISH_DESKTOP "Crea icona sul desktop"
${LangFileString} TEXT_FINISH_WEBSITE "Visitate github.com/otherworld-dev/OtherCAD per ultime novità, aiuto e suggerimenti"

#${LangFileString} FileTypeTitle "Documento di OtherCAD"

#${LangFileString} SecAllUsersTitle "Installare per tutti gli utenti?"
${LangFileString} SecFileAssocTitle "Associazioni dei file"
${LangFileString} SecDesktopTitle "Icona sul Desktop"

${LangFileString} SecCoreDescription "I file di OtherCAD."
#${LangFileString} SecAllUsersDescription "Installazione OtherCAD per tutti gli utenti o solo per l'utente attuale."
${LangFileString} SecFileAssocDescription "Associa i files con estensione .FCStd al programma OtherCAD."
${LangFileString} SecDesktopDescription "Icona OtherCAD sul desktop."
#${LangFileString} SecDictionaries "Dizionari"
#${LangFileString} SecDictionariesDescription "Dizionari per il controllo ortografico che possono essere scaricati e installati."

#${LangFileString} PathName 'Percorso del file $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Il file $\"xxx.exe$\" non è nel percorso indicato.'

#${LangFileString} DictionariesFailed 'Lo scaricamento del dizionario per la lingua  $\"$R3$\" non e$\' andato a buon fine.'

#${LangFileString} ConfigInfo "La seguente configurazione di OtherCAD richiederà un po' di tempo."

#${LangFileString} RunConfigureFailed "Fallito tentativo di eseguire lo script di configurazione"
${LangFileString} InstallRunning "Il programma di installazione è già in esecuzione!"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} è già installato!$\r$\n\
				Volete procedere comunque con l'installazione di OtherCAD su quella esistente?"
${LangFileString} NewerInstalled "Si sta procedendo ad installare una versione di OtherCAD precedente a quella in uso.$\r$\n\
				  Se si vuole procedere, è necessario prima disinstallare la versione OtherCAD $OldVersionNumber."

#${LangFileString} FinishPageMessage "Congratulazioni! OtherCAD è stato installato con successo.$\r$\n\
#					$\r$\n\
#					(Il primo avvio di OtherCAD potrebbe richiedere qualche secondo in più.)"
${LangFileString} FinishPageRun "Lancia OtherCAD"

${LangFileString} UnNotInRegistryLabel "Non riesco a trovare OtherCAD nel registro.$\r$\n\
					I collegamenti sul desktop e nel menu Start non saranno rimossi."
${LangFileString} UnInstallRunning "È necessario chiudere OtherCAD!"
${LangFileString} UnNotAdminLabel "Occorrono i privilegi da amministratore per rimuovere OtherCAD!"
${LangFileString} UnReallyRemoveLabel "Siete sicuri di voler rimuovere completamente OtherCAD e tutti i suoi componenti?"
${LangFileString} UnOtherCADPreferencesTitle 'Impostazioni personali di OtherCAD'

#${LangFileString} SecUnProgDescription "Rimuove xxx."
${LangFileString} SecUnPreferencesDescription 'Elimina la cartella con la configurazione di OtherCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						per tutti gli utenti.'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Rimuove OtherCAD e tutti i suoi componenti."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
