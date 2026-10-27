#!/bin/bash

set -e
set -x

conda_env="$(pwd | sed 's#\\#/#g')/../../../.pixi/envs/default"

copy_dir="OtherCAD_Windows"
mkdir -p ${copy_dir}/bin

# Copy Conda's Python and (U)CRT to OtherCAD/bin
cp -a ${conda_env}/DLLs ${copy_dir}/bin/DLLs
cp -a ${conda_env}/Lib ${copy_dir}/bin/Lib
cp -a ${conda_env}/Scripts ${copy_dir}/bin/Scripts
cp -a ${conda_env}/python*.* ${copy_dir}/bin
cp -a ${conda_env}/msvc*.* ${copy_dir}/bin
cp -a ${conda_env}/ucrt*.* ${copy_dir}/bin
# Copy meaningful executables
cp -a ${conda_env}/Library/bin/ccx.exe ${copy_dir}/bin
cp -a ${conda_env}/Library/bin/gmsh.exe ${copy_dir}/bin
cp -a ${conda_env}/Library/bin/dot.exe ${copy_dir}/bin
cp -a ${conda_env}/Library/bin/unflatten.exe ${copy_dir}/bin
cp -a ${conda_env}/Library/mingw-w64/bin/* ${copy_dir}/bin
# copy resources -- perhaps needs reduction
cp -a ${conda_env}/Library/share ${copy_dir}/share
# get all the dependency .dlls
cp -a ${conda_env}/Library/bin/*.dll ${copy_dir}/bin
# Copy OtherCAD build. The conda package lowercases the executables (othercad.exe, othercadcmd.exe), a local
# `pixi run install-release` leaves them as OtherCAD.exe and OtherCADCmd.exe, and the Python module keeps the
# FreeCAD name (FreeCAD.pyd); globs are case-sensitive here, so match all of them.
cp -a ${conda_env}/Library/bin/[Oo]ther[Cc][Aa][Dd]* ${copy_dir}/bin
cp -a ${conda_env}/Library/bin/FreeCAD* ${copy_dir}/bin
cp -a ${conda_env}/Library/data ${copy_dir}/data
cp -a ${conda_env}/Library/Ext ${copy_dir}/Ext
cp -a ${conda_env}/Library/lib ${copy_dir}/lib
cp -a ${conda_env}/Library/Mod ${copy_dir}/Mod
mkdir -p ${copy_dir}/doc
cp -a ${conda_env}/Library/doc/{ThirdPartyLibraries.html,LICENSE.html} ${copy_dir}/doc

# delete unnecessary stuff
find ${copy_dir} -name \*.a -delete
find ${copy_dir} -name \*.lib -delete
find ${copy_dir} -name \*arm\*.exe -delete # arm binaries that fail to extract unless using latest 7zip

rm -rf ${copy_dir}/bin/Lib/site-packages/conda
rm -rf ${copy_dir}/bin/Lib/site-packages/pandas/tests
rm -rf ${copy_dir}/bin/Lib/site-packages/pre_commit
rm -rf ${copy_dir}/bin/Lib/site-packages/pycparser
rm -rf ${copy_dir}/bin/Lib/site-packages/pyright*
rm -rf ${copy_dir}/bin/libclang-*.dll
rm -rf ${copy_dir}/lib/cmake
rm -rf ${copy_dir}/lib/objects-Release
rm -rf ${copy_dir}/lib/qt6/bin
rm -rf ${copy_dir}/share/cmake
rm -rf ${copy_dir}/share/cmake-*
rm -rf ${copy_dir}/share/man

# Apply Patches
mv ${copy_dir}/bin/Lib/ssl.py .ssl-orig.py
cp ssl-patch.py ${copy_dir}/bin/Lib/ssl.py

# Turn off the echo before we start actually calling "echo"
set +x

echo '[Paths]' >> ${copy_dir}/bin/qt6.conf
echo 'Prefix = ../lib/qt6' >> ${copy_dir}/bin/qt6.conf

# convenient shortcuts to run the binaries
if [ -x /c/ProgramData/chocolatey/tools/shimgen.exe ]; then
    pushd ${copy_dir}
    /c/ProgramData/chocolatey/tools/shimgen.exe -p bin/othercadcmd.exe -i "$(pwd)/../../../WindowsInstaller/icons/OtherCAD.ico" -o "$(pwd)/OtherCADCmd.exe"
    /c/ProgramData/chocolatey/tools/shimgen.exe --gui -p bin/othercad.exe -i "$(pwd)/../../../WindowsInstaller/icons/OtherCAD.ico" -o "$(pwd)/OtherCAD.exe"
    popd
fi

version_name="OtherCAD_${BUILD_TAG}-Windows-$(uname -m)"

echo -e "################"
echo -e "version_name:  ${version_name}"
echo -e "################"

pixi list -e default > ${copy_dir}/packages.txt
sed -i '1s/.*/\nLIST OF PACKAGES:/' ${copy_dir}/packages.txt

