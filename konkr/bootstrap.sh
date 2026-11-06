#!/usr/bin/env bash
# Instalación en una línea (repositorio público):
#   bash <(curl -fsSL https://raw.githubusercontent.com/varelacambon15/G3G3AI/main/konkr/bootstrap.sh)
set -euo pipefail
REPO_URL="${G3G3AI_REPO:-https://github.com/varelacambon15/G3G3AI.git}"
BRANCH="${G3G3AI_BRANCH:-main}"
DEST="${G3G3AI_DIR:-$HOME/G3G3AI}"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" pull --ff-only
else
  git clone -b "$BRANCH" "$REPO_URL" "$DEST"
fi
cd "$DEST" && ./install.sh "$@"
