# Windows bundle: code signing

`create_bundle.sh` assembles the Windows bundle from the conda environment, signs it, and builds the
NSIS installer. Signing is optional — the script and both release workflows degrade to an unsigned
bundle when credentials are absent — but an unsigned bundle is blocked on modern Windows.

## Why signing is not optional in practice

Windows 11's **Smart App Control** (SAC) only runs code that is either signed by a publisher it
trusts or already carries reputation with Microsoft's cloud. It evaluates **every binary as it is
loaded**, not just the launcher, and there is no "run anyway" prompt — the user's only lever is
turning SAC off, which cannot be undone without reinstalling Windows.

The practical symptom of a partly-signed bundle is:

> Smart App Control has blocked part of this app

The app starts, because the launcher passes, and then individual DLL and `.pyd` loads are refused, so
workbenches and features fail — often silently.

This is why the signing step walks the **whole** bundle. Signing only `*.exe`, `bin/*.exe`,
`bin/*.dll` and `bin/*.pyd` leaves roughly 60% of the tree unsigned: the Qt plugins under `lib/qt6`
(`qt6.conf` sets `Prefix = ../lib/qt6`, so the platform plugin loads at startup), the Python
extension modules in `bin/DLLs` and `bin/Lib/site-packages`, and the console shims in `bin/Scripts`.

## Required GitHub configuration

Signing uses [Azure Trusted Signing](https://learn.microsoft.com/azure/trusted-signing/) via the
[`dotnet/sign`](https://github.com/dotnet/sign) CLI. Set these on the repository (or its
environment/organisation) under **Settings → Secrets and variables → Actions**.

### Secrets

| Secret | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | Service principal used by `azure/login`. **Also the on/off switch** — see below. |
| `AZURE_CLIENT_SECRET` | Service principal secret. |
| `AZURE_SUBSCRIPTION_ID` | Subscription holding the Trusted Signing account. |
| `AZURE_TENANT_ID` | Entra tenant of the service principal. |

### Variables

| Variable | Purpose |
| --- | --- |
| `AZURE_TRUSTED_SIGNING_ENDPOINT` | Regional endpoint, e.g. `https://eus.codesigning.azure.net` |
| `AZURE_TRUSTED_SIGNING_ACCOUNT` | Trusted Signing account name. |
| `AZURE_TRUSTED_SIGNING_CERTIFICATE_PROFILE` | Certificate profile within that account. |

The service principal needs the **Trusted Signing Certificate Profile Signer** role on the account.

## How the gate works

Both `build_release.yml` and `sub_releaseWindowsLibpack.yml` compute:

```yaml
HAS_WINDOWS_SIGNING: ${{ secrets.AZURE_CLIENT_ID != '' }}
```

When that is false the .NET SDK, the `sign` tool install, and the Azure login are all skipped, the
workflow exports `WINDOWS_SIGN_RELEASE=0`, and `create_bundle.sh` reports:

```
Not logged into Azure -- skipping signing.
No code signing available, leaving the installer unsigned
```

**A fork with no secrets configured therefore publishes a completely unsigned installer**, which SAC
will block. This is deliberate — forks build without failing on missing credentials — but it means a
successful release run is *not* evidence that anything was signed. Check the log for the lines above.

## Verifying a signed bundle

The script verifies two files after signing: the launcher, and a nested binary from `lib/` or
`bin/Lib`. The nested check is the meaningful one — verifying only the launcher is how the unsigned
remainder went unnoticed. To audit a built bundle by hand:

```powershell
$root = 'C:\Program Files\OtherCAD'
Get-ChildItem $root -Recurse -Include *.dll,*.pyd,*.exe -File |
  ForEach-Object { Get-AuthenticodeSignature $_.FullName } |
  Group-Object Status
```

Every file should report `Valid`. Any `NotSigned` result is a file SAC can block.

If a machine has already hit the block, the offending file is named in Event Viewer under
**Applications and Services Logs → Microsoft → Windows → CodeIntegrity → Operational**.

## Note on signing volume

Walking the whole bundle raises the count from roughly 650 files to roughly 1700 per release. The
files are submitted to `sign` in batches of 100 with `--max-concurrency 8` rather than one process
per file, but the per-release call volume against the Trusted Signing account still grows by about
2.5x — worth checking against the account's quota before a release train.
