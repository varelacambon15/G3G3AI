# -*- coding: utf-8 -*-
"""Generador de códigos QR (byte mode, corrección de errores M) sin dependencias.

Se usa en el servidor para mostrar un QR con la dirección y la contraseña de G3G3AI
y escanearlo con la app de Android (página /m). Implementa las versiones 1 a 10 de la
norma ISO/IEC 18004 (para un enlace de emparejamiento, ~80 bytes, sobra con la v5).
`tests/test_qr.py` lo verifica decodificándolo con OpenCV y comprobando que los
códigos de datos + corrección cuadran exactamente con la capacidad de cada versión.
"""
from __future__ import annotations

# Por versión: lado en módulos (21 + 4·(v-1)) y bloques (nº de bloques, datos, corrección).
# Datos + corrección por bloque debe sumar la capacidad total de la versión (ver test).
VERSIONS: dict[int, tuple[int, list[tuple[int, int, int]]]] = {
    1: (21, [(1, 16, 10)]),
    2: (25, [(1, 28, 16)]),
    3: (29, [(1, 44, 26)]),
    4: (33, [(2, 32, 18)]),
    5: (37, [(2, 43, 24)]),
    6: (41, [(4, 27, 16)]),
    7: (45, [(4, 31, 18)]),
    8: (49, [(2, 38, 22), (2, 39, 22)]),
    9: (53, [(3, 36, 22), (2, 37, 22)]),
    10: (57, [(4, 43, 26), (1, 44, 26)]),
}
DATA_MAX = {}  # bytes de datos que caben por versión (cabecera de modo/longitud y terminador aparte)
for _v, (_, _blocks) in VERSIONS.items():
    _cap_bits = sum(nb * d for nb, d, _ in _blocks) * 8
    DATA_MAX[_v] = (_cap_bits - 4 - (8 if _v < 10 else 16)) // 8
ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30],
         6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42], 9: [6, 26, 46], 10: [6, 28, 50]}

# Aritmética de Galois GF(256) para la corrección Reed-Solomon.
GF_EXP = [0] * 512
GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    GF_EXP[_i] = _x
    GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    GF_EXP[_i] = GF_EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return GF_EXP[GF_LOG[a] + GF_LOG[b]]


def _poly_mul(p: list[int], q: list[int]) -> list[int]:
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a:
            for j, b in enumerate(q):
                if b:
                    out[i + j] ^= _gmul(a, b)
    return out


def _ecc(data: bytes, n: int) -> bytes:
    """n bytes de corrección Reed-Solomon para `data`."""
    gen = [1]
    for i in range(n):
        gen = _poly_mul(gen, [1, GF_EXP[i]])
    res = list(data) + [0] * n
    for i in range(len(data)):
        c = res[i]
        if c:
            for j in range(1, n + 1):
                res[i + j] ^= _gmul(gen[j], c)
    return bytes(res[-n:])


def _version_for(n: int) -> int:
    for v, cap in DATA_MAX.items():
        if n <= cap:
            return v
    raise ValueError(f"Demasiados datos para la versión 10 ({n} bytes)")


def _codewords(data: bytes, version: int) -> bytes:
    """Codewords finales: datos (con cabecera y relleno) entrelazados con su corrección."""
    blocks = VERSIONS[version][1]
    # Cabecera: modo 0100 + longitud (8 bits en v1-9, 16 bits desde la v10)
    bits = [0, 1, 0, 0]
    if version < 10:
        bits += [(len(data) >> i) & 1 for i in range(7, -1, -1)]
    else:
        bits += [(len(data) >> i) & 1 for i in range(15, -1, -1)]
    for b in data:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    cap_bits = sum(n * d for n, d, _ in blocks) * 8
    bits = bits[:cap_bits - 4] if len(bits) > cap_bits - 4 else bits  # deja sitio al terminador
    bits += [0] * min(4, cap_bits - len(bits))                       # terminador
    bits += [0] * (-len(bits) % 8)                                   # relleno a byte
    out = bytearray(int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8))
    pad = [0xEC, 0x11]
    i = 0
    while len(out) < cap_bits // 8:
        out.append(pad[i % 2])
        i += 1
    # Parte en bloques, calcula la corrección de cada uno y entrelaza
    bd, be, pos = [], [], 0
    for n, dlen, elen in blocks:
        for _ in range(n):
            d = bytes(out[pos:pos + dlen])
            bd.append(d)
            be.append(_ecc(d, elen))
            pos += dlen
    stream = bytearray()
    for i in range(max(len(b) for b in bd)):
        stream += bytes(b[i] for b in bd if i < len(b))
    for i in range(max(len(b) for b in be)):
        stream += bytes(b[i] for b in be if i < len(b))
    return bytes(stream)


