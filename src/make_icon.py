"""
Generate elite-discoveries.ico — a stealth-purple diamond (the app's brand mark)
on a transparent background. Stdlib only (no Pillow): hand-rolls a 256x256 RGBA
PNG and wraps it in an ICO. Run once:  python make_icon.py
"""

import os
import struct
import zlib

SIZE = 256
VIOLET = (165, 47, 255)     # #A52FFF
CORE = (210, 180, 250)      # light lavender core


def _mix(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _pixels() -> bytearray:
    cx = cy = (SIZE - 1) / 2.0
    rx = ry = SIZE * 0.40            # diamond half-extent
    buf = bytearray(SIZE * SIZE * 4)
    for y in range(SIZE):
        for x in range(SIZE):
            dx = abs(x - cx) / rx
            dy = abs(y - cy) / ry
            d = dx + dy                       # 0 at centre, 1 on the diamond edge
            i = (y * SIZE + x) * 4
            if d <= 1.0:
                col = _mix(CORE, VIOLET, min(1.0, d))        # bright centre -> violet edge
                edge = max(0.0, min(1.0, (1.0 - d) / 0.06))  # soft 1px edge
                a = int(255 * (0.6 + 0.4 * edge)) if d > 0.94 else 255
                buf[i:i + 4] = bytes((col[0], col[1], col[2], a))
            elif d <= 1.55:
                glow = (1.55 - d) / 0.55                      # outer glow halo
                a = int(120 * glow * glow)
                buf[i:i + 4] = bytes((VIOLET[0], VIOLET[1], VIOLET[2], a))
            # else: fully transparent (already 0)
    return buf


def _png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(typ: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)                          # filter type 0 (none)
        raw += rgba[y * stride:(y + 1) * stride]
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def _ico(png_bytes: bytes, size: int) -> bytes:
    dim = 0 if size >= 256 else size           # 0 means 256 in the ICO header
    header = struct.pack("<HHH", 0, 1, 1)      # reserved, type=icon, count=1
    entry = struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png_bytes), 22)
    return header + entry + png_bytes


def main():
    png = _png(SIZE, SIZE, bytes(_pixels()))
    # Always write next to the project's assets/ dir (src/ is this file's
    # own directory), regardless of the caller's current working directory.
    here = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(here, "..", "assets")
    os.makedirs(assets_dir, exist_ok=True)
    out_path = os.path.join(assets_dir, "elite-discoveries.ico")
    with open(out_path, "wb") as fh:
        fh.write(_ico(png, SIZE))
    print(f"Wrote {out_path} ({SIZE}x{SIZE}, {len(png)} bytes PNG)")


if __name__ == "__main__":
    main()
