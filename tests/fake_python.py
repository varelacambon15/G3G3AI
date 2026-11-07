#!/usr/bin/env python3
"""Imita el Python del entorno de compilación: responde a «-m PyInstaller --version» y a una compilación."""
import sys
from pathlib import Path

args = sys.argv[1:]
if args[:2] == ["-m", "PyInstaller"]:
    if "--version" in args:
        print("6.0.0-fake")
        sys.exit(0)
    dist = Path(args[args.index("--distpath") + 1])
    name = args[args.index("--name") + 1]
    script = Path(args[-1])
    if "syntax error" in script.read_text():
        print("SyntaxError: invalid syntax", file=sys.stderr)
        sys.exit(1)
    dist.mkdir(parents=True, exist_ok=True)
    (dist / (name + (".exe" if sys.platform == "win32" else ""))).write_bytes(b"MZ fake executable")
    print("Building EXE completed successfully.")
    sys.exit(0)
if args[:3] == ["-m", "pip", "install"]:
    print("Successfully installed", *args[3:])
    sys.exit(0)
sys.exit(2)