mv ${copy_dir} ${version_name}


# Sign the EXE, DLL, and PYD files (if we can access the Azure account for signing):
set -euo pipefail
SIGN_DIR="${version_name}"


if [[ "${WINDOWS_SIGN_RELEASE:-0}" == "1" ]]; then
  TENANT="$(az account show --query tenantId -o tsv)"
  export AZURE_IDENTITY_DISABLE_WORKLOAD_IDENTITY=true
  export AZURE_IDENTITY_DISABLE_MANAGED_IDENTITY=true
  unset AZURE_IDENTITY_LOGGING_ENABLED

  if az account get-access-token \
       --tenant "$TENANT" \
       --scope "https://codesigning.azure.net/.default" \
       >/dev/null 2>&1;
  then
    echo "Azure Artifact Signing access confirmed. Beginning signing process..."

    shopt -s nullglob

    # Smart App Control evaluates every binary as it is loaded, not just the launcher, so a single
    # unsigned DLL or .pyd anywhere in the tree is refused and the user gets "Smart App Control has
    # blocked part of this app". Globbing bin/ alone left about 60% of the bundle unsigned: the Qt
    # plugins under lib/qt6 (qt6.conf sets Prefix there, so the platform plugin loads at startup),
    # the Python extension modules in bin/DLLs and bin/Lib/site-packages, and the shims in
    # bin/Scripts. Walk the whole bundle instead.
    mapfile -t FILES < <(find "$SIGN_DIR" -type f \( -name '*.exe' -o -name '*.dll' -o -name '*.pyd' \) | sort)

    total=${#FILES[@]}
    if [[ "$total" -eq 0 ]]; then
      echo "No signable files found under ${SIGN_DIR} -- refusing to ship an unsigned bundle."
      exit 1
    fi

    # "sign" takes file(s) with arity OneOrMore, so hand it batches: one process per file would be
    # ~1700 sequential Azure round trips for a full bundle.
    BATCH_SIZE=100
    echo "Signing $total files in batches of ${BATCH_SIZE}"
    for ((i = 0; i < total; i += BATCH_SIZE)); do
      batch=("${FILES[@]:i:BATCH_SIZE}")
      echo "Signing [$((i + 1))-$((i + ${#batch[@]}))/$total]"
      sign code artifact-signing \
        --artifact-signing-endpoint "${WINDOWS_AZURE_ENDPOINT}" \
        --artifact-signing-certificate-profile "${WINDOWS_AZURE_CERTIFICATE_PROFILE}" \
        --artifact-signing-account "${WINDOWS_AZURE_SIGNING_ACCOUNT}" \
        --timestamp-url https://timestamp.acs.microsoft.com \
        --timestamp-digest sha256 \
        --max-concurrency 8 \
        "${batch[@]}" >/dev/null 2>&1

      # Output was redirected to /dev/null because Azure authentication is absurdly noisy, with constant misleading
      # "failure" messages about Managed Identity authentication failing. We don't use, or want to use, that
      # authentication, and the fact that it fails is not a problem as long as the real authentication succeeds.
    done

    # Manually check the important one!
    signtool verify -pa "$SIGN_DIR/bin/OtherCAD.exe"

    # ...and a nested one, which is what proves the walk reached the plugins and extension modules
    # that Smart App Control blocks. Verifying only the launcher is how the gap went unnoticed.
    mapfile -t NESTED < <(find "$SIGN_DIR/lib" "$SIGN_DIR/bin/Lib" "$SIGN_DIR/bin/DLLs" -type f \( -name '*.dll' -o -name '*.pyd' \) 2>/dev/null | sort)
    if [[ ${#NESTED[@]} -eq 0 ]]; then
      echo "Expected nested binaries under lib/ or bin/ -- has the bundle layout changed?"
      exit 1
    fi
    signtool verify -pa "${NESTED[0]}"

    echo "Signing completed."
  else
    echo "Signing requested, but no Azure Artifact Signing available -- skipping signing."
  fi
else
  echo "Not logged into Azure -- skipping signing."
fi

echo "Running OtherCAD command-line smoke test..."
if ! "$SIGN_DIR/bin/othercadcmd.exe" --safe-mode --version; then
  echo "OtherCAD command-line smoke test failed; the Windows bundle cannot start."
  exit 1
fi

echo "Running OtherCAD bundled Pivy smoke test..."
if ! "$SIGN_DIR/bin/othercadcmd.exe" --safe-mode --console "import pivy; from pivy import coin; print(pivy.__file__); print(coin.SoDB.getVersion())"; then
  echo "OtherCAD bundled Pivy smoke test failed; the Windows bundle cannot import the bundled Coin/Pivy runtime."
  exit 1
fi

7z a -t7z -mx9 -mmt=${NUMBER_OF_PROCESSORS} ${version_name}.7z ${version_name} -bb
# create hash
sha256sum ${version_name}.7z > ${version_name}.7z-SHA256.txt

if [ "${MAKE_INSTALLER}" == "true" ]; then
    FILES_OTHERCAD="$(cygpath -w $(pwd))\\${version_name}"
    nsis_cmd="${CONDA_PREFIX}/NSIS/makensis.exe"
    "${nsis_cmd}" -V4 \
        -D"ExeFile=${version_name}-installer.exe" \
        -D"FILES_OTHERCAD=${FILES_OTHERCAD}" \
        -X'SetCompressor /FINAL lzma' \
        ../../WindowsInstaller/OtherCAD-installer.nsi
    mv ../../WindowsInstaller/${version_name}-installer.exe .
    echo "Created installer ${version_name}-installer.exe"
    # See if we can sign the installer exe as well:
    if [[ "${WINDOWS_SIGN_RELEASE:-0}" == "1" ]] && \
       az account get-access-token \
           --tenant "$TENANT" \
           --scope "https://codesigning.azure.net/.default" \
           >/dev/null 2>&1;
    then
      echo "Signing the installer..."
      sign code artifact-signing \
          --artifact-signing-endpoint "${WINDOWS_AZURE_ENDPOINT}" \
          --artifact-signing-certificate-profile "${WINDOWS_AZURE_CERTIFICATE_PROFILE}" \
          --artifact-signing-account "${WINDOWS_AZURE_SIGNING_ACCOUNT}" \
          --timestamp-url https://timestamp.acs.microsoft.com \
          --timestamp-digest sha256 \
          ${version_name}-installer.exe >/dev/null 2>&1 \
          || { echo "Signing the installer failed!"; exit 1; }
    else
      echo "No code signing available, leaving the installer unsigned"
    fi
    sha256sum ${version_name}-installer.exe > ${version_name}-installer.exe-SHA256.txt
fi

if [ "${UPLOAD_RELEASE}" == "true" ]; then
    echo "Uploading the release..."
    gh release upload --clobber ${BUILD_TAG} "${version_name}.7z" "${version_name}.7z-SHA256.txt"
    if [ "${MAKE_INSTALLER}" == "true" ]; then
        gh release upload --clobber ${BUILD_TAG} "${version_name}-installer.exe" "${version_name}-installer.exe-SHA256.txt"
    fi
    echo "Done uploading"
fi
