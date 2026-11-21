#!/usr/bin/env python3
"""LOOP-1 - The Extension Cord That Powers Itself.

Catalogue photo of an impossible gadget: a white power strip whose own
cord loops back and plugs into itself, with a small desk lamp (the one
accessory) plugged in and lit - proof the strip "works".

Pure stdlib. Deterministic: no random, no clock, no file reads.
Writes /output/entry.png (1024x1024, <= 1 MiB).
"""
import math
import os
import struct
import zlib

W = 1024
H = 1024
OUT = "/output/entry.png"


# ---------------------------------------------------------------- buffer ---
class Canvas:
    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.buf = bytearray(w * h * 3)

    def set(self, x, y, r, g, b):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = r
            self.buf[i + 1] = g
            self.buf[i + 2] = b

    def blend(self, x, y, r, g, b, a):
        """Blend colour (r,g,b) with alpha a (0..1) over existing pixel."""
        if a <= 0:
            return
        if a >= 1:
            self.set(x, y, r, g, b)
            return
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i] = int(self.buf[i] * (1 - a) + r * a)
            self.buf[i + 1] = int(self.buf[i + 1] * (1 - a) + g * a)
            self.buf[i + 2] = int(self.buf[i + 2] * (1 - a) + b * a)

    def get(self, x, y):
        i = (y * self.w + x) * 3
        return self.buf[i], self.buf[i + 1], self.buf[i + 2]


# ---------------------------------------------------------------- shapes ---
def fill_polygon(cv, pts, color, alpha=1.0):
    """Scanline fill of a simple polygon."""
    r, g, b = color
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    y0 = max(0, int(math.floor(min(ys))))
    y1 = min(cv.h - 1, int(math.ceil(max(ys))))
    n = len(pts)
    for y in range(y0, y1 + 1):
        inter = []
        for i in range(n):
            x1, y1p = pts[i]
            x2, y2p = pts[(i + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                t = (y - y1p) / (y2p - y1p)
                inter.append(x1 + t * (x2 - x1))
        inter.sort()
        for k in range(0, len(inter) - 1, 2):
            xa = max(0, int(math.ceil(inter[k])))
            xb = min(cv.w - 1, int(math.floor(inter[k + 1])))
            for x in range(xa, xb + 1):
                cv.blend(x, y, r, g, b, alpha)


def fill_ellipse(cv, cx, cy, rx, ry, color, alpha=1.0):
    r, g, b = color
    x0 = max(0, int(cx - rx))
    x1 = min(cv.w - 1, int(cx + rx))
    y0 = max(0, int(cy - ry))
    y1 = min(cv.h - 1, int(cy + ry))
    for y in range(y0, y1 + 1):
        dy = (y - cy) / ry
        if abs(dy) > 1:
            continue
        dx = rx * math.sqrt(max(0.0, 1 - dy * dy))
        for x in range(max(0, int(cx - dx)), min(cv.w - 1, int(cx + dx)) + 1):
            cv.blend(x, y, r, g, b, alpha)


def fill_circle(cv, cx, cy, rad, color, alpha=1.0):
    fill_ellipse(cv, cx, cy, rad, rad, color, alpha)


def fill_rounded_rect(cv, x0, y0, x1, y1, rad, color, alpha=1.0):
    r, g, b = color
    rad = min(rad, (x1 - x0) / 2, (y1 - y0) / 2)
    fill_polygon(cv, [(x0 + rad, y0), (x1 - rad, y0), (x1, y0 + rad),
                      (x1, y1 - rad), (x1 - rad, y1), (x0 + rad, y1),
                      (x0, y1 - rad), (x0, y0 + rad)], color, alpha)
    for cx, cy in ((x0 + rad, y0 + rad), (x1 - rad, y0 + rad),
                   (x0 + rad, y1 - rad), (x1 - rad, y1 - rad)):
        fill_circle(cv, cx, cy, rad, color, alpha)


def hline(cv, x0, x1, y, color, alpha=1.0):
    r, g, b = color
    for x in range(max(0, int(x0)), min(cv.w - 1, int(x1)) + 1):
        cv.blend(x, int(y), r, g, b, alpha)


def vline(cv, x, y0, y1, color, alpha=1.0):
    r, g, b = color
    for y in range(max(0, int(y0)), min(cv.h - 1, int(y1)) + 1):
        cv.blend(int(x), y, r, g, b, alpha)


def thick_line(cv, x0, y0, x1, y1, width, color, alpha=1.0):
    """Draw a thick line as a chain of circles (fast enough at this size)."""
    dx = x1 - x0
    dy = y1 - y0
    steps = int(max(abs(dx), abs(dy)) * 1.2) + 1
    rad = width / 2.0
    for i in range(steps + 1):
        t = i / steps
        fill_circle(cv, x0 + dx * t, y0 + dy * t, rad, color, alpha)


def cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0],
            u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1])


