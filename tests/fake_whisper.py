"""whisper-cli falso para las pruebas: comprueba que recibe un WAV válido y devuelve un texto fijo."""
import sys
import wave

args = sys.argv[1:]
f = args[args.index("-f") + 1]
with wave.open(f) as w:
    assert w.getframerate() == 16000 and w.getnchannels() == 1, "se esperaba WAV 16 kHz mono"
    secs = w.getnframes() / 16000
print(f"[BLANK_AUDIO]\n hola desde whisper ({args[args.index('-l') + 1]}, {secs:.1f} s)\n")
