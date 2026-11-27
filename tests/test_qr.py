# -*- coding: utf-8 -*-
"""Pruebas del generador QR propio (scripts/qr.py).

La matriz «dorada» quedó verificada celda a celda contra la biblioteca de
referencia de Project Nayuki (MIT), y el decodificado real con OpenCV se
ejecuta aquí cuando la biblioteca está instalada.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import qr  # noqa: E402

# Matriz v1-M para b"HELLO" (idéntica a la de la biblioteca de referencia)
GOLDEN = [
    [1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 1, 0, 1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 1, 1],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
    [1, 0, 0, 0, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 0, 1],
    [0, 0, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1, 1, 1],
    [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0],
    [1, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 0, 1, 0, 0, 0, 0],
    [0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 0, 0, 1, 1, 0],
    [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 1, 0, 1, 1],
    [1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1, 1, 0, 0, 0, 1, 0, 1, 0],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 1, 0, 0, 0, 1, 0],
    [1, 0, 1, 1, 1, 0, 1, 0, 1, 0, 0, 1, 0, 0, 1, 1, 1, 0, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 1, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 1, 1, 1, 0, 0, 0],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0],
    [1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1],
]


def test_golden_matrix():
    assert qr.qr_matrix(b"HELLO") == GOLDEN


def test_codewords_v1():
    # Datos + corrección v1-M para HELLO (verificado contra la referencia)
    assert qr._codewords(b"HELLO", 1).hex() == "40548454c4c4f0ec11ec11ec11ec11ec23732399ec08c9f737df"


def test_capacidades_y_lados():
    lados = {v: len(qr.qr_matrix(b"x" * qr.DATA_MAX[v])) for v in range(1, 11)}
    assert lados == {v: 17 + 4 * v for v in range(1, 11)}
    with pytest.raises(ValueError):
        qr.qr_matrix(b"x" * (qr.DATA_MAX[10] + 1))


def test_svg():
    svg = qr.qr_svg(b"HELLO")
    assert svg.startswith("<svg") and svg.count("<rect") > 200 and 'viewBox="0 0 116 116"' in svg


def test_decodificado_opencv():
    """Decodifica un QR por versión con OpenCV (requiere opencv-python y numpy)."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    ok = 0
    for v in range(1, 11):
        n = qr.DATA_MAX[v]
        data = (b"https://ejemplo.local/pair?c=123456&t=" + bytes(65 + i % 26 for i in range(n)))[:n]
        m = qr.qr_matrix(data)
        assert len(m) == qr.VERSIONS[v][0]
        img = 255 - np.array(m, dtype=np.uint8) * 255      # oscuro en negro
        img = cv2.copyMakeBorder(img, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        dec = ""
        for escala in (3, 6, 2, 4):                        # OpenCV 5.x falla con algunas escalas
            big = cv2.resize(img, None, fx=escala, fy=escala, interpolation=cv2.INTER_NEAREST)
            try:
                dec = cv2.QRCodeDetector().detectAndDecode(big)[0]
            except cv2.error:
                dec = ""
            if dec:
                break
        assert dec == data.decode(), f"v{v}: OpenCV no decodifica el QR generado"
        ok += 1
    assert ok == 10