def draw_cable(cv, points, width, color, hi_color):
    """Smooth cable through control points (Catmull-Rom -> cubic beziers)."""
    pts = [points[0]] + list(points) + [points[-1]]
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        n = 26
        prev = p1
        for k in range(1, n + 1):
            pt = cubic(p1, c1, c2, p2, k / n)
            thick_line(cv, prev[0], prev[1], pt[0], pt[1], width, color)
            prev = pt
    # glossy highlight, offset up-left
    for i in range(len(pts) - 3):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        n = 26
        prev = (p1[0] - 3, p1[1] - 4)
        for k in range(1, n + 1):
            pt = cubic(p1, c1, c2, p2, k / n)
            pt = (pt[0] - 3, pt[1] - 4)
            thick_line(cv, prev[0], prev[1], pt[0], pt[1], max(2.0, width * 0.22), hi_color, 0.55)
            prev = pt


def box_blur_alpha(buf, w, h, radius):
    """Box blur on a float alpha buffer (separable, 2 passes)."""
    tmp = [0.0] * (w * h)
    for y in range(h):
        acc = 0.0
        for x in range(-radius, radius + 1):
            xx = min(w - 1, max(0, x))
            acc += buf[y * w + xx]
        for x in range(w):
            tmp[y * w + x] = acc / (2 * radius + 1)
            xa = min(w - 1, max(0, x - radius))
            xb = min(w - 1, max(0, x + radius + 1))
            acc += buf[y * w + xb] - buf[y * w + xa]
    out = [0.0] * (w * h)
    for x in range(w):
        acc = 0.0
        for y in range(-radius, radius + 1):
            yy = min(h - 1, max(0, y))
            acc += tmp[yy * w + x]
        for y in range(h):
            out[y * w + x] = acc / (2 * radius + 1)
            ya = min(h - 1, max(0, y - radius))
            yb = min(h - 1, max(0, y + radius + 1))
            acc += tmp[yb * w + x] - tmp[ya * w + x]
    return out


