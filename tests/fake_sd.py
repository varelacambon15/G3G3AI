#!/usr/bin/env python3
"""Imita stable-diffusion.cpp: escribe un PNG en la ruta de -o."""
import base64
import sys

args = sys.argv[1:]
out = args[args.index("-o") + 1]
assert "-m" in args and "-p" in args
open(out, "wb").write(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="))
print("ok", " ".join(args))
