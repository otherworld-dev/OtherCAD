"""Generate OtherCAD's flat solid-modelling icons.

Each icon is a small isometric scene: existing material in blue, what the command
makes in orange, what it removes in red, sketches in white and datums in
yellow. Faces are shaded by which way they point, and everything has
the same dark outline, so the set reads as one family on the dark ribbon and on
the light one. A mark that is only a line (an axis, an arrow) is drawn as a filled
shape with an outline too, since a bare dark stroke disappears on the dark ribbon.

The command icons are written beside this script, where BitmapFactory finds them
ahead of the stock ones, and the fork's own face tools into PartDesign's icons.

Usage: python othercad_icons.py [NAME ...]
"""

import math
import os
import sys

OUT = "#0b1521"
SW = 3.0  # outline width in the 64 px viewBox

BLUE = {"top": "#d3e5f6", "left": "#a9c9e8", "right": "#7ea8d1"}
ORANGE = {"top": "#ffc94d", "left": "#f0a202", "right": "#c47f00"}
RED = {"top": "#ec7a80", "left": "#ca333b", "right": "#98222a"}
HOLE = {"top": "#2b4764", "left": "#5d86ad", "right": "#44698f"}
WHITE = "#f4f6f8"
DATUM = "#ffd76a"
ACCENT = "#0696d7"
AXIS_X = "#e54848"
AXIS_Y = "#4fb35a"
AXIS_Z = "#3d8fe0"

COS30 = math.cos(math.radians(30))


# -- scene items -------------------------------------------------------------


class Poly:
    """A filled polygon (or an open polyline when fill is None and closed is False)."""

    def __init__(self, pts, fill=None, stroke=OUT, width=SW, closed=True, opacity=1.0, cap="round"):
        self.pts = [tuple(p) for p in pts]
        self.fill = fill
        self.stroke = stroke
        self.width = width
        self.closed = closed
        self.opacity = opacity
        self.cap = cap

    def svg(self, tf):
        pts = [tf(p) for p in self.pts]
        d = "M " + " L ".join("%.2f,%.2f" % p for p in pts)
        if self.closed:
            d += " Z"
        style = ["fill:%s" % (self.fill or "none")]
        if self.fill and self.opacity < 1.0:
            style.append("fill-opacity:%.2f" % self.opacity)
        if self.stroke:
            style += [
                "stroke:%s" % self.stroke,
                "stroke-width:%.2f" % self.width,
                "stroke-linejoin:round",
                "stroke-linecap:%s" % self.cap,
            ]
        else:
            style.append("stroke:none")
        return '    <path d="%s" style="%s" />' % (d, ";".join(style))


def P(x, y, z=0.0):
    """Isometric projection: x runs right and down, y left and down, z up."""
    return ((x - y) * COS30, (x + y) * 0.5 - z)


def shade(pal, n):
    """Mix a palette's three tones by how much a face points up, left or right."""
    nx, ny, nz = n
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    w = [max(0.0, nz / length) ** 2, max(0.0, ny / length) ** 2, max(0.0, nx / length) ** 2]
    total = sum(w) or 1.0
    cols = [pal["top"], pal["left"], pal["right"]]
    rgb = [0.0, 0.0, 0.0]
    for weight, col in zip(w, cols):
        for i in range(3):
            rgb[i] += weight / total * int(col[1 + 2 * i : 3 + 2 * i], 16)
    return "#%02x%02x%02x" % tuple(int(round(c)) for c in rgb)


def ellipse_pts(c, r, z, t0=0.0, t1=2 * math.pi, n=48):
    """A horizontal circle in the world, as projected points."""
    out = []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        out.append(P(c[0] + r * math.cos(t), c[1] + r * math.sin(t), z))
    return out


def depth(p3):
    return p3[0] + p3[1] + p3[2]


# -- solids ------------------------------------------------------------------


def polyhedron(faces, pal, outline=True, keep_order=False):
    """faces: the faces of a convex solid, as lists of 3D points in either winding.

    Only the faces given are drawn, so a solid may leave out the ones that can never
    face the viewer. Each normal is turned away from the middle of the solid. The
    faces are drawn back to front, unless keep_order says they are given in an order
    that can be drawn as it is, which lets a caller recolour one by its index.
    """
    items = []
    visible = []
    corners = [p for f in faces for p in f]
    # The mean of the corners lies inside a convex solid even when only its near faces
    # are given, and every face's centre is on the outer side of it.
    middle = [sum(p[i] for p in corners) / len(corners) for i in range(3)]
    for f in faces:
        a, b, c = f[0], f[1], f[2]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        centre = [sum(p[i] for p in f) / len(f) for i in range(3)]
        if sum(n[i] * (centre[i] - middle[i]) for i in range(3)) < 0:
            n = (-n[0], -n[1], -n[2])
        if n[0] + n[1] + n[2] <= 1e-9:
            continue
        visible.append((depth(centre), f, n))
    if not keep_order:
        visible.sort(key=lambda t: t[0])
    for _, f, n in visible:
        items.append(Poly([P(*p) for p in f], shade(pal, n), OUT if outline else None))
    return items


