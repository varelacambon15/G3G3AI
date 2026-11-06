#!/data/data/com.termux/files/usr/bin/bash
# EXPERIMENTAL: ejecutar G3G3AI como servidor en Android con Termux (instala Termux desde F-Droid).
#   pkg install git && git clone https://github.com/varelacambon15/G3G3AI && cd G3G3AI && bash android/termux-install.sh
# Para usar el móvil sólo como cliente no hace falta nada de esto: abre la dirección del Konkr/PC en el navegador.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$HOME/.local/share/g3g3ai"

pkg update -y
pkg install -y python git cmake clang make binutils
# pydantic-core no tiene ruedas para Android: se usa el paquete de Termux o se compila con Rust.
pkg install -y python-pydantic 2>/dev/null || pkg install -y rust
pip install -r "$REPO_DIR/requirements.txt"

if [ ! -x "$DATA_DIR/llama.cpp/build/bin/llama-server" ]; then
  git clone --depth 1 https://github.com/ggml-org/llama.cpp "$DATA_DIR/llama.cpp" 2>/dev/null || true
  cmake -S "$DATA_DIR/llama.cpp" -B "$DATA_DIR/llama.cpp/build" -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF
  cmake --build "$DATA_DIR/llama.cpp/build" -j 4 --target llama-server
fi

mkdir -p "$HOME/bin"
printf '#!/data/data/com.termux/files/usr/bin/bash\ncd "%s" && termux-wake-lock 2>/dev/null; exec python -m g3g3ai "$@"\n' "$REPO_DIR" > "$HOME/bin/g3g3ai"
chmod +x "$HOME/bin/g3g3ai"
echo
echo "Listo. Arranca con:  g3g3ai   y abre http://127.0.0.1:8800 en el navegador del móvil."
echo "Consejo: desactiva la optimización de batería para Termux para que no se cierre en segundo plano."
