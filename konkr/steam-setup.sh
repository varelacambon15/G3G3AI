#!/usr/bin/env bash
# Integra G3G3AI con el escritorio y con Steam (modo Big Picture). Lo llama install.sh.
set -u
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${G3G3AI_DATA_DIR:-$HOME/.local/share/g3g3ai}"
APPS="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/256x256/apps"
say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }

mkdir -p "$DATA_DIR/bin" "$APPS" "$ICON_DIR"
install -m 755 "$REPO_DIR/konkr/g3g3ai-launch.sh" "$DATA_DIR/bin/g3g3ai-launch"
cp "$REPO_DIR/packaging/icon.png" "$ICON_DIR/g3g3ai.png"

cat > "$APPS/g3g3ai.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=G3G3AI
Comment=Chat de IA local y por API
Exec=$DATA_DIR/bin/g3g3ai-launch
Icon=g3g3ai
Terminal=false
Categories=Utility;Development;
DESK
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" >/dev/null 2>&1 || true

# Navegador para el modo quiosco
has_browser=0
for app in org.chromium.Chromium com.google.Chrome com.brave.Browser com.microsoft.Edge org.mozilla.firefox; do
  command -v flatpak >/dev/null && flatpak info "$app" >/dev/null 2>&1 && has_browser=1
done
for bin in chromium chromium-browser google-chrome brave firefox; do command -v "$bin" >/dev/null && has_browser=1; done
if [ "$has_browser" = 0 ] && command -v flatpak >/dev/null; then
  say "Instalando Chromium (Flatpak, sólo para tu usuario) para abrir G3G3AI en modo juego"
  flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo || true
  flatpak install --user -y --noninteractive flathub org.chromium.Chromium || \
    echo "No se pudo instalar Chromium. Instálalo desde Discover en el modo escritorio."
fi

# Acceso directo en Steam
say "Añadiendo G3G3AI a Steam"
if command -v steamos-add-to-steam >/dev/null; then
  steamos-add-to-steam "$APPS/g3g3ai.desktop" && echo "Añadido. Aparecerá en Biblioteca → No de Steam." || ADD_FAILED=1
else
  ADD_FAILED=1
fi
if [ "${ADD_FAILED:-0}" = 1 ]; then
  cat <<TXT
No se pudo añadir automáticamente. Hazlo una vez a mano:
  1. Modo escritorio → abre Steam → Juegos → «Añadir un juego que no es de Steam a mi biblioteca».
  2. Marca «G3G3AI» (o pulsa Examinar y elige $DATA_DIR/bin/g3g3ai-launch).
  3. Vuelve al modo juego: lo tendrás en Biblioteca → No de Steam.
TXT
fi
