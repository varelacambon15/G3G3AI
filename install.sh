#!/usr/bin/env bash
# Instalador de G3G3AI para Konkr Pocket Fit (SteamOS ARM) y otros Linux.
# No necesita root: todo se instala en tu carpeta personal.
#
#   ./install.sh               instala todo (entorno Python + llama.cpp + servicio)
#   ./install.sh --vulkan      compila llama.cpp con Vulkan (GPU Adreno, experimental)
#   ./install.sh --skip-llama  no compila llama.cpp (sólo APIs o ya lo tienes)
#   ./install.sh --no-service  no instala el servicio de arranque automático
#   ./install.sh --update-llama  vuelve a descargar y compilar llama.cpp
#   ./install.sh --no-steam    no crea el acceso en Steam / menú de aplicaciones
#   ./install.sh --with-sd     compila también stable-diffusion.cpp (generar imágenes en local)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${G3G3AI_DATA_DIR:-$HOME/.local/share/g3g3ai}"
VENV="$DATA_DIR/venv"
LLAMA_DIR="$DATA_DIR/llama.cpp"
BIN_DIR="$HOME/.local/bin"

VULKAN=0; SKIP_LLAMA=0; SERVICE=1; UPDATE_LLAMA=0; STEAM=1; WITH_SD=0
for a in "$@"; do
  case "$a" in
    --vulkan) VULKAN=1 ;;
    --skip-llama) SKIP_LLAMA=1 ;;
    --no-service) SERVICE=0 ;;
    --update-llama) UPDATE_LLAMA=1 ;;
    --no-steam) STEAM=0 ;;
    --with-sd) WITH_SD=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $a"; exit 1 ;;
  esac
done

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[aviso] %s\033[0m\n' "$*"; }

mkdir -p "$DATA_DIR" "$BIN_DIR"

# 1) Entorno Python ------------------------------------------------------------
say "Preparando entorno Python en $VENV"
python3 -c 'import sys; assert sys.version_info >= (3, 10), "Se necesita Python 3.10+"'
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -q -r "$REPO_DIR/requirements.txt"

# 2) llama.cpp -------------------------------------------------------------------
if [ "$SKIP_LLAMA" = 0 ]; then
  for t in git cmake gcc g++ make; do
    command -v "$t" >/dev/null || { warn "Falta '$t'; no se puede compilar llama.cpp."; SKIP_LLAMA=1; }
  done
fi
if [ "$SKIP_LLAMA" = 0 ]; then
  if [ -d "$LLAMA_DIR/.git" ] && [ "$UPDATE_LLAMA" = 1 ]; then
    say "Actualizando llama.cpp"
    git -C "$LLAMA_DIR" pull --ff-only
  elif [ ! -d "$LLAMA_DIR/.git" ]; then
    say "Descargando llama.cpp"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
  fi
  if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ] || [ "$UPDATE_LLAMA" = 1 ] || [ "$VULKAN" = 1 ]; then
    say "Compilando llama-server (puede tardar 10-20 min en el Konkr)"
    # GGML_NATIVE detecta las extensiones ARM de tu CPU (dotprod, i8mm…).
    FLAGS=(-DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF
           -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_CURL=OFF)
    if [ "$VULKAN" = 1 ]; then
      if command -v glslc >/dev/null; then FLAGS+=(-DGGML_VULKAN=ON)
      else warn "No se encontró glslc (Vulkan SDK). Se compila sólo para CPU."; fi
    fi
    # Limitamos los trabajos en paralelo para no agotar los 8 GB de RAM.
    JOBS=$(( $(nproc) > 4 ? 4 : $(nproc) ))
    cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" "${FLAGS[@]}"
    cmake --build "$LLAMA_DIR/build" --config Release -j "$JOBS" --target llama-server
  fi
  "$LLAMA_DIR/build/bin/llama-server" --version 2>&1 | head -n 3 || true
fi

# 2b) stable-diffusion.cpp (opcional) ------------------------------------------------------
if [ "$WITH_SD" = 1 ]; then
  SD_DIR="$DATA_DIR/stable-diffusion.cpp"
  say "Descargando y compilando stable-diffusion.cpp (puede tardar 15-30 min)"
  if [ ! -d "$SD_DIR/.git" ]; then
    git clone --depth 1 --recursive https://github.com/leejet/stable-diffusion.cpp "$SD_DIR"
  else
    git -C "$SD_DIR" pull --ff-only && git -C "$SD_DIR" submodule update --init --recursive
  fi
  JOBS=$(( $(nproc) > 4 ? 4 : $(nproc) ))
  cmake -S "$SD_DIR" -B "$SD_DIR/build" -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON
  cmake --build "$SD_DIR/build" --config Release -j "$JOBS"
  ls "$SD_DIR/build/bin/" 2>/dev/null | grep -E '^sd(-cli)?$' || echo "[aviso] no se encontró el ejecutable sd en build/bin"
fi

# 3) Lanzador ---------------------------------------------------------------------
say "Creando el comando 'g3g3ai' en $BIN_DIR"
cat > "$BIN_DIR/g3g3ai" <<LAUNCH
#!/usr/bin/env bash
cd "$REPO_DIR" && exec "$VENV/bin/python" -m g3g3ai "\$@"
LAUNCH
chmod +x "$BIN_DIR/g3g3ai"
mkdir -p "$HOME/Models"

# 4) Servicio de usuario (arranca solo al iniciar sesión) ------------------------------------
if [ "$SERVICE" = 1 ] && command -v systemctl >/dev/null; then
  say "Instalando servicio systemd de usuario"
  mkdir -p "$HOME/.config/systemd/user"
  sed -e "s#@REPO_DIR@#$REPO_DIR#g" -e "s#@VENV@#$VENV#g" \
    "$REPO_DIR/systemd/g3g3ai.service" > "$HOME/.config/systemd/user/g3g3ai.service"
  systemctl --user daemon-reload
  systemctl --user enable g3g3ai.service >/dev/null
  systemctl --user restart g3g3ai.service
  sleep 2
  systemctl --user --no-pager --lines=0 status g3g3ai.service || true
fi

# 5) Acceso en Steam (Big Picture) y en el menú de aplicaciones ------------------------------
if [ "$STEAM" = 1 ]; then
  bash "$REPO_DIR/konkr/steam-setup.sh" || true
fi

TOKEN="$("$VENV/bin/python" -c 'import sys; sys.path.insert(0, sys.argv[1]); from g3g3ai.config import Config; print(Config()["token"])' "$REPO_DIR")"
IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}' || true)"
say "¡Listo!"
echo "  En el Konkr:          http://127.0.0.1:8800"
[ -n "$IP" ] && echo "  Desde móvil/portátil: http://$IP:8800/?token=$TOKEN"
echo "  Contraseña:           $TOKEN"
[ "$SERVICE" = 1 ] || echo "  Arranque manual:      g3g3ai"
echo "  Registro del servicio: journalctl --user -u g3g3ai -f"
[ "$STEAM" = 1 ] && echo "  En modo juego:        Biblioteca → No de Steam → G3G3AI"
