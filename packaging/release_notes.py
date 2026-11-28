"""Notas de una Release: las novedades (mensajes de los commits desde la versión anterior) y las descargas.

La app las muestra al ofrecer la actualización, así que se escriben para el usuario, en español.
"""
import re
import subprocess


def git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()


prev = git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD^") if git("tag", "-l", "v*") else ""
rng = f"{prev}..HEAD" if prev else "HEAD~10..HEAD"
raw = git("log", rng, "--no-merges", "--pretty=%B%x1e")
items = []
for msg in raw.split("\x1e"):
    lines = [l.rstrip() for l in msg.strip().splitlines()]
    lines = [l for l in lines if l and not re.match(r"^(Co-Authored-By|Claude-Session|Signed-off-by):", l) and "[skip ci]" not in l]
    if not lines or re.match(r"^(CI|ci)[:(]", lines[0]):
        continue
    title = re.sub(r"\s*\(\d+\.\d+\.\d+\)\s*$", "", lines[0])
    items.append((title, [l for l in lines[1:] if l.lstrip().startswith("-") or l.startswith("  ")]))

print("## Novedades")
if not items:
    print("- Mejoras y correcciones.")
for title, rest in items:
    print(f"- **{title}**")
    for l in rest:
        print("  " + l.strip() if l.lstrip().startswith("-") else "    " + l.strip())
print("""
## Descargas
- **G3G3AI-windows-completo.zip** — recomendado en Windows: descomprime y abre `G3G3AI.exe`. Incluye llama.cpp (CPU y gráfica), stable-diffusion.cpp, Python y Git portátiles; no hay que instalar nada más.
- **G3G3AI.exe** — versión ligera para Windows (descarga el motor local al usarlo).
- **G3G3AI-linux-x64-completo.tar.gz** / **G3G3AI-linux-x64** — Linux, completa o ligera.
- **G3G3AI-macos.zip** — macOS (Apple Silicon): descomprime, arrastra **G3G3AI** a Aplicaciones y la primera vez ábrela con clic derecho → *Abrir* (no está notarizada por Apple). El motor local se descarga al usarlo.
- **G3G3AI-android.apk** — app de Android (chat directo con tus APIs y conexión con tu PC). Firmada con clave de prueba: Android puede avisar al instalarla.

Desde la versión 0.43.0, G3G3AI se actualiza solo: botón «Actualizar» abajo a la izquierda (o Ajustes → Buscar actualizaciones).
Windows puede mostrar «SmartScreen» porque el programa no está firmado: *Más información → Ejecutar de todas formas*.""")
