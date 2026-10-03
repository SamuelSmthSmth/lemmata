#!/bin/sh
# Install the Lemmata command-line checker (macOS and Linux).
#
#   curl -fsSL https://lemmata.sous.systems/install.sh | sh
#
# What it does, so you can read it before running it:
#   1. uses uv (https://docs.astral.sh/uv/) if you have it, or installs it
#      with Astral's own installer;
#   2. installs the `lemmata` command with `uv tool install`, from the source
#      on GitHub, with its own Python 3.12 -- nothing else on your system is
#      touched;
#   3. runs `lemmata --version` to show it works.
# Running it again upgrades to the newest version.  To remove it:
#   uv tool uninstall aether
#
# LEMMATA_REF picks a branch or tag (default: master).

set -eu

REPO="https://github.com/SamuelSmthSmth/lemmata"
REF="${LEMMATA_REF:-master}"

say() { printf '%s\n' "$*"; }
fail() { printf 'lemmata installer: %s\n' "$*" >&2; exit 1; }

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
    elif [ -x "${HOME}/.local/bin/uv" ]; then
        printf '%s\n' "${HOME}/.local/bin/uv"
    elif [ -x "${HOME}/.cargo/bin/uv" ]; then
        printf '%s\n' "${HOME}/.cargo/bin/uv"
    fi
}

UV="$(find_uv || true)"
if [ -z "${UV}" ]; then
    say "Installing uv, which manages Lemmata's Python for it..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        fail "needs curl or wget to install uv"
    fi
    UV="$(find_uv || true)"
    [ -n "${UV}" ] || fail "uv was installed but cannot be found; open a new terminal and run this again"
fi

say "Installing Lemmata from ${REPO} (${REF})..."
"${UV}" tool install --force --python 3.12 "git+${REPO}@${REF}"

BIN="$("${UV}" --color never tool dir --bin 2>/dev/null || printf '%s' "${HOME}/.local/bin")"
if command -v lemmata >/dev/null 2>&1; then
    lemmata --version
else
    "${BIN}/lemmata" --version
    say ""
    say "Add ${BIN} to your PATH to run \`lemmata\` from anywhere:"
    say "  ${UV} tool update-shell"
fi
say ""
say "Check a proof:  lemmata proof.aether"
say "Or open the app in your browser: https://lemmata.sous.systems/app/"