def box(x, y, z, dx, dy, dz, pal):
    """The three faces a box shows, always as top, +y, +x: none of them overlaps another."""
    x1, y1, z1 = x + dx, y + dy, z + dz
    return polyhedron(
        [
            [(x, y, z1), (x, y1, z1), (x1, y1, z1), (x1, y, z1)],  # top
            [(x, y1, z), (x1, y1, z), (x1, y1, z1), (x, y1, z1)],  # +y
            [(x1, y, z), (x1, y, z1), (x1, y1, z1), (x1, y1, z)],  # +x
        ],
        pal,
        keep_order=True,
    )


def frustum_box(x, y, dx, dy, h, inset, pal, highlight=None):
    """A box whose top is inset on every side, like a drafted boss."""
    x1, y1 = x + dx, y + dy
    a, b = x + inset, y + inset
    a1, b1 = x1 - inset, y1 - inset
    faces = [
        [(a, b, h), (a, b1, h), (a1, b1, h), (a1, b, h)],
        [(x, y1, 0), (x1, y1, 0), (a1, b1, h), (a, b1, h)],
        [(x1, y, 0), (a1, b, h), (a1, b1, h), (x1, y1, 0)],
    ]
    items = polyhedron(faces, pal, keep_order=True)
    if highlight:
        items[1] = Poly(items[1].pts, shade(highlight, (0, 1, 0.4)))
    return items


def cylinder(cx, cy, z0, r, h, pal, top=True):
    """A vertical cylinder: shaded side, then its top."""
    items = []
    front = ellipse_pts((cx, cy), r, z0, math.radians(-45), math.radians(135))
    # The side's silhouette: down the left, round the front of the bottom, up the right.
    left_top = P(cx + r * math.cos(math.radians(135)), cy + r * math.sin(math.radians(135)), z0 + h)
    right_top = P(
        cx + r * math.cos(math.radians(-45)), cy + r * math.sin(math.radians(-45)), z0 + h
    )
    bottom = list(reversed(front))
    mid = len(bottom) // 2
    top_centre = P(cx, cy, z0 + h)
    items.append(
        Poly([left_top] + bottom[: mid + 1] + [(bottom[mid][0], top_centre[1])], pal["left"], None)
    )
    items.append(
        Poly([(bottom[mid][0], top_centre[1])] + bottom[mid:] + [right_top], pal["right"], None)
    )
    items.append(Poly([left_top] + bottom + [right_top], None, OUT, closed=False))
    if top:
        items.append(Poly(ellipse_pts((cx, cy), r, z0 + h), pal["top"]))
    return items


def cone(cx, cy, r, h, pal):
    apex = P(cx, cy, h)
    front = list(reversed(ellipse_pts((cx, cy), r, 0, math.radians(-45), math.radians(135))))
    mid = len(front) // 2
    items = [
        Poly([apex] + front[: mid + 1], pal["left"], None),
        Poly([apex] + front[mid:], pal["right"], None),
        Poly([apex] + front, None, OUT),
    ]
    return items


