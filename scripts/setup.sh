#!/usr/bin/env bash
# Sets up job-radar after a clone: uv, Python and the dependencies, your
# config_local/ folder, and a check of the Claude Code login.
#
#     ./scripts/setup.sh
#
# Safe to run again: it never overwrites config_local/, and it never installs
# or logs in to Claude Code (it only says what to do).

set -euo pipefail

cd "$(dirname "$0")/.."

say() { printf '%s\n' "$*"; }

say "== uv and Python"
if ! command -v uv >/dev/null 2>&1; then
    say "uv not found: installing it with the official installer (https://astral.sh/uv)."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The installer puts uv in ~/.local/bin; use it for the rest of this script.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        say "uv was installed but isn't on PATH yet. Open a new terminal (or source the"
        say "file the installer named above), then run ./scripts/setup.sh again."
        exit 1
    fi
    say "uv installed. In new terminals it is on PATH; in this one, open a new terminal"
    say "or source the file the installer named above before running uv yourself."
else
    say "uv found: $(uv --version)"
fi
uv sync
say "Dependencies installed (uv also fetched Python 3.12+ if it was missing)."

say ""
say "== Your config_local/ folder"
if [ -e config_local ]; then
    say "config_local/ already exists: left as it is, nothing copied over it."
else
    cp -R config_local_example config_local
    say "Copied config_local_example/ to config_local/ (gitignored, never committed)."
fi

say ""
say "== Claude Code"
claude_ok=no
if ! command -v claude >/dev/null 2>&1; then
    say "claude not found. Install Claude Code (https://claude.com/claude-code), run"
    say "\`claude\` once and log in with your Claude Pro or Max subscription."
elif status="$(claude auth status 2>/dev/null || true)" \
    && printf '%s' "$status" | grep -q '"loggedIn": *true'; then
    claude_ok=yes
    say "claude is installed and logged in."
else
    say "claude is installed but not logged in: run \`claude\` (or \`claude auth login\`)"
    say "and log in with your Claude Pro or Max subscription."
fi

say ""
say "== Next steps"
say "1. Try the demo (no network, no Claude): uv run job-radar run --demo"
say "2. Edit the files in config_local/:"
say "   cv.md (or put your CV there as cv.pdf), preferences.md, profile.yaml,"
say "   settings.yaml (only what you change), .env (only for JobsPipe)"
if [ "$claude_ok" = no ]; then
    say "3. Log in to Claude Code (above); every real run checks it first"
    say "4. Run for real: uv run job-radar run"
else
    say "3. Run for real: uv run job-radar run"
fi
