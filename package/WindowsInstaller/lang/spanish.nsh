/*
OtherCAD Installer Language File
Language: Spanish
*/

!insertmacro LANGFILE_EXT "Spanish"

${LangFileString} TEXT_INSTALL_CURRENTUSER "(Instalado para el actual usuario)"

${LangFileString} TEXT_WELCOME "Este programa instalará OtherCAD en su ordenador.$\r$\n\
				$\r$\n\
				$_CLICK"

#${LangFileString} TEXT_CONFIGURE_PYTHON "Compilando guiones Python..."

${LangFileString} TEXT_FINISH_DESKTOP "Crear acceso directo en el escritorio"
${LangFileString} TEXT_FINISH_WEBSITE "Visite github.com/otherworld-dev/OtherCAD para últimas noticias, ayuda y consejos"

#${LangFileString} FileTypeTitle "Documento OtherCAD"

#${LangFileString} SecAllUsersTitle "Instalar para todos los usuarios"
${LangFileString} SecFileAssocTitle "Asociar ficheros"
${LangFileString} SecDesktopTitle "Icono de escritorio"

${LangFileString} SecCoreDescription "Los ficheros de OtherCAD."
#${LangFileString} SecAllUsersDescription "Instalar OtherCAD para todos los usuarios o sólo para el usuario actual."
${LangFileString} SecFileAssocDescription "Asociar la extensión .FCStd con OtherCAD."
${LangFileString} SecDesktopDescription "Crear un icono de OtherCAD en el escritorio."
#${LangFileString} SecDictionaries "Diccionarios"
#${LangFileString} SecDictionariesDescription "Diccionarios de revisión ortográfica que se pueden descargar e instalar."

#${LangFileString} PathName 'Ruta al fichero $\"xxx.exe$\"'
#${LangFileString} InvalidFolder 'Imposible encontrar $\"xxx.exe$\".'

#${LangFileString} DictionariesFailed 'La descarga del diccionario para el idioma $\"$R3$\" ha fallado.'

#${LangFileString} ConfigInfo "La siguiente configuración de OtherCAD va a tardar un poco."

#${LangFileString} RunConfigureFailed "Error al intentar ejecutar el programa de configuración"
${LangFileString} InstallRunning "El instalador ya está siendo ejecutado!"
${LangFileString} AlreadyInstalled "¡OtherCAD ${APP_SERIES_KEY2} ya está instalado!$\r$\n\
				Aún así, ¿quiere instalar OtherCAD sobre la versión existente?"
${LangFileString} NewerInstalled "Está tratando de instalar una versión de OtherCAD más antigua que la que tiene instalada.$\r$\n\
				  Si realmente lo desea, debe desinstalar antes la versión de OtherCAD instalada $OldVersionNumber."

#${LangFileString} FinishPageMessage "¡Enhorabuena! OtherCAD ha sido instalado con éxito.$\r$\n\
#					$\r$\n\
#					(El primer arranque de OtherCAD puede tardar algunos segundos.)"
${LangFileString} FinishPageRun "Ejecutar OtherCAD"

${LangFileString} UnNotInRegistryLabel "Imposible encontrar OtherCAD en el registro.$\r$\n\
					Los accesos rápidos del escritorio y del Menú de Inicio no serán eliminados."
${LangFileString} UnInstallRunning "Antes cierre OtherCAD!"
${LangFileString} UnNotAdminLabel "Necesita privilegios de administrador para desinstalar OtherCAD!"
${LangFileString} UnReallyRemoveLabel "¿Está seguro de que desea eliminar completamente OtherCAD y todos sus componentes?"
${LangFileString} UnOtherCADPreferencesTitle 'Preferencias de usuario de OtherCAD'

#${LangFileString} SecUnProgDescription "Desinstala xxx."
${LangFileString} SecUnPreferencesDescription 'Elimina las carpetas de configuración de OtherCAD$\r$\n\
						$\"$AppPre\username\$\r$\n\
						$AppSuff\$\r$\n\
						${APP_DIR_USERDATA}$\")$\r$\n\
						de todos los usuarios.'
${LangFileString} DialogUnPreferences 'Eligió eliminar la configuración de usuario de OtherCAD.$\r$\n\
						Esto también eliminará todos los addons de OtherCAD instalados.$\r$\n\
						¿Está de acuerdo con esto?'
${LangFileString} SecUnProgramFilesDescription "Desinstala OtherCAD y todos sus componentes."

${LangFileString} DirNotEmptyWarning "La carpeta seleccionada '$INSTDIR' no está vacia.$\r$\n\
                        El instalador eliminará todo su contenido antes de instalar. ¿Continuar?"
${LangFileString} RMInstDirFailed "No se ha podido eliminar '$INSTDIR'.$\r$\n\
                        Asegúrese de tener suficientes permisos y que ningún archivo esté en use."