def ball(c2, rx, ry, pal):
    """A sphere or ellipsoid in screen space: a disc with a highlight."""
    cx, cy = c2
    disc = [(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in _angles(64)]
    light = [
        (cx - rx * 0.28 + rx * 0.42 * math.cos(t), cy - ry * 0.3 + ry * 0.4 * math.sin(t))
        for t in _angles(48)
    ]
    return [Poly(disc, pal["left"]), Poly(light, pal["top"], None), Poly(disc, None, OUT)]


def torus(cx, cy, R, r, pal):
    outer = ellipse_pts((cx, cy), R + r, 0, n=64)
    inner = ellipse_pts((cx, cy), R - r, 0, n=48)
    # The ring is thick, so its outline drops by the tube radius on the near side.
    body = [
        (x, y + r * 0.9 * max(0.0, math.sin(t + math.radians(45))))
        for (x, y), t in zip(outer, _angles(64))
    ]
    top_ring = outer
    hole = [(x, y + r * 0.35) for (x, y) in inner]
    return [
        Poly(body, pal["right"], None),
        Poly(top_ring, pal["left"], None),
        Poly(
            [(x, y - r * 0.15) for x, y in ellipse_pts((cx, cy), R + r * 0.35, 0, n=64)],
            pal["top"],
            None,
        ),
        Poly(body, None, OUT),
        Poly(hole, "#1b2a3a", OUT),
    ]


def prism(cx, cy, r, h, sides, pal):
    ring = [
        (
            cx + r * math.cos(2 * math.pi * i / sides + math.pi / sides),
            cy + r * math.sin(2 * math.pi * i / sides + math.pi / sides),
        )
        for i in range(sides)
    ]
    faces = [[(x, y, h) for x, y in ring]]
    for i in range(sides):
        (xa, ya), (xb, yb) = ring[i], ring[(i + 1) % sides]
        faces.append([(xa, ya, 0), (xb, yb, 0), (xb, yb, h), (xa, ya, h)])
    return polyhedron(faces, pal)


def wedge(x, y, dx, dy, h, pal):
    """A ramp, high along its x end and falling to nothing at x + dx."""
    x1, y1 = x + dx, y + dy
    faces = [
        [(x, y, h), (x, y1, h), (x1, y1, 0), (x1, y, 0)],
        [(x, y1, 0), (x1, y1, 0), (x, y1, h)],
    ]
    return polyhedron(faces, pal)


def _angles(n):
    return [2 * math.pi * i / n for i in range(n)]


# -- flat marks --------------------------------------------------------------


def plate(x, y, dx, dy, z=0.0, fill=WHITE, opacity=1.0):
    pts = [P(x, y, z), P(x, y + dy, z), P(x + dx, y + dy, z), P(x + dx, y, z)]
    return Poly(pts, fill, OUT, opacity=opacity)


def arrow(p0, p1, fill=WHITE, shaft=5.0, head=12.0, head_len=9.0):
    """A filled arrow from p0 to p1 in screen space."""
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -uy, ux
    bx, by = x1 - ux * head_len, y1 - uy * head_len
    s, hw = shaft / 2, head / 2
    pts = [
        (x0 + nx * s, y0 + ny * s),
        (bx + nx * s, by + ny * s),
        (bx + nx * hw, by + ny * hw),
        (x1, y1),
        (bx - nx * hw, by - ny * hw),
        (bx - nx * s, by - ny * s),
        (x0 - nx * s, y0 - ny * s),
    ]
    return Poly(pts, fill, OUT, width=2.5)


def curved_arrow(path, fill=WHITE, shaft=5.0, head=12.0, head_len=9.0):
    """A filled arrow along a screen-space polyline, head at the end."""
    # Trim the path so the head sits on its end.
    total = 0.0
    for i in range(len(path) - 1, 0, -1):
        seg = math.dist(path[i], path[i - 1])
        if total + seg >= head_len:
            t = (head_len - total) / seg
            end = (
                path[i][0] + (path[i - 1][0] - path[i][0]) * t,
                path[i][1] + (path[i - 1][1] - path[i][1]) * t,
            )
            body = path[:i] + [end]
            break
        total += seg
    else:
        body = path[:1]
        end = path[0]
    left, right = [], []
    s = shaft / 2
    for i, p in enumerate(body):
        a = body[max(0, i - 1)]
        b = body[min(len(body) - 1, i + 1)]
        L = math.dist(a, b) or 1.0
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        left.append((p[0] + nx * s, p[1] + ny * s))
        right.append((p[0] - nx * s, p[1] - ny * s))
    tip = path[-1]
    ux, uy = (tip[0] - end[0]) / head_len, (tip[1] - end[1]) / head_len
    nx, ny = -uy, ux
    hw = head / 2
    pts = (
        left
        + [(end[0] + nx * hw, end[1] + ny * hw), tip, (end[0] - nx * hw, end[1] - ny * hw)]
        + list(reversed(right))
    )
    return Poly(pts, fill, OUT, width=2.5)


def haloed_line(pts, colour, width=4.0, closed=False):
    return [
        Poly(pts, None, OUT, width=width + 3.5, closed=closed),
        Poly(pts, None, colour, width=width, closed=closed),
    ]


def dot(c, r, fill, width=2.5):
    return Poly(
        [(c[0] + r * math.cos(t), c[1] + r * math.sin(t)) for t in _angles(32)],
        fill,
        OUT,
        width=width,
    )


# -- icons -------------------------------------------------------------------


def pencil(tip, length=30.0, width=9.0, angle=-45.0):
    a = math.radians(angle)
    ux, uy = math.cos(a), math.sin(a)
    nx, ny = -uy, ux
    tx, ty = tip
    cone_len = 9.0
    bx, by = tx + ux * cone_len, ty + uy * cone_len
    ex, ey = tx + ux * length, ty + uy * length
    hw = width / 2
    wood = [(tx, ty), (bx + nx * hw, by + ny * hw), (bx - nx * hw, by - ny * hw)]
    lead_len = 3.5
    lead = [
        (tx, ty),
        (
            tx + ux * lead_len + nx * hw * lead_len / cone_len,
            ty + uy * lead_len + ny * hw * lead_len / cone_len,
        ),
        (
            tx + ux * lead_len - nx * hw * lead_len / cone_len,
            ty + uy * lead_len - ny * hw * lead_len / cone_len,
        ),
    ]
    body = [
        (bx + nx * hw, by + ny * hw),
        (ex + nx * hw, ey + ny * hw),
        (ex - nx * hw, ey - ny * hw),
        (bx - nx * hw, by - ny * hw),
    ]
    return [Poly(body, ORANGE["left"]), Poly(wood, "#f3d9a4"), Poly(lead, OUT, OUT, width=1.5)]


def icon_sketch(with_pencil):
    items = [plate(0, 0, 40, 40)]
    items.append(Poly(ellipse_pts((20, 20), 11, 0), None, ACCENT, width=3.5))
    if with_pencil:
        items += pencil(P(26, 26), length=34, width=10, angle=-40)
    return items


def icon_body():
    return box(0, 0, 0, 30, 30, 24, BLUE)


def icon_extrude():
    items = [plate(-6, -6, 36, 36)]
    items += box(0, 0, 0, 24, 24, 18, ORANGE)
    c = P(12, 12, 18)
    items.append(arrow((c[0], c[1] - 2), (c[0], c[1] - 20)))
    return items


def pocketed(pal_outer, pal_inner, x, y, dx, dy, h, inset, depth_, rim=None):
    """A box with a rectangular recess in its top."""
    items = box(x, y, 0, dx, dy, h, pal_outer)
    if rim:
        items[0] = Poly(items[0].pts, rim["top"])
    a, b = x + inset, y + inset
    a1, b1 = x + dx - inset, y + dy - inset
    zf = h - depth_
    items.append(Poly([P(a, b, h), P(a, b1, h), P(a1, b1, h), P(a1, b, h)], pal_inner["top"]))
    # The two far walls of the recess face the viewer.
    items.append(Poly([P(a, b, zf), P(a, b1, zf), P(a, b1, h), P(a, b, h)], pal_inner["right"]))
    items.append(Poly([P(a, b, zf), P(a, b, h), P(a1, b, h), P(a1, b, zf)], pal_inner["left"]))
    return items


def icon_pocket():
    return pocketed(BLUE, RED, 0, 0, 34, 34, 18, 8, 10)


def icon_shell():
    return pocketed(BLUE, BLUE, 0, 0, 34, 34, 22, 4.5, 17, rim=ORANGE)


def axis_line(x, y, z0, z1):
    return haloed_line([P(x, y, z0), P(x, y, z1)], WHITE, width=2.5)


def icon_revolve():
    # The axis stands to the left of the solid, so it reads as revolving about it.
    items = haloed_line([P(-6, 22, -2), P(-6, 22, 34)], WHITE, width=2.5)
    items += cylinder(10, 10, 0, 13, 20, ORANGE)
    arc = ellipse_pts((10, 10), 19, 26, math.radians(200), math.radians(40), n=30)
    items.append(curved_arrow(arc, shaft=4.5, head=11, head_len=8))
    return items


def icon_groove():
    items = cylinder(0, 0, 0, 15, 30, BLUE)
    band = ellipse_pts((0, 0), 15, 11, math.radians(-45), math.radians(135), n=40)
    band2 = ellipse_pts((0, 0), 15, 19, math.radians(-45), math.radians(135), n=40)
    items.insert(3, Poly(band + list(reversed(band2)), RED["left"], OUT))
    items += axis_line(0, 0, 30, 42)
    return items


def icon_sweep():
    path = [
        (10 + 26 * (1 - math.cos(t)), 54 - 34 * math.sin(t))
        for t in [math.pi / 2 * i / 30 for i in range(31)]
    ]
    tube = []
    left, right = [], []
    for i, p in enumerate(path):
        a = path[max(0, i - 1)]
        b = path[min(len(path) - 1, i + 1)]
        L = math.dist(a, b)
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        left.append((p[0] + nx * 7, p[1] + ny * 7))
        right.append((p[0] - nx * 7, p[1] - ny * 7))
    tube.append(Poly(left + list(reversed(right)), ORANGE["left"]))
    end = path[-1]
    tube.append(
        Poly(
            [(end[0] + 4 * math.cos(t), end[1] + 7 * math.sin(t)) for t in _angles(32)],
            ORANGE["top"],
            OUT,
            width=2.5,
        )
    )
    start = path[0]
    tube.insert(
        0,
        Poly(
            [(start[0] + 11 * math.cos(t), start[1] + 5 * math.sin(t)) for t in _angles(32)],
            WHITE,
            OUT,
            width=2.5,
        ),
    )
    return tube


def icon_loft():
    items = [plate(0, 0, 36, 36)]
    base = [P(5, 5, 0), P(5, 31, 0), P(31, 31, 0), P(31, 5, 0)]
    top = ellipse_pts((18, 18), 9, 30, n=48)
    items.append(Poly(_hull(base + top), ORANGE["left"]))
    items.append(Poly(top, ORANGE["top"]))
    return items


def _hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def icon_hole():
    items = box(0, 0, 0, 36, 36, 20, BLUE)
    items.append(Poly(ellipse_pts((18, 18), 12, 20), ORANGE["top"]))
    opening = ellipse_pts((18, 18), 7.5, 20)
    items.append(Poly(opening, HOLE["top"]))
    back = ellipse_pts((18, 18), 7.5, 20, math.radians(135), math.radians(315), n=24)
    items.append(Poly(back + [(x, y + 6) for x, y in reversed(back)], HOLE["left"], None))
    items.append(Poly(opening, None, OUT))
    return items


def icon_coil():
    r, pitch, turns = 15, 11, 2.6
    n = 180
    pts = []
    for i in range(n + 1):
        t = 2 * math.pi * turns * i / n
        x, y, z = r * math.cos(t), r * math.sin(t), pitch * t / (2 * math.pi)
        pts.append(((x, y, z), P(x, y, z)))
    back, front = [], []
    run, is_front = [], None
    for p3, p2 in pts:
        f = p3[0] + p3[1] > 0
        if is_front is None or f == is_front:
            run.append(p2)
        else:
            run.append(p2)
            (front if is_front else back).append(run)
            run = [p2]
        is_front = f
    (front if is_front else back).append(run)
    items = []
    for seg in back:
        items += haloed_line(seg, ORANGE["right"], width=5.5)
    for seg in front:
        items += haloed_line(seg, ORANGE["left"], width=5.5)
    return items


def icon_primitive(kind, pal):
    if kind == "Box":
        return box(0, 0, 0, 28, 28, 24, pal)
    if kind == "Cylinder":
        return cylinder(0, 0, 0, 15, 28, pal)
    if kind == "Sphere":
        return ball((0, 0), 20, 20, pal)
    if kind == "Ellipsoid":
        return ball((0, 0), 24, 15, pal)
    if kind == "Cone":
        return cone(0, 0, 17, 36, pal)
    if kind == "Torus":
        return torus(0, 0, 13, 7, pal)
    if kind == "Prism":
        return prism(0, 0, 16, 22, 6, pal)
    if kind == "Wedge":
        return wedge(0, 0, 34, 26, 26, pal)
    raise KeyError(kind)


def cubes(positions, size, originals=(0,)):
    """Cubes at the given corners, drawn back to front; the originals in orange."""
    order = sorted(range(len(positions)), key=lambda i: depth(positions[i]))
    items = []
    for i in order:
        x, y, z = positions[i]
        items += box(x, y, z, size, size, size, ORANGE if i in originals else BLUE)
    return items


def icon_linear_pattern():
    s = 13
    items = cubes([(0, 0, 0), (19, 0, 0), (38, 0, 0)], s)
    a, b = P(8, 26, 0), P(52, 26, 0)
    items.append(arrow(a, b, shaft=4.5, head=11, head_len=8))
    return items


def icon_polar_pattern():
    s, R = 10, 21
    pos = []
    for i in range(6):
        t = math.radians(45 + 60 * i)
        pos.append((R * math.cos(t) - s / 2, R * math.sin(t) - s / 2, 0))
    items = [Poly(ellipse_pts((0, 0), R, 0, n=64), None, WHITE, width=2.0)]
    items.append(dot(P(0, 0, 0), 3.5, WHITE, width=2.0))
    return items + cubes(pos, s, originals=(0,))


def icon_multi_transform():
    s = 14
    return cubes([(0, 0, 0), (20, 0, 0), (0, 20, 0), (20, 20, 0)], s)


def icon_mirror():
    """The mirror plane is x = y, which the isometric view shows edge on, as a
    vertical line: the halves sit either side of it at the same depth, and swapping x
    and y mirrors one into the other exactly."""
    items = haloed_line([P(0, 0, -4), P(0, 0, 28)], DATUM, width=3.0)
    # The original: a low block with a tower at the end nearest the plane.
    parts = [(0, 22, 0, 12, 20, 10), (0, 22, 10, 12, 8, 14)]
    for x, y, z, dx, dy, dz in parts:
        items += box(x, y, z, dx, dy, dz, BLUE)
    for x, y, z, dx, dy, dz in parts:
        items += box(y, x, z, dy, dx, dz, ORANGE)
    return items


def icon_edge(rounded):
    """A block whose near vertical edge is rounded or cut; the new face is orange."""
    a, b, h, r = 34, 34, 22, 15
    if rounded:
        corner = [
            (a - r + r * math.sin(t), b - r + r * math.cos(t))
            for t in [math.pi / 2 * i / 14 for i in range(15)]
        ]
    else:
        corner = [(a - r, b), (a, b - r)]
    top = [P(0, 0, h), P(0, b, h)] + [P(x, y, h) for x, y in corner] + [P(a, 0, h)]
    items = [
        Poly([P(0, b, 0), P(a - r, b, 0), P(a - r, b, h), P(0, b, h)], BLUE["left"]),
        Poly([P(a, 0, 0), P(a, b - r, 0), P(a, b - r, h), P(a, 0, h)], BLUE["right"]),
    ]
    if rounded:
        # The round, split where it turns from facing left to facing right.
        half = len(corner) // 2
        for part, pal_key in ((corner[: half + 1], "left"), (corner[half:], "right")):
            face = [P(x, y, 0) for x, y in part] + [P(x, y, h) for x, y in reversed(part)]
            items.append(Poly(face, ORANGE[pal_key], None))
        items.append(
            Poly(
                [P(x, y, 0) for x, y in corner]
                + [P(corner[-1][0], corner[-1][1], h)]
                + [P(x, y, h) for x, y in reversed(corner)]
                + [P(corner[0][0], corner[0][1], 0)],
                None,
                OUT,
            )
        )
    else:
        items.append(
            Poly(
                [P(a - r, b, 0), P(a, b - r, 0), P(a, b - r, h), P(a - r, b, h)],
                shade(ORANGE, (1, 1, 0)),
            )
        )
    items.append(Poly(top, BLUE["top"]))
    return items


def icon_draft():
    return frustum_box(0, 0, 34, 34, 22, 7, BLUE, highlight=ORANGE)


def icon_combine():
    items = box(-4, -4, 0, 26, 26, 18, BLUE)
    items += cylinder(24, 18, 0, 11, 26, ORANGE)
    return items


def icon_plane():
    return [plate(0, 0, 40, 40, fill=DATUM)]


def icon_axis():
    items = [plate(0, 0, 34, 34, fill=WHITE)]
    items += haloed_line([P(17, 17, -6), P(17, 17, 34)], DATUM, width=5)
    return items


def icon_point():
    items = [plate(0, 0, 34, 34, fill=WHITE)]
    items.append(dot(P(17, 17, 0), 7, DATUM, width=3))
    return items


def icon_csys():
    o = (0, 0)
    return [
        arrow(o, (P(26, 0, 0)), fill=AXIS_X, shaft=5, head=12, head_len=10),
        arrow(o, (P(0, 26, 0)), fill=AXIS_Y, shaft=5, head=12, head_len=10),
        arrow(o, (P(0, 0, 28)), fill=AXIS_Z, shaft=5, head=12, head_len=10),
        dot(o, 4.5, WHITE),
    ]


def icon_press_pull():
    items = box(0, 0, 0, 34, 30, 20, BLUE)
    items[0] = Poly(items[0].pts, ORANGE["top"])
    c = P(17, 15, 20)
    items.append(arrow((c[0], c[1] - 1), (c[0], c[1] - 20), shaft=4.5, head=11, head_len=8))
    items.append(arrow((c[0], c[1] - 10), (c[0], c[1] + 8), shaft=4.5, head=11, head_len=8))
    return items


def icon_offset_face():
    items = box(0, 0, 0, 34, 30, 16, BLUE)
    items.append(Poly([P(0, 0, 30), P(0, 30, 30), P(34, 30, 30), P(34, 0, 30)], ORANGE["top"]))
    c = P(17, 15, 16)
    items.insert(3, arrow((c[0], c[1] + 2), (c[0], c[1] - 13), shaft=4.5, head=11, head_len=7))
    return items


def icon_move_face():
    items = box(0, 0, 0, 22, 30, 24, BLUE)
    face = [P(40, 0, 0), P(40, 0, 24), P(40, 30, 24), P(40, 30, 0)]
    items.append(Poly(face, ORANGE["right"]))
    items.append(arrow(P(21, 30, 12), P(37, 30, 12), shaft=4.5, head=11, head_len=8))
    return items


def icon_delete_face():
    items = box(0, 0, 0, 34, 30, 22, BLUE)
    items[1] = Poly(items[1].pts, RED["left"])
    c = P(17, 30, 11)
    k = 7
    items += haloed_line([(c[0] - k, c[1] - k), (c[0] + k, c[1] + k)], WHITE, width=4)
    items += haloed_line([(c[0] - k, c[1] + k), (c[0] + k, c[1] - k)], WHITE, width=4)
    return items


def icon_assembly():
    return box(0, 0, 0, 22, 22, 16, BLUE) + box(22, 4, 0, 14, 14, 28, ORANGE)


def icon_insert_component():
    items = box(0, 0, 0, 28, 28, 22, BLUE)
    c = P(34, 22, 0)
    items.append(dot(c, 13, ORANGE["left"], width=2.5))
    items += haloed_line([(c[0] - 7, c[1]), (c[0] + 7, c[1])], WHITE, width=4)
    items += haloed_line([(c[0], c[1] - 7), (c[0], c[1] + 7)], WHITE, width=4)
    return items


def icon_joint():
    items = box(0, 0, 0, 30, 30, 12, BLUE)
    items += box(8, 8, 12, 14, 14, 16, BLUE)
    # The joint, where the near corner of the upper part meets the lower one.
    items.append(dot(P(22, 22, 12), 6.5, ORANGE["left"], width=2.5))
    return items


def icon_ground():
    items = [plate(-8, -8, 44, 44)]
    items += box(0, 0, 0, 28, 28, 18, BLUE)
    top = P(14, 14, 18)
    items += haloed_line([top, (top[0], top[1] - 14)], WHITE, width=2.5)
    items.append(dot((top[0], top[1] - 16), 5.5, ORANGE["left"], width=2.5))
    return items


def icon_measure():
    items = box(0, 0, 0, 48, 18, 5, ORANGE)
    for i, x in enumerate(range(4, 48, 5)):
        reach = 6 if i % 2 == 0 else 3.5
        items.append(Poly([P(x, 0, 5), P(x, reach * 1.4, 5)], None, OUT, width=2.0, closed=False))
    return items


def icon_section_cut():
    a, b, h = 34, 15, 26
    items = box(0, 0, 0, a, b, h, BLUE)
    items[1] = Poly(items[1].pts, ORANGE["left"])
    # Section hatching across the cut face, clipped to it.
    for c in range(-h + 6, a, 8):
        x0, z0 = (c, 0) if c >= 0 else (0, -c)
        x1, z1 = (c + h, h) if c + h <= a else (a, a - c)
        items.append(Poly([P(x0, b, z0), P(x1, b, z1)], None, OUT, width=2.0, closed=False))
    return items


def icon_canvas():
    items = [plate(0, 0, 40, 40)]
    mountain = [P(6, 34, 0), P(30, 34, 0), P(18, 22, 0)]
    items.append(Poly([(x, y) for x, y in mountain], BLUE["right"], OUT, width=2.5))
    items.append(dot(P(12, 12, 0), 5, ORANGE["left"], width=2.5))
    return items


def icon_import():
    items = box(0, 0, 0, 30, 30, 20, BLUE)
    c = P(15, 15, 20)
    items.append(arrow((c[0] - 24, c[1] - 26), (c[0], c[1] - 1)))
    return items


# name -> (description, builder)
ICONS = {
    "Sketcher_NewSketch": ("A pencil over a sketch plane", lambda: icon_sketch(True)),
    "Sketcher_Sketch": ("A sketch plane with a profile on it", lambda: icon_sketch(False)),
    "PartDesign_Body": ("A plain solid body", icon_body),
    "PartDesign_Pad": ("A profile extruded into new material", icon_extrude),
    "PartDesign_Pocket": ("A recess cut into a solid", icon_pocket),
    "PartDesign_Revolution": ("New material revolved about an axis", icon_revolve),
    "PartDesign_Groove": ("A groove revolved into a solid about its axis", icon_groove),
    "PartDesign_AdditivePipe": ("A profile swept along a path", icon_sweep),
    "PartDesign_AdditiveLoft": ("New material lofted between two profiles", icon_loft),
    "PartDesign_Hole": ("A hole drilled into a solid", icon_hole),
    "PartDesign_AdditiveHelix": ("A coil", icon_coil),
    "PartDesign_LinearPattern": ("A feature repeated in a row", icon_linear_pattern),
    "PartDesign_PolarPattern": ("A feature repeated around an axis", icon_polar_pattern),
    "PartDesign_MultiTransform": ("A feature repeated by several transforms", icon_multi_transform),
    "PartDesign_Mirrored": ("A feature mirrored across a plane", icon_mirror),
    "PartDesign_Fillet": ("A rounded edge", lambda: icon_edge(True)),
    "PartDesign_Chamfer": ("A bevelled edge", lambda: icon_edge(False)),
    "PartDesign_Thickness": ("A solid hollowed into a shell", icon_shell),
    "PartDesign_Draft": ("A face tilted by a draft angle", icon_draft),
    "PartDesign_Boolean": ("Two bodies combined", icon_combine),
    "PartDesign_Plane": ("A datum plane", icon_plane),
    "PartDesign_Line": ("A datum axis", icon_axis),
    "PartDesign_Point": ("A datum point", icon_point),
    "PartDesign_CoordinateSystem": ("A coordinate system", icon_csys),
    # The rest of the SOLID tab: ASSEMBLE, INSPECT and INSERT.
    "Geoassembly": ("Two parts put together", icon_assembly),
    "Assembly_InsertLink": ("A part added to the assembly", icon_insert_component),
    "Assembly_CreateJointFixed": ("Two parts held together by a joint", icon_joint),
    "Assembly_ToggleGrounded": ("A part pinned in place", icon_ground),
    "umf-measurement": ("A ruler", icon_measure),
    "Part_SectionCut": ("A solid cut open along a section", icon_section_cut),
    "image-plane": ("A picture on a canvas", icon_canvas),
    "Std_Import": ("A file brought into the model", icon_import),
}
for _kind in ("Box", "Cylinder", "Sphere", "Ellipsoid", "Cone", "Torus", "Prism", "Wedge"):
    ICONS["PartDesign_Additive" + _kind] = (
        "An additive %s primitive" % _kind.lower(),
        (lambda k: lambda: icon_primitive(k, ORANGE))(_kind),
    )
    ICONS["PartDesign_Subtractive" + _kind] = (
        "A subtractive %s primitive" % _kind.lower(),
        (lambda k: lambda: icon_primitive(k, RED))(_kind),
    )

# The fork's own face tools, redrawn in the same style. These live beside the other
# PartDesign icons rather than in the override set.
FACE_TOOLS = {
    "PartDesign_PressPull": (
        "A face that can be pushed either way, for the adaptive press and pull tool",
        icon_press_pull,
    ),
    "PartDesign_OffsetFace": ("A face offset from its solid", icon_offset_face),
    "PartDesign_MoveFace": ("A face moved away from its solid", icon_move_face),
    "PartDesign_DeleteFace": ("A face deleted from a solid", icon_delete_face),
}


# -- output ------------------------------------------------------------------

HEADER = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
   width="64px"
   height="64px"
   viewBox="0 0 64 64"
   version="1.1"
   id="{name}"
   xmlns="http://www.w3.org/2000/svg"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:cc="http://creativecommons.org/ns#"
   xmlns:dc="http://purl.org/dc/elements/1.1/">
  <metadata id="metadata1">
    <rdf:RDF>
      <cc:Work rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type rdf:resource="http://purl.org/dc/dcmitype/StillImage" />
        <dc:title>{name}</dc:title>
        <dc:description>{desc}</dc:description>
        <dc:publisher>
          <cc:Agent>
            <dc:title>OtherCAD</dc:title>
          </cc:Agent>
        </dc:publisher>
        <dc:rights>
          <cc:Agent>
            <dc:title>FreeCAD LGPL2+</dc:title>
          </cc:Agent>
        </dc:rights>
        <cc:license>https://www.gnu.org/copyleft/lesser.html</cc:license>
      </cc:Work>
    </rdf:RDF>
  </metadata>
  <g id="layer1">
"""

MARGIN = 3.0


def render(name, desc, items):
    xs = [p[0] for it in items for p in it.pts]
    ys = [p[1] for it in items for p in it.pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    room = 64 - 2 * MARGIN - SW
    scale = min(room / (x1 - x0), room / (y1 - y0))
    ox = 32 - (x0 + x1) / 2 * scale
    oy = 32 - (y0 + y1) / 2 * scale

    def tf(p):
        return (ox + p[0] * scale, oy + p[1] * scale)

    body = "\n".join(it.svg(tf) for it in items)
    return HEADER.format(name=name, desc=desc) + body + "\n  </g>\n</svg>\n"


HERE = os.path.dirname(os.path.abspath(__file__))
FACE_TOOLS_DIR = os.path.join(
    HERE, "..", "..", "..", "Mod", "PartDesign", "Gui", "Resources", "icons"
)


def main():
    wanted = set(sys.argv[1:])
    for table, out in ((ICONS, HERE), (FACE_TOOLS, FACE_TOOLS_DIR)):
        for name, (desc, build) in table.items():
            if wanted and name not in wanted:
                continue
            path = os.path.normpath(os.path.join(out, name + ".svg"))
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(render(name, desc, build()))
            print(path)


if __name__ == "__main__":
    main()