def _function_matrix(size: int, version: int) -> list[list[int | None]]:
    """Patrones fijos del QR; None donde va la zona de datos."""
    m: list[list[int | None]] = [[None] * size for _ in range(size)]

    def put(r: int, c: int, v: int) -> None:
        if 0 <= r < size and 0 <= c < size:
            m[r][c] = v

    # Patrones de posición (7x7) con su separación: anillo oscuro (d=3), claro (d=2),
    # oscuro (d=1) y centro oscuro (d=0); el borde (d=4) es la separación clara.
    for r0, c0 in ((0, 0), (0, size - 7), (size - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                d = max(abs(dr - 3), abs(dc - 3))
                put(r0 + dr, c0 + dc, 0 if d in (2, 4) else 1)
    # Líneas de temporización (sólo donde no hay ya un patrón fijo)
    for i in range(size):
        if m[6][i] is None:
            m[6][i] = 1 if i % 2 == 0 else 0
        if m[i][6] is None:
            m[i][6] = 1 if i % 2 == 0 else 0
    # Patrones de alineación (5x5), excepto los que solapan un patrón de posición
    for r in ALIGN[version]:
        for c in ALIGN[version]:
            if (r, c) in ((6, 6), (6, size - 7), (size - 7, 6)):
                continue
            for dr in (-2, -1, 0, 1, 2):
                for dc in (-2, -1, 0, 1, 2):
                    put(r + dr, c + dc, 0 if max(abs(dr), abs(dc)) == 1 else 1)
    # Bloques de versión (sólo v7+): dos copias con su BCH, junto a las esquinas
    if version >= 7:
        rem = version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vbits = (version << 12) | rem
        for i in range(18):
            b = (vbits >> i) & 1
            a = size - 11 + i % 3
            put(i // 3, a, b)
            put(a, i // 3, b)
    # Zona de formato y módulo oscuro permanente
    for i in range(9):
        for j in range(9):
            if m[i][j] is None:
                m[i][j] = 0
    for i in range(size - 8, size):
        for j in range(9):
            if m[i][j] is None:
                m[i][j] = 0
    for i in range(9):
        for j in range(size - 8, size):
            if m[i][j] is None:
                m[i][j] = 0
    m[size - 8][8] = 1
    return m


def _is_function(m: list[list[int | None]], r: int, c: int) -> bool:
    return m[r][c] is not None


def _format_bits(mask: int) -> int:
    """15 bits de formato: nivel M (00), máscara y BCH con la máscara 101010000010010."""
    data = (0b00 << 3) | mask
    rem = data << 10
    for i in range(14, 9, -1):
        if rem & (1 << i):
            rem ^= 0b10100110111 << (i - 10)
    return ((data << 10) | rem) ^ 0b101010000010010


def _set_format(m: list[list[int | None]], mask: int) -> None:
    """Escribe los 15 bits de formato en sus dos copias (norma, figura 25)."""
    size = len(m)
    fmt = _format_bits(mask)
    bit = lambda i: (fmt >> i) & 1  # noqa: E731
    for i in range(6):              # primera copia, alrededor de la esquina superior izquierda
        m[i][8] = bit(i)            # columna 8, filas 0..5 = b0..b5
        m[8][5 - i] = bit(i + 9)    # fila 8, columnas 5..0 = b9..b14
    m[7][8] = bit(6)
    m[8][8] = bit(7)
    m[8][7] = bit(8)
    for i in range(8):              # segunda copia, fila 8 (arriba a la derecha)
        m[8][size - 1 - i] = bit(i)         # columnas size-1..size-8 = b0..b7
    for i in range(8, 15):          # segunda copia, columna 8 (abajo a la izquierda)
        m[size - 15 + i][8] = bit(i)        # filas size-7..size-1 = b8..b14
    m[size - 8][8] = 1              # módulo oscuro permanente


def _mask_on(mask: int, r: int, c: int) -> bool:
    if mask == 0:
        return (r + c) % 2 == 0
    if mask == 1:
        return r % 2 == 0
    if mask == 2:
        return c % 3 == 0
    if mask == 3:
        return (r + c) % 3 == 0
    if mask == 4:
        return (r // 2 + c // 3) % 2 == 0
    if mask == 5:
        return (r * c) % 2 + (r * c) % 3 == 0
    if mask == 6:
        return ((r * c) % 2 + (r * c) % 3) % 2 == 0
    return ((r + c) % 2 + (r * c) % 3) % 2 == 0


def _penalty(m: list[list[int | None]]) -> int:
    size = len(m)
    total = 0
    for r in range(size):          # N1: carreras de 5+ del mismo color
        for line in (m[r], [m[i][r] for i in range(size)]):
            run = 1
            for i in range(1, size):
                run = run + 1 if line[i] == line[i - 1] else 1
                if run >= 5:
                    total += 3 + (run - 5)
    for r in range(size - 1):      # N2: bloques 2x2
        for c in range(size - 1):
            if m[r][c] == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                total += 3
    p1, p2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1], [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    for r in range(size):          # N3: proporción 1:1:3:1:1 en filas y columnas
        for c in range(size - 10):
            if [m[r][c + k] for k in range(11)] in (p1, p2):
                total += 40
            if [m[c + k][r] for k in range(11)] in (p1, p2):
                total += 40
    dark = sum(1 for r in range(size) for c in range(size) if m[r][c])  # N4: proporción de oscuros
    total += abs(dark * 100 // (size * size) - 50) // 5 * 10
    return total


def qr_matrix(data: bytes, mask: int | None = None) -> list[list[int]]:
    """Matriz del QR (1 = oscuro) para `data`, versión mínima que quepa (1..10).

    Con `mask` se fuerza una máscara concreta (0..7); sin ella se elige la de
    menor penalización, como hace la norma.
    """
    version = _version_for(len(data))
    size = VERSIONS[version][0]
    stream = _codewords(data, version)
    base = _function_matrix(size, version)
    best = None
    for mask in ([mask] if mask is not None else range(8)):
        m = [row[:] for row in base]
        idx = 0
        col = size - 1
        up = True
        while col > 0:                      # coloca los bits en zigzag
            if col == 6:
                col -= 1
            for k in range(size):
                r = (size - 1 - k) if up else k
                for c in (col, col - 1):
                    if not _is_function(m, r, c):
                        bit = (stream[idx // 8] >> (7 - idx % 8)) & 1 if idx < len(stream) * 8 else 0
                        m[r][c] = bit ^ (1 if _mask_on(mask, r, c) else 0)
                        idx += 1
            up = not up
            col -= 2
        _set_format(m, mask)
        score = _penalty(m)
        if best is None or score < best[0]:
            best = (score, m)
    return best[1]


def qr_svg(data: bytes, module: int = 4, border: int = 4) -> str:
    """SVG del QR como cadena (para incrustarlo en la interfaz)."""
    m = qr_matrix(data)
    size = len(m) + 2 * border
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size * module} {size * module}" '
             f'shape-rendering="crispEdges" role="img" aria-label="QR de emparejamiento">']
    parts.append(f'<rect width="{size * module}" height="{size * module}" fill="#fff"/>')
    for r, row in enumerate(m):
        for c, v in enumerate(row):
            if v:
                parts.append(f'<rect x="{(c + border) * module}" y="{(r + border) * module}" '
                             f'width="{module}" height="{module}"/>')
    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    import sys
    payload = sys.argv[1].encode() if len(sys.argv) > 1 else b"ejemplo"
    print(qr_svg(payload))
