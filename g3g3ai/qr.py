"""Generador de códigos QR (modo byte, corrección M, versiones 1–10) sin dependencias; devuelve SVG.

Sigue la especificación ISO/IEC 18004: codificación, Reed-Solomon sobre GF(256), colocación en zigzag,
las 8 máscaras con su penalización y los bits de formato y versión.
"""
from __future__ import annotations

# Por versión (índice = versión): bytes de corrección por bloque y número de bloques, nivel M
_ECC_PER_BLOCK_M = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_BLOCKS_M = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
MAX_VERSION = 10          # hasta 213 bytes: de sobra para un enlace de emparejamiento


def _raw_modules(ver: int) -> int:
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        a = ver // 7 + 2
        n -= (25 * a - 10) * a - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK_M[ver] * _BLOCKS_M[ver]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 2)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _bit(x: int, i: int) -> bool:
    return ((x >> i) & 1) != 0


def _align_positions(ver: int, size: int) -> list[int]:
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = 26 if ver == 32 else (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    return list(reversed([size - 7 - i * step for i in range(n - 1)] + [6]))


class _Matrix:
    def __init__(self, ver: int):
        self.ver, self.size = ver, ver * 4 + 17
        self.m = [[False] * self.size for _ in range(self.size)]
        self.fn = [[False] * self.size for _ in range(self.size)]
        self._draw_function_patterns()

    def _set(self, x: int, y: int, dark: bool) -> None:
        self.m[y][x] = dark
        self.fn[y][x] = True

    def _draw_function_patterns(self) -> None:
        s = self.size
        for i in range(s):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (s - 4, 3), (3, s - 4)):          # buscadores con separador
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < s and 0 <= y < s:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver, s)
        for i, cx in enumerate(pos):
            for j, cy in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)                                     # reserva el sitio
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = (self.ver << 12) | rem
            for i in range(18):
                a, b = s - 11 + i % 3, i // 3
                self._set(a, b, _bit(bits, i))
                self._set(b, a, _bit(bits, i))

    def _draw_format(self, mask: int) -> None:
        s = self.size
        data = (0 << 3) | mask                                   # nivel M = 0
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = ((data << 10) | rem) ^ 0x5412
        for i in range(0, 6):
            self._set(8, i, _bit(bits, i))
        self._set(8, 7, _bit(bits, 6))
        self._set(8, 8, _bit(bits, 7))
        self._set(7, 8, _bit(bits, 8))
        for i in range(9, 15):
            self._set(14 - i, 8, _bit(bits, i))
        for i in range(0, 8):
            self._set(s - 1 - i, 8, _bit(bits, i))
        for i in range(8, 15):
            self._set(8, s - 15 + i, _bit(bits, i))
        self._set(8, s - 8, True)

    def draw_codewords(self, data: list[int]) -> None:
        s, i = self.size, 0
        for right in range(s - 1, 0, -2):
            if right == 6:
                right = 5
            for vert in range(s):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (s - 1 - vert) if upward else vert
                    if not self.fn[y][x] and i < len(data) * 8:
                        self.m[y][x] = _bit(data[i >> 3], 7 - (i & 7))
                        i += 1

    def apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            for x in range(self.size):
                inv = ((x + y) % 2 == 0, y % 2 == 0, x % 3 == 0, (x + y) % 3 == 0, (x // 3 + y // 2) % 2 == 0,
                       x * y % 2 + x * y % 3 == 0, (x * y % 2 + x * y % 3) % 2 == 0, ((x + y) % 2 + x * y % 3) % 2 == 0)[mask]
                if inv and not self.fn[y][x]:
                    self.m[y][x] = not self.m[y][x]

    def penalty(self) -> int:
        s, m, score = self.size, self.m, 0
        for rows in (m, [list(c) for c in zip(*m)]):             # filas y columnas
            for line in rows:
                run, color = 1, line[0]
                for k in range(1, s):
                    if line[k] == color:
                        run += 1
                        continue
                    score += 3 + (run - 5) if run >= 5 else 0
                    run, color = 1, line[k]
                score += 3 + (run - 5) if run >= 5 else 0
                pat = "".join("1" if v else "0" for v in line)
                for needle in ("10111010000", "00001011101"):
                    score += 40 * pat.count(needle)
        for y in range(s - 1):
            for x in range(s - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(v for row in m for v in row)
        k = (abs(dark * 20 - s * s * 10) + s * s - 1) // (s * s) - 1
        return score + max(k, 0) * 10


def _encode(text: bytes) -> tuple[int, list[int]]:
    for ver in range(1, MAX_VERSION + 1):
        cc_bits = 8 if ver < 10 else 16
        cap = _data_codewords(ver) * 8
        if 4 + cc_bits + len(text) * 8 <= cap:
            break
    else:
        raise ValueError("Texto demasiado largo para el QR")
    bits: list[int] = []

    def put(val: int, n: int) -> None:
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))
    put(0b0100, 4)
    put(len(text), cc_bits)
    for b in text:
        put(b, 8)
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    return ver, data


def _interleave(ver: int, data: list[int]) -> list[int]:
    nb, ecc_len = _BLOCKS_M[ver], _ECC_PER_BLOCK_M[ver]
    raw = _raw_modules(ver) // 8
    short_blocks, short_len = nb - raw % nb, raw // nb
    div = _rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(nb):
        dat = data[k:k + short_len - ecc_len + (0 if i < short_blocks else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, div)
        if i < short_blocks:
            dat = dat + [0]
        blocks.append(dat + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, blk in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_blocks:
                out.append(blk[i])
    return out


def make(text: str) -> list[list[bool]]:
    """Matriz del QR (True = módulo oscuro)."""
    ver, data = _encode(text.encode("utf-8"))
    codewords = _interleave(ver, data)
    best, best_pen = None, None
    for mask in range(8):
        mx = _Matrix(ver)
        mx.draw_codewords(codewords)
        mx.apply_mask(mask)
        mx._draw_format(mask)
        pen = mx.penalty()
        if best_pen is None or pen < best_pen:
            best, best_pen = mx, pen
    return best.m


def svg(text: str, border: int = 4, dark: str = "#000", light: str = "#fff") -> str:
    m = make(text)
    n = len(m) + border * 2
    path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(m) for x, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges" role="img" '
            f'aria-label="Código QR"><rect width="{n}" height="{n}" fill="{light}"/><path d="{path}" fill="{dark}"/></svg>')