# ------------------------------------------------------------------ text ---
FONT = {
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "-": ["00000", "00000", "00000", "01110", "00000", "00000", "00000"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    " ": ["00000"] * 7,
}


def draw_text(cv, x, y, text, scale, color):
    cx = x
    for ch in text:
        glyph = FONT.get(ch)
        if glyph is None:
            cx += 6 * scale
            continue
        for row in range(7):
            for col in range(5):
                if glyph[row][col] == "1":
                    for dy in range(scale):
                        for dx in range(scale):
                            cv.set(cx + col * scale + dx, y + row * scale + dy,
                                   color[0], color[1], color[2])
        cx += 6 * scale


# ------------------------------------------------------------------- png ---
def write_png(path, cv):
    w, h = cv.w, cv.h
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # filter: None
        raw += cv.buf[y * w * 3:(y + 1) * w * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", comp) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return len(png)


# ----------------------------------------------------------------- scene ---
def render():
    cv = Canvas(W, H)

    # --- seamless studio backdrop: soft vertical gradient + centre glow
    for y in range(H):
        t = y / (H - 1)
        r = int(239 - 24 * t)
        g = int(239 - 24 * t)
        b = int(240 - 23 * t)
        for x in range(W):
            dx = (x - 512) / 700.0
            dy = (y - 430) / 700.0
            glow = max(0.0, 1 - dx * dx - dy * dy) * 9
            cv.set(x, y, min(255, r + int(glow)), min(255, g + int(glow)),
                   min(255, b + int(glow)))
    # faint horizon seam where floor meets wall
    for x in range(W):
        cv.blend(x, 782, 190, 190, 192, 0.25)

    # --- soft shadows (blurred alpha layer)
    shadow = [0.0] * (W * H)
    sh = Canvas(W, H)  # scratch canvas for shadow shapes
    fill_ellipse(sh, 445, 712, 305, 26, (0, 0, 0))
    fill_ellipse(sh, 105, 806, 85, 14, (0, 0, 0))
    fill_ellipse(sh, 445, 700, 260, 14, (0, 0, 0))
    for i in range(W * H):
        if sh.buf[i * 3]:
            shadow[i] = 1.0
    shadow = box_blur_alpha(shadow, W, H, 9)
    shadow = box_blur_alpha(shadow, W, H, 9)
    for y in range(H):
        for x in range(W):
            a = shadow[y * W + x] * 0.30
            if a > 0.003:
                cv.blend(x, y, 40, 40, 44, a)

    # --- warm light pool under the lamp
    for y in range(740, 870):
        for x in range(0, 260):
            dx = (x - 105) / 120.0
            dy = (y - 800) / 55.0
            d = dx * dx + dy * dy
            if d < 1:
                cv.blend(x, y, 255, 214, 130, (1 - d) * 0.20)

    # --- lamp cord: from lamp base along the floor into the middle socket
    draw_cable(cv, [(105, 800), (220, 812), (340, 806), (440, 786),
                    (495, 724), (508, 668)], 7, (58, 58, 62), (120, 120, 126))

    # --- THE LOOP: cord leaves the strip's right end, sweeps up and around,
    #     and plugs back into the strip's own rightmost socket.
    loop_pts = [(700, 648), (806, 700), (884, 624), (902, 480),
                (862, 344), (742, 252), (566, 228), (392, 258),
                (286, 338), (238, 452), (252, 548), (300, 596),
                (360, 606), (398, 588)]
    draw_cable(cv, loop_pts, 26, (52, 54, 58), (128, 130, 136))

    # --- power strip body (3/4-ish: top face + front face + right end)
    # top face
    fill_polygon(cv, [(172, 606), (688, 606), (706, 588), (190, 588)],
                 (246, 243, 238))
    # right end face
    fill_polygon(cv, [(688, 606), (706, 588), (706, 672), (688, 690)],
                 (206, 202, 195))
    # front face with subtle vertical gradient
    for yy in range(606, 691):
        t = (yy - 606) / 84.0
        r = int(238 - 16 * t)
        g = int(235 - 15 * t)
        b = int(229 - 14 * t)
        hline(cv, 172, 688, yy, (r, g, b))
    # rounded corners on front face
    fill_circle(cv, 172, 606, 10, (238, 235, 229))
    fill_circle(cv, 172, 690, 10, (222, 220, 215))
    # top highlight edge + bottom edge
    hline(cv, 176, 686, 607, (255, 255, 255), 0.7)
    hline(cv, 176, 686, 689, (178, 174, 168), 0.8)
    # cord-exit grommet on right end face
    fill_ellipse(cv, 697, 648, 9, 15, (70, 70, 74))
    fill_ellipse(cv, 697, 648, 5, 10, (40, 40, 44))

    # --- brand text on the strip (product text only)
    draw_text(cv, 214, 628, "LOOP-1", 2, (88, 84, 78))
    draw_text(cv, 216, 648, "SELF-POWERING", 1, (130, 126, 120))

    # --- LED (green, on) at left end
    fill_circle(cv, 196, 622, 13, (120, 220, 130), 0.35)
    fill_circle(cv, 196, 622, 8, (90, 200, 105), 0.6)
    fill_circle(cv, 196, 622, 5, (46, 196, 86))
    fill_circle(cv, 195, 621, 2, (190, 255, 205))

    # --- rocker switch
    fill_rounded_rect(cv, 306, 622, 330, 668, 4, (214, 211, 205))
    fill_rounded_rect(cv, 308, 624, 328, 644, 3, (196, 193, 187))
    fill_rounded_rect(cv, 308, 646, 328, 666, 3, (228, 225, 219))

    # --- sockets (3): dark recessed outlets with slots
    for sx in (372, 494, 616):
        fill_rounded_rect(cv, sx, 618, sx + 96, 676, 8, (58, 56, 52))
        fill_rounded_rect(cv, sx + 4, 622, sx + 92, 672, 6, (38, 37, 35))
        # two slots + ground hole
        fill_rounded_rect(cv, sx + 22, 634, sx + 30, 660, 3, (12, 12, 12))
        fill_rounded_rect(cv, sx + 66, 634, sx + 74, 660, 3, (12, 12, 12))
        fill_circle(cv, sx + 48, 650, 6, (12, 12, 12))
        # inner top highlight
        hline(cv, sx + 8, sx + 88, 623, (90, 88, 84), 0.6)

    # --- plug of the loop cord, seated in the leftmost socket
    #     (tall enough to rise above the strip's top edge, so the
    #     cable is visibly entering it)
    fill_rounded_rect(cv, 380, 570, 444, 626, 7, (242, 240, 236))
    fill_rounded_rect(cv, 384, 574, 440, 606, 5, (228, 225, 220))
    vline(cv, 394, 576, 604, (180, 177, 172), 0.8)
    vline(cv, 430, 576, 604, (180, 177, 172), 0.8)
    # plug prongs disappearing into the socket
    fill_rounded_rect(cv, 390, 622, 398, 634, 2, (160, 158, 152))
    fill_rounded_rect(cv, 422, 622, 430, 634, 2, (160, 158, 152))

    # --- lamp plug, seated in the middle socket (small, bottom edge)
    fill_rounded_rect(cv, 528, 660, 556, 682, 5, (242, 240, 236))

    # --- desk lamp (the ONE accessory): base, stem, shade, lit bulb.
    #     Kept left of the strip with the shade raised clear of it.
    # base
    fill_ellipse(cv, 105, 800, 58, 13, (66, 66, 70))
    fill_ellipse(cv, 105, 796, 58, 13, (96, 96, 100))
    fill_ellipse(cv, 105, 794, 45, 9, (120, 120, 124))
    # stem
    thick_line(cv, 105, 796, 100, 612, 9, (80, 80, 84))
    thick_line(cv, 105, 796, 100, 612, 3, (150, 150, 154), 0.7)
    # joint
    fill_circle(cv, 100, 612, 11, (70, 70, 74))
    # angled arm to shade
    thick_line(cv, 100, 612, 140, 538, 8, (80, 80, 84))
    # bulb glow halo (drawn before the shade so it does not wash it out)
    for rad, al in ((52, 0.08), (38, 0.13), (26, 0.20)):
        fill_circle(cv, 164, 576, rad, (255, 210, 110), al)
    # shade: cone, warm amber outside with a dark rim, glowing inside
    fill_polygon(cv, [(128, 528), (200, 528), (222, 584), (106, 584)],
                 (214, 158, 72))
    fill_polygon(cv, [(128, 528), (200, 528), (212, 568), (116, 568)],
                 (232, 182, 96))
    fill_polygon(cv, [(116, 568), (212, 568), (222, 584), (106, 584)],
                 (255, 226, 150))
    # shade rim outline
    thick_line(cv, 128, 528, 200, 528, 3, (146, 104, 44))
    thick_line(cv, 200, 528, 222, 584, 3, (146, 104, 44))
    thick_line(cv, 222, 584, 106, 584, 3, (146, 104, 44))
    thick_line(cv, 106, 584, 128, 528, 3, (146, 104, 44))
    # bulb
    fill_circle(cv, 164, 576, 13, (255, 226, 140))
    fill_circle(cv, 164, 576, 9, (255, 240, 180))
    fill_circle(cv, 161, 573, 4, (255, 252, 220))
    # light spill cone on the floor
    fill_polygon(cv, [(128, 584), (200, 584), (280, 800), (30, 800)],
                 (255, 220, 130), 0.10)
    return cv


def main():
    cv = render()
    os.makedirs("/output", exist_ok=True)
    size = write_png(OUT, cv)
    print(f"wrote {OUT}: {cv.w}x{cv.h}, {size} bytes")


if __name__ == "__main__":
    main()
