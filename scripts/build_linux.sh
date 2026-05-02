#!/usr/bin/env bash
# Build script for Linux (equivalent to build_windows.ps1)
# NOTE FOR SELF: Release builds target Ubuntu 22.04+ (glibc 2.35+). Building on older distros may fail
# due to wheel compatibility (e.g., PySide6). Building on newer distros may produce binaries that
# won't run on Ubuntu 22.04 due to newer glibc requirements.
set -euo pipefail

APP_NAME="${APP_NAME:-intenserp-next-v2}"
PACKAGE_NAME="${PACKAGE_NAME:-intenserp-next-v2-linux-x64}"
PACKAGE_APP_DIR_NAME="${PACKAGE_APP_DIR_NAME:-intense-rp-next}"
PACKAGE_OPTIONAL_DIR_NAME="${PACKAGE_OPTIONAL_DIR_NAME:-optional}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

ENTRY_POINT="$REPO_ROOT/main.py"
UPDATER_ENTRY_POINT="$REPO_ROOT/updater/main.py"
VERSION_PATH="$REPO_ROOT/version.json"
NUITKA_CONFIG_PATH="$REPO_ROOT/scripts/nuitka-package.config.yml"

for f in "$ENTRY_POINT" "$UPDATER_ENTRY_POINT" "$VERSION_PATH" "$NUITKA_CONFIG_PATH"; do
    if [[ ! -f "$f" ]]; then
        echo "Required file not found: $f" >&2
        exit 1
    fi
done

BUILD_DIR="$REPO_ROOT/build"
DIST_DIR="$REPO_ROOT/dist"
SPEC_PATH="$REPO_ROOT/$APP_NAME.spec"

# Cleanup previous build artifacts
for path in "$BUILD_DIR" "$DIST_DIR" "$SPEC_PATH"; do
    if [[ -e "$path" ]]; then
        rm -rf "$path"
    fi
done

mkdir -p "$BUILD_DIR" "$DIST_DIR"

COMMON_NUITKA_ARGS=(
    --assume-yes-for-downloads
    --deployment
    "--user-package-configuration-file=$NUITKA_CONFIG_PATH"
    --enable-plugin=pyside6
    --include-package=patchright
    --include-package=playwright
    --include-package=desktop_notifier
    --include-package-data=desktop_notifier
    "--include-data-files=$VERSION_PATH=version.json"
    "--include-data-dir=$REPO_ROOT/.github/state=.github/state"
    "--include-data-dir=$REPO_ROOT/remote_control/assets=remote_control/assets"
    "--include-data-dir=$REPO_ROOT/remote_control/templates=remote_control/templates"
    "--include-data-dir=$REPO_ROOT/ui/assets=ui/assets"
    "--include-data-dir=$REPO_ROOT/ui/fonts=ui/fonts"
)

echo "Nuitka version:"
python -m nuitka --version
echo "GCC version:"
gcc --version | head -n 1

echo "Building main application with Nuitka..."
python -m nuitka \
    --mode=standalone \
    "--output-dir=$DIST_DIR" \
    "--output-folder-name=$APP_NAME" \
    "--output-filename=$APP_NAME" \
    "${COMMON_NUITKA_ARGS[@]}" \
    "$ENTRY_POINT"

BUILT_APP_DIR="$DIST_DIR/$APP_NAME.dist"
if [[ ! -d "$BUILT_APP_DIR" ]]; then
    echo "Nuitka output folder not found: $BUILT_APP_DIR" >&2
    exit 1
fi

# Copy version.json to package root
cp -f "$VERSION_PATH" "$BUILT_APP_DIR/version.json"

# Existing 2.8.0 auto-updaters only accept package roots with _internal present.
INTERNAL_COMPAT_DIR="$BUILT_APP_DIR/_internal"
mkdir -p "$INTERNAL_COMPAT_DIR"
printf '%s\n' "compatibility marker" > "$INTERNAL_COMPAT_DIR/.nuitka-standalone"

echo "Building updater with Nuitka..."
UPDATER_OUTPUT_DIR="$BUILD_DIR/nuitka-updater"
mkdir -p "$UPDATER_OUTPUT_DIR"

python -m nuitka \
    --mode=onefile \
    "--output-dir=$UPDATER_OUTPUT_DIR" \
    --output-filename=updater \
    --assume-yes-for-downloads \
    --deployment \
    --enable-plugin=pyside6 \
    "$UPDATER_ENTRY_POINT"

UPDATER_EXE="$UPDATER_OUTPUT_DIR/updater"
if [[ ! -f "$UPDATER_EXE" ]]; then
    if [[ -f "$UPDATER_OUTPUT_DIR/updater.bin" ]]; then
        mv "$UPDATER_OUTPUT_DIR/updater.bin" "$UPDATER_EXE"
    else
        echo "Updater output not found: $UPDATER_EXE" >&2
        exit 1
    fi
fi

chmod +x "$UPDATER_EXE"

# Remove any logs/config from built app
for root in "$BUILT_APP_DIR" "$BUILT_APP_DIR/_internal"; do
    if [[ -d "$root" ]]; then
        for forbidden_dir in logs config_data; do
            p="$root/$forbidden_dir"
            if [[ -d "$p" ]]; then
                rm -rf "$p"
            fi
        done
        for forbidden_file in config_dir.txt .env; do
            p="$root/$forbidden_file"
            if [[ -f "$p" ]]; then
                rm -f "$p"
            fi
        done
    fi
done

echo "Creating release package..."
STAGING_DIR="$DIST_DIR/$PACKAGE_NAME"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

MAIN_STAGE="$STAGING_DIR/$PACKAGE_APP_DIR_NAME"
OPTIONAL_STAGE="$STAGING_DIR/$PACKAGE_OPTIONAL_DIR_NAME"
mkdir -p "$MAIN_STAGE" "$OPTIONAL_STAGE"

cp -r "$BUILT_APP_DIR"/. "$MAIN_STAGE/"
cp "$UPDATER_EXE" "$OPTIONAL_STAGE/updater"

# Create tar.gz archive
ARCHIVE_PATH="$DIST_DIR/$PACKAGE_NAME.tar.gz"
rm -f "$ARCHIVE_PATH"
tar -czvf "$ARCHIVE_PATH" -C "$STAGING_DIR" .

echo "Created release asset: $ARCHIVE_PATH"
