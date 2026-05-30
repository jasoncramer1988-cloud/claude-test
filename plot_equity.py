#!/usr/bin/env python3
"""Render the equity curve from a run into a PNG -- pure stdlib, no deps.

Reads runs/<dir>/equity_curve.csv and writes equity_curve.png next to it, so
you get a picture of the simulated account value without installing anything.

    python3 plot_equity.py [runs/latest]
"""

from __future__ import annotations

import csv
import struct
import sys
import zlib

# Tiny 5x7 bitmap font so we can label axes without a font library.
FONT = {
    '0': ["111", "101", "101", "101", "111"], '1': ["010", "110", "010", "010", "111"],
    '2': ["111", "001", "111", "100", "111"], '3': ["111", "001", "111", "001", "111"],
    '4': ["101", "101", "111", "001", "001"], '5': ["111", "100", "111", "001", "111"],
    '6': ["111", "100", "111", "101", "111"], '7': ["111", "001", "010", "010", "010"],
    '8': ["111", "101", "111", "101", "111"], '9': ["111", "101", "111", "001", "111"],
    '.': ["000", "000", "000", "000", "010"], ',': ["000", "000", "000", "010", "100"],
    '+': ["000", "010", "111", "010", "000"], '-': ["000", "000", "111", "000", "000"],
    '%': ["101", "001", "010", "100", "101"], ' ': ["000", "000", "000", "000", "000"],
    'N': ["101", "111", "111", "101", "101"], 'A': ["111", "101", "111", "101", "101"],
    'V': ["101", "101", "101", "101", "010"], 'U': ["101", "101", "101", "101", "111"],
    'S': ["111", "100", "111", "001", "111"], 'D': ["110", "101", "101", "101", "110"],
    'T': ["111", "010", "010", "010", "010"], 'c': ["000", "111", "100", "100", "111"],
    'y': ["000", "101", "111", "001", "111"], 'l': ["110", "010", "010", "010", "111"],
    'e': ["000", "111", "111", "100", "111"], 'k': ["100", "101", "110", "101", "101"],
    'i': ["010", "000", "010", "010", "010"], 'n': ["000", "110", "101", "101", "101"],
    'a': ["000", "111", "101", "101", "111"], 'f': ["011", "010", "111", "010", "010"],
    'r': ["000", "110", "101", "100", "100"], 't': ["010", "111", "010", "010", "011"],
    's': ["000", "111", "100", "001", "110"], ':': ["000", "010", "000", "010", "000"],
}


def render(run_dir: str) -> str:
    rows = list(csv.DictReader(open(f"{run_dir}/equity_curve.csv")))
    cycles = [int(r["cycle"]) for r in rows]
    navs = [float(r["nav"]) for r in rows]
    pos = [int(r["open_positions"]) for r in rows]

    W, H = 920, 480
    ml, mr, mt, mb = 75, 25, 45, 55
    pw, ph = W - ml - mr, H - mt - mb
    BG = (13, 17, 23)
    buf = bytearray(BG * (W * H))

    def setpx(x, y, c):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 3
            buf[i:i + 3] = bytes(c)

    def hline(x0, x1, y, c):
        for x in range(int(x0), int(x1) + 1):
            setpx(x, int(y), c)

    def vline(x, y0, y1, c):
        for y in range(int(y0), int(y1) + 1):
            setpx(int(x), y, c)

    def line(x0, y0, x1, y1, c, thick=1):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            for ox in range(-thick + 1, thick):
                for oy in range(-thick + 1, thick):
                    setpx(x0 + ox, y0 + oy, c)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def text(s, x, y, c, scale=2):
        cx = x
        for ch in s:
            g = FONT.get(ch, FONT[' '])
            for ry, row in enumerate(g):
                for rx, bit in enumerate(row):
                    if bit == '1':
                        for sx in range(scale):
                            for sy in range(scale):
                                setpx(cx + rx * scale + sx, y + ry * scale + sy, c)
            cx += 4 * scale
        return cx

    xmin, xmax = min(cycles), max(cycles)
    ymin, ymax = min(navs), max(navs)
    pad = (ymax - ymin) * 0.12 or 1
    ymin -= pad
    ymax += pad
    start, final = navs[0], navs[-1]

    def px(c):
        return ml + (c - xmin) / (xmax - xmin) * pw

    def py(v):
        return mt + (1 - (v - ymin) / (ymax - ymin)) * ph

    GRID, AXIS = (34, 48, 63), (110, 118, 129)
    for i in range(5):
        hline(ml, ml + pw, py(ymin + (ymax - ymin) * i / 4), GRID)
    for i in range(6):
        vline(px(xmin + (xmax - xmin) * i / 5), mt, mt + ph, GRID)
    vline(ml, mt, mt + ph, AXIS)
    hline(ml, ml + pw, mt + ph, AXIS)

    yb = int(py(start))
    for x in range(ml, ml + pw, 10):
        hline(x, x + 5, yb, (110, 118, 129))

    OPEN = (20, 30, 45)
    for k in range(len(cycles) - 1):
        if pos[k] > 0:
            x = int(px(cycles[k]))
            for y in range(mt, mt + ph):
                i = (y * W + x) * 3
                if buf[i:i + 3] == bytes(BG):
                    buf[i:i + 3] = bytes(OPEN)

    col = (63, 185, 80) if final >= start else (248, 81, 73)
    for k in range(len(cycles) - 1):
        line(px(cycles[k]), py(navs[k]), px(cycles[k + 1]), py(navs[k + 1]), col, thick=2)

    MUT = (122, 139, 154)
    text("NAV USDT", ml - 70, mt - 22, MUT, 2)
    for i in range(5):
        v = ymin + (ymax - ymin) * i / 4
        text(f"{v:,.0f}", 8, int(py(v)) - 4, MUT, 2)
    for i in range(6):
        c = xmin + (xmax - xmin) * i / 5
        text(f"{int(c)}", int(px(c)) - 12, mt + ph + 12, MUT, 2)
    ret = (final - start) / start * 100
    text(f"start {start:,.0f}   final {final:,.0f}   {ret:+.2f}%", ml, mt + ph + 30, col, 2)

    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += buf[y * W * 3:(y + 1) * W * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(typ, data):
        c = typ + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", comp)
    png += chunk(b"IEND", b"")
    out = f"{run_dir}/equity_curve.png"
    open(out, "wb").write(png)
    return out


if __name__ == "__main__":
    run_dir = sys.argv[1] if len(sys.argv) > 1 else "runs/latest"
    path = render(run_dir)
    print(f"wrote {path}")
