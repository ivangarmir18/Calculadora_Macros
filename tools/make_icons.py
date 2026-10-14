"""Genera los iconos de la app (SVG + PNG) sin dependencias externas.

Uso:  python tools/make_icons.py
Dibuja un anillo de progreso (verde) con una llama, sobre fondo oscuro. Los PNG se rasterizan a mano
con supersampling para que se vean suaves.
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "icons"
BG, GREEN, TRACK = (11, 13, 18), (52, 211, 153), (35, 41, 54)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="112" fill="#0b0d12"/>
  <circle cx="256" cy="256" r="150" fill="none" stroke="#232936" stroke-width="40"/>
  <circle cx="256" cy="256" r="150" fill="none" stroke="#34d399" stroke-width="40" stroke-linecap="round"
          stroke-dasharray="660 943" transform="rotate(-90 256 256)"/>
  <path d="M256 190c10 28 42 44 42 82a42 42 0 0 1-84 0c0-14 6-24 14-32 2 14 10 20 18 20-8-26-2-48 10-70z" fill="#34d399"/>
</svg>
"""


def inside_flame(x, y):
    """Silueta de llama simple en coordenadas 0..512 (gota con punta arriba)."""
    cx, cy = 256, 276
    dx, dy = x - cx, y - cy
    if dy >= 0:  # mitad inferior: círculo
        return dx * dx + dy * dy <= 46 * 46
    # mitad superior: se estrecha hacia la punta (y=190)
    t = (-dy) / 86.0
    if t > 1:
        return False
    half = 46 * (1 - t) ** 1.4
    return abs(dx) <= half


def pixel(x, y, ring_frac, maskable):
    """Color (r,g,b,a) del punto (x,y) del lienzo 512x512."""
    scale = 0.74 if maskable else 1.0  # los maskable necesitan margen de seguridad
    ox, oy = 256 + (x - 256) / scale, 256 + (y - 256) / scale
    if not maskable:  # esquinas redondeadas
        rx, ry = min(x, 511 - x), min(y, 511 - y)
        if rx < 112 and ry < 112 and (112 - rx) ** 2 + (112 - ry) ** 2 > 112 ** 2:
            return (0, 0, 0, 0)
    d = math.hypot(ox - 256, oy - 256)
    if abs(d - 150) <= 20:
        ang = (math.degrees(math.atan2(oy - 256, ox - 256)) + 90) % 360
        return GREEN + (255,) if ang <= 360 * ring_frac else TRACK + (255,)
    if inside_flame(ox, oy):
        return GREEN + (255,)
    return BG + (255,)


def png(size, maskable=False, ss=3, ring_frac=0.7):
    rows = []
    for py in range(size):
        row = bytearray([0])
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + .5) / ss) * 512 / size
                    y = (py + (sy + .5) / ss) * 512 / size
                    r, g, b, a = pixel(x, y, ring_frac, maskable)
                    acc[0] += r * a; acc[1] += g * a; acc[2] += b * a; acc[3] += a
            if acc[3]:
                row += bytes([round(acc[0] / acc[3]), round(acc[1] / acc[3]), round(acc[2] / acc[3]), round(acc[3] / (ss * ss))])
            else:
                row += bytes([0, 0, 0, 0])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "icon.svg").write_text(SVG, encoding="utf-8")
    for name, size, mask in [("icon-180.png", 180, False), ("icon-192.png", 192, False),
                             ("icon-512.png", 512, False), ("icon-maskable-512.png", 512, True)]:
        (OUT / name).write_bytes(png(size, mask))
        print("creado", name)

