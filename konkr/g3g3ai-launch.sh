#!/usr/bin/env bash
# Abre G3G3AI a pantalla completa. Pensado para lanzarse desde Steam (modo Big Picture / modo juego).
# Arranca el servidor si no está en marcha y abre un navegador en modo quiosco.
# Al salir del "juego" el servidor sigue encendido para que puedas usarlo desde el móvil.
set -u
CFG="${G3G3AI_CONFIG_DIR:-$HOME/.config/g3g3ai}/config.json"
PORT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("port", 8800))' "$CFG" 2>/dev/null || echo 8800)"
URL="http://127.0.0.1:${PORT}/"
SCALE="${G3G3AI_SCALE:-1.25}"   # tamaño de la interfaz en la pantalla de la Konkr

up() { curl -fs -o /dev/null --max-time 1 "$URL"; }
if ! up; then
  systemctl --user start g3g3ai.service 2>/dev/null || (nohup "$HOME/.local/bin/g3g3ai" >/dev/null 2>&1 &)
  for _ in $(seq 1 80); do up && break; sleep 0.25; done
fi

CHROME_FLAGS=(--kiosk --app="$URL" --start-fullscreen --no-first-run --no-default-browser-check
              --password-store=basic --force-device-scale-factor="$SCALE" --disable-features=Translate)
have_flatpak() { command -v flatpak >/dev/null && flatpak info "$1" >/dev/null 2>&1; }

for app in org.chromium.Chromium com.google.Chrome com.brave.Browser com.microsoft.Edge; do
  if have_flatpak "$app"; then exec flatpak run "$app" "${CHROME_FLAGS[@]}"; fi
done
for bin in chromium chromium-browser google-chrome brave; do
  if command -v "$bin" >/dev/null; then exec "$bin" "${CHROME_FLAGS[@]}"; fi
done
if have_flatpak org.mozilla.firefox; then exec flatpak run org.mozilla.firefox --kiosk "$URL"; fi
if command -v firefox >/dev/null; then exec firefox --kiosk "$URL"; fi

echo "No se encontró ningún navegador. Instala Chromium desde Discover (modo escritorio) o ejecuta:"
echo "  flatpak install --user -y flathub org.chromium.Chromium"
exec xdg-open "$URL"
