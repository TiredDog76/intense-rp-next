[CmdletBinding()]
param(
  [string]$AppName = "intenserp-next-v2",
  [string]$PackageName = "intenserp-next-v2-win32-x64",
  [string]$PackageAppDirName = "intense-rp-next",
  [string]$PackageOptionalDirName = "optional"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$EntryPoint = Join-Path $RepoRoot "main.py"
$UpdaterEntryPoint = Join-Path $RepoRoot "updater/main.py"
$IconPath = Join-Path $RepoRoot "ui/assets/brand/newlogo.ico"
$VersionPath = Join-Path $RepoRoot "version.json"
$NuitkaConfigPath = Join-Path $RepoRoot "scripts/nuitka-package.config.yml"

if (!(Test-Path $EntryPoint)) { throw "Entry point not found: $EntryPoint" }
if (!(Test-Path $UpdaterEntryPoint)) { throw "Updater entry point not found: $UpdaterEntryPoint" }
if (!(Test-Path $IconPath)) { throw "Icon not found: $IconPath" }
if (!(Test-Path $VersionPath)) { throw "version.json not found: $VersionPath" }
if (!(Test-Path $NuitkaConfigPath)) { throw "Nuitka package config not found: $NuitkaConfigPath" }

$BuildDir = Join-Path $RepoRoot "build"
$DistDir = Join-Path $RepoRoot "dist"
$SpecPath = Join-Path $RepoRoot "$AppName.spec"

foreach ($path in @($BuildDir, $DistDir, $SpecPath)) {
  if (Test-Path $path) {
    Remove-Item -Recurse -Force $path
  }
}

New-Item -ItemType Directory -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Path $DistDir | Out-Null

$commonNuitkaArgs = @(
  "--assume-yes-for-downloads",
  "--deployment",
  "--user-package-configuration-file=$NuitkaConfigPath",
  "--enable-plugin=pyside6",
  "--include-package=patchright",
  "--include-package=playwright",
  "--include-package=desktop_notifier",
  "--include-package-data=desktop_notifier",
  "--include-data-files=$VersionPath=version.json",
  "--include-data-dir=$(Join-Path $RepoRoot '.github/state')=.github/state",
  "--include-data-dir=$(Join-Path $RepoRoot 'remote_control/assets')=remote_control/assets",
  "--include-data-dir=$(Join-Path $RepoRoot 'remote_control/templates')=remote_control/templates",
  "--include-data-dir=$(Join-Path $RepoRoot 'ui/assets')=ui/assets",
  "--include-data-dir=$(Join-Path $RepoRoot 'ui/fonts')=ui/fonts"
)

Write-Output "Nuitka version:"
python -m nuitka --version

Write-Output "Building main application with Nuitka..."
$mainArgs = @(
  "--mode=standalone",
  "--msvc=latest",
  "--windows-console-mode=disable",
  "--windows-icon-from-ico=$IconPath",
  "--output-dir=$DistDir",
  "--output-folder-name=$AppName",
  "--output-filename=$AppName.exe"
) + $commonNuitkaArgs + @(
  $EntryPoint
)

python -m nuitka @mainArgs

$BuiltAppDir = Join-Path $DistDir "$AppName.dist"
if (!(Test-Path $BuiltAppDir)) { throw "Nuitka output folder not found: $BuiltAppDir" }

# version.json must be present at the package root (convenience copy; runtime uses bundled data).
Copy-Item -Force $VersionPath (Join-Path $BuiltAppDir "version.json")

# Existing 2.8.0 auto-updaters only accept package roots with _internal present.
$InternalCompatDir = Join-Path $BuiltAppDir "_internal"
New-Item -ItemType Directory -Force -Path $InternalCompatDir | Out-Null
Set-Content -Path (Join-Path $InternalCompatDir ".nuitka-standalone") -Value "compatibility marker" -Encoding UTF8

Write-Output "Building updater with Nuitka..."
$updaterOutputDir = Join-Path $BuildDir "nuitka-updater"
New-Item -ItemType Directory -Force -Path $updaterOutputDir | Out-Null

$updaterArgs = @(
  "--mode=onefile",
  "--msvc=latest",
  "--windows-console-mode=disable",
  "--windows-icon-from-ico=$IconPath",
  "--output-dir=$updaterOutputDir",
  "--output-filename=updater.exe",
  "--assume-yes-for-downloads",
  "--deployment",
  "--enable-plugin=pyside6",
  $UpdaterEntryPoint
)

python -m nuitka @updaterArgs

$UpdaterExe = Join-Path $updaterOutputDir "updater.exe"
if (!(Test-Path $UpdaterExe)) { throw "Updater output not found: $UpdaterExe" }

# Make sure logs/configs are not shipped (even if present locally).
foreach ($root in @($BuiltAppDir, (Join-Path $BuiltAppDir "_internal"))) {
  if (!(Test-Path $root)) { continue }
  foreach ($forbiddenDir in @("logs", "config_data")) {
    $p = Join-Path $root $forbiddenDir
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
  }
  foreach ($forbiddenFile in @("config_dir.txt", ".env")) {
    $p = Join-Path $root $forbiddenFile
    if (Test-Path $p) { Remove-Item -Force $p }
  }
}

$StagingDir = Join-Path $DistDir $PackageName
if (Test-Path $StagingDir) { Remove-Item -Recurse -Force $StagingDir }
New-Item -ItemType Directory -Path $StagingDir | Out-Null

$MainStage = Join-Path $StagingDir $PackageAppDirName
$OptionalStage = Join-Path $StagingDir $PackageOptionalDirName
New-Item -ItemType Directory -Path $MainStage | Out-Null
New-Item -ItemType Directory -Path $OptionalStage | Out-Null

Copy-Item -Recurse -Force (Join-Path $BuiltAppDir "*") $MainStage
Copy-Item -Force $UpdaterExe (Join-Path $OptionalStage "updater.exe")

$ZipPath = Join-Path $DistDir "$PackageName.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Compress-Archive -Path (Join-Path $StagingDir "*") -DestinationPath $ZipPath -Force

Write-Output "Created release asset: $ZipPath"
