"""Genera el catálogo de proveedores de la app de Android a partir del del escritorio (g3g3ai/catalog.py).

    python scripts/gen_android_catalog.py
Los tests comprueban que el archivo generado está al día.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from g3g3ai.catalog import as_list  # noqa: E402

OUT = ROOT / "android/app/src/main/assets/direct/catalog.js"


def render() -> str:
    items = [c for c in as_list() if "local" not in c["tags"]]   # en el móvil no hay Ollama ni LM Studio locales
    return ("// Generado por scripts/gen_android_catalog.py a partir de g3g3ai/catalog.py: no editar a mano.\n"
            "window.G3_CATALOG = " + json.dumps(items, ensure_ascii=False, indent=1) + ";\n")


if __name__ == "__main__":
    OUT.write_text(render(), encoding="utf-8")
    print("escrito", OUT)
