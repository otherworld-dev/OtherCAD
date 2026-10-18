/*
OtherCAD Installer Language File
Language: French
*/

!insertmacro LANGFILE_EXT "French"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Installation pour l'utilisateur courant)"

${LangFileString} TEXT_WELCOME "Cet assistant va vous guider tout au long de l'installation de $(^NameDA).$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compilation des scripts Python..."

${LangFileString} TEXT_FINISH_DESKTOP "Créer un raccourci sur le bureau"
${LangFileString} TEXT_FINISH_WEBSITE "Consulter les dernières nouvelles, trucs et astuces sur le site github.com/otherworld-dev/OtherCAD"

#${LangFileString} FileTypeTitle "Document OtherCAD"

#${LangFileString} SecAllUsersTitle "Installer pour tous les utilisateurs ?"
${LangFileString} SecFileAssocTitle "Associations de fichiers"
${LangFileString} SecDesktopTitle "Icône du bureau"

${LangFileString} SecCoreDescription "Les fichiers OtherCAD"
#${LangFileString} SecAllUsersDescription "Installer OtherCAD pour tous les utilisateurs, ou seulement pour l$\'utilisateur courant ?"
${LangFileString} SecFileAssocDescription "Les fichiers de suffixe .FCStd seront automatiquement ouverts dans OtherCAD."
${LangFileString} SecDesktopDescription "Une icône OtherCAD sur le bureau."
#${LangFileString} SecDictionaries "Dictionnaires"
#${LangFileString} SecDictionariesDescription "Les dictionnaires pour correcteur orthographique qui peuvent être téléchargés et installés."

#${LangFileString} PathName 'Chemin vers le fichier $\"xxx.exe$\"'
#${LangFileString} InvalidFolder '$\"xxx.exe$\" introuvable dans le chemin d$\'accès spécifié.'

#${LangFileString} DictionariesFailed 'Le chargement du dictionnaire pour la langue $\"$R3$\" a échoué.'

#${LangFileString} ConfigInfo "La configuration de OtherCAD qui va suivre prendra un moment."

#${LangFileString} RunConfigureFailed "Échec de la tentative de configuration initiale de OtherCAD."
${LangFileString} InstallRunning "Le programme d$\'installation est toujours en cours !"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} est déjà installé !$\r$\n\
				Voulez-vous néanmoins installer OtherCAD par dessus la version existante ?"
${LangFileString} NewerInstalled "Vous essayez d$\'installer une version de OtherCAD plus ancienne que celle qui est déjà installée.$\r$\n\
				  Si c$\'est ce qu vous voulez, vous devez d$\'abord désinstaller OtherCAD $OldVersionNumber."

#${LangFileString} FinishPageMessage "Félicitations ! OtherCAD est installé avec succès.$\r$\n\
#					$\r$\n\
#					(Le premier démarrage de OtherCAD peut demander quelques secondes.)"
${LangFileString} FinishPageRun "Démarrer OtherCAD"

${LangFileString} UnNotInRegistryLabel "OtherCAD introuvable dans la base des registres.$\r$\n\
					Les raccourcis sur le bureau et dans le menu de démarrage ne seront pas supprimés."
${LangFileString} UnInstallRunning "Vous devez fermer OtherCAD d$\'abord !"
${LangFileString} UnNotAdminLabel "Vous devez avoir les droits d$\'administration pour désinstaller OtherCAD !"
${LangFileString} UnReallyRemoveLabel "Êtes vous sûr(e) de vouloir supprimer complètement OtherCAD et tous ses composants ?"
${LangFileString} UnOtherCADPreferencesTitle 'Préférences utilisateurs de OtherCAD'

#${LangFileString} SecUnProgDescription "Désinstalle le gestionnaire de bibliographie xxx."
${LangFileString} SecUnPreferencesDescription 'Supprime le répertoire de configuration de OtherCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						pour tous les utilisateurs.'
${LangFileString} DialogUnPreferences 'Vous avez choisi de supprimer le répertoire de configuration de OtherCADs.$\r$\n\
						Cela supprimera également tous les addons OtherCAD installés.$\r$\n\
						Êtes-vous d$\'accord avec cela ?'
${LangFileString} SecUnProgramFilesDescription "Désinstaller OtherCAD et tous ses composants."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
