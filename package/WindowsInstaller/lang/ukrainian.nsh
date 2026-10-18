/*
OtherCAD Installer Language File
Language: Ukrainian
*/

!insertmacro LANGFILE_EXT "Ukrainian"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Встановлено для поточного користувача)"

${LangFileString} TEXT_WELCOME "За допомогою цього майстра ви зможете встановити OtherCAD у вашу систему.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Обробка скриптів Python..."

${LangFileString} TEXT_FINISH_DESKTOP "Створити значок на стільниці"
${LangFileString} TEXT_FINISH_WEBSITE "Відвідати github.com/otherworld-dev/OtherCAD, щоб ознайомитися з новинами, довідковими матеріалами та підказками"

#${LangFileString} FileTypeTitle "Документ OtherCAD"

#${LangFileString} SecAllUsersTitle "Встановити для всіх користувачів?"
${LangFileString} SecFileAssocTitle "Прив’язка файлів"
${LangFileString} SecDesktopTitle "Піктограма стільниці"

${LangFileString} SecCoreDescription "Файли OtherCAD."
#${LangFileString} SecAllUsersDescription "Визначає, чи слід встановити OtherCAD для всіх користувачів, чи лише для поточного користувача."
${LangFileString} SecFileAssocDescription "Файли з суфіксом .FCStd автоматично відкриватимуться за допомогою OtherCAD."
${LangFileString} SecDesktopDescription "Піктограма OtherCAD на стільниці."
#${LangFileString} SecDictionaries "Словники"
#${LangFileString} SecDictionariesDescription "Словники для перевірки правопису, які можна отримати і встановити."

#${LangFileString} PathName 'Розташування файла $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'У вказаній теці немає файла $\"xxx.exe$\".'

#${LangFileString} DictionariesFailed 'Спроба отримання словника для мови $\"$R3$\" зазнала невдачі.'

#${LangFileString} ConfigInfo "Налаштування OtherCAD може тривати досить довго."

#${LangFileString} RunConfigureFailed "Не вдалося виконати скрипт налаштування"
${LangFileString} InstallRunning "Засіб для встановлення вже працює!"
${LangFileString} AlreadyInstalled "OtherCAD ${APP_SERIES_KEY2} вже встановлено!$\r$\n\
				Чи хочете ви попри ці зауваження встановити OtherCAD на місце наявної версії?"
${LangFileString} NewerInstalled "Ви намагаєтеся встановити версію OtherCAD, яка є застарілою порівняно з вже встановленою.$\r$\n\
				  Якщо ви хочете встановити застарілу версію, вам слід спочатку вилучити вже встановлений OtherCAD $OldVersionNumber."

#${LangFileString} FinishPageMessage "Вітаємо! OtherCAD було успішно встановлено.$\r$\n\
#					$\r$\n\
#					(Перший запуск OtherCAD може тривати декілька секунд.)"
${LangFileString} FinishPageRun "Запустити OtherCAD"

${LangFileString} UnNotInRegistryLabel "Не вдалося знайти записи OtherCAD у регістрі.$\r$\n\
					Записи на стільниці і у меню запуску вилучено не буде."
${LangFileString} UnInstallRunning "Спочатку слід завершити роботу програми OtherCAD!"
${LangFileString} UnNotAdminLabel "Для вилучення OtherCAD вам слід мати привілеї адміністратора!"
${LangFileString} UnReallyRemoveLabel "Ви справді бажаєте повністю вилучити OtherCAD і всі його компоненти?"
${LangFileString} UnOtherCADPreferencesTitle 'Параметри OtherCAD, встановлені користувачем'

#${LangFileString} SecUnProgDescription "Вилучає xxx."
${LangFileString} SecUnPreferencesDescription 'Вилучає теку з налаштуваннями OtherCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						для всіх користувачів.'
${LangFileString} DialogUnPreferences 'You chose to delete the OtherCADs user configuration.$\r$\n\
						This will also delete all installed OtherCAD addons.$\r$\n\
						Do you agree with this?'
${LangFileString} SecUnProgramFilesDescription "Вилучити OtherCAD і всі його компоненти."

${LangFileString} DirNotEmptyWarning "The selected folder '$INSTDIR' is not empty.$\r$\n\
                        The installer will remove all its content before installing. Continue?"
${LangFileString} RMInstDirFailed "Failed to remove '$INSTDIR'.$\r$\n\
                        Make sure you have sufficient permissions and that no files are in use."
