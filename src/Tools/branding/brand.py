# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2026 FuCad contributors

"""Single source of truth for the OtherCAD visual identity.

The palette and the geometry of the OtherCAD icon are defined here once and are
consumed by ``generate_brand_assets.py`` to emit every logo, icon, splash and
packaging graphic in the repository. Nothing else should hard-code brand
colours or redraw the icon.

OtherCAD belongs to Otherworld Dev's Other family, so it follows the family
brand sheet: a night tile, the teal portal ring every family icon shares, and
one paper-white glyph inside it with at most one small glow accent. The
OtherCAD glyph is an isometric cube drawn as a line sketch, with a glow profile
sketched on its top face: the sketch-then-pad step every parametric model
starts with. The wordmark sets "Other" in a light weight and "CAD" in bold teal.
"""

import math
import struct
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Palette: the Other family brand sheet
# --------------------------------------------------------------------------

NIGHT = (10, 15, 22)  # #0A0F16, backgrounds and the dark end of the tile
NIGHT_LIT = (18, 32, 43)  # #12202B, the lit centre of the tile
INK = (10, 17, 24)  # #0A1118, text on light surfaces
TEAL = (34, 211, 196)  # #22D3C4, the portal ring and the wordmark suffix
GLOW = (94, 234, 212)  # #5EEAD4, the single accent inside a glyph
MINT = (155, 232, 222)  # #9BE8DE
PAPER = (242, 239, 230)  # #F2EFE6, glyphs and text on dark surfaces
DEEP_TEAL = (13, 148, 136)  # #0D9488, teal on light backgrounds
MUTED = (138, 151, 163)  # #8A97A3, secondary text

TAGLINE = "PARAMETRIC 3D MODELING"


def hex_of(rgb):
    """Return the ``#rrggbb`` form of an RGB tuple."""
    return "#{:02x}{:02x}{:02x}".format(*rgb[:3])


def rgba(rgb, alpha=255):
    """Return an RGBA tuple for an RGB colour and an 0-255 alpha."""
    return (rgb[0], rgb[1], rgb[2], alpha)


# --------------------------------------------------------------------------
# Icon geometry, in the family's 512 unit tile
# --------------------------------------------------------------------------

TILE = 512.0
TILE_RADIUS = 112.0

# The tile's radial gradient runs from NIGHT_LIT at this point out to NIGHT.
TILE_GLOW_CENTRE = (256.0, 0.42 * TILE)
TILE_GLOW_RADIUS = 0.65 * TILE

# The portal ring, the same on every family icon, and its soft glow.
RING_CENTRE = (256.0, 256.0)
RING_RADIUS = 178.0
RING_WIDTH = 20.0
RING_GLOW_WIDTH = 44.0
RING_GLOW_OPACITY = 0.14

# The cube glyph: a pointy-topped hexagon with the three edges that meet at the
# near top corner. It stays inside the brand sheet's 120 unit glyph circle.
GLYPH_WIDTH = 24.0
_CUBE_R = 104.0
_CUBE_X = _CUBE_R * math.cos(math.radians(30.0))
_CUBE_Y = _CUBE_R * math.sin(math.radians(30.0))
CUBE_TOP = (256.0, 256.0 - _CUBE_R)
CUBE_CENTRE = (256.0, 256.0)
CUBE_OUTLINE = [
    CUBE_TOP,
    (256.0 + _CUBE_X, 256.0 - _CUBE_Y),
    (256.0 + _CUBE_X, 256.0 + _CUBE_Y),
    (256.0, 256.0 + _CUBE_R),
    (256.0 - _CUBE_X, 256.0 + _CUBE_Y),
    (256.0 - _CUBE_X, 256.0 - _CUBE_Y),
]
CUBE_EDGES = [
    [CUBE_OUTLINE[5], CUBE_CENTRE, CUBE_OUTLINE[1]],
    [CUBE_CENTRE, CUBE_OUTLINE[3]],
]


def _top_face_profile(scale=0.5):
    """The glow accent: the top face, shrunk about its own centre."""
    face = [CUBE_TOP, CUBE_OUTLINE[1], CUBE_CENTRE, CUBE_OUTLINE[5]]
    cx = sum(x for x, _ in face) / 4.0
    cy = sum(y for _, y in face) / 4.0
    return [(cx + (x - cx) * scale, cy + (y - cy) * scale) for x, y in face]


CUBE_PROFILE = _top_face_profile()


def glyph_primitives(line, accent, ring=None, ring_glow=None):
    """Return the drawing primitives of the icon, without its tile.

    Each primitive is ``("ring", centre, radius, width, colour)``,
    ``("path", points, width, colour, closed)`` or ``("fill", points, colour)``,
    in the 512 unit tile space, back to front. The ring is left out when no
    colour is given for it.
    """
    shapes = []
    if ring_glow is not None:
        shapes.append(("ring", RING_CENTRE, RING_RADIUS, RING_GLOW_WIDTH, ring_glow))
    if ring is not None:
        shapes.append(("ring", RING_CENTRE, RING_RADIUS, RING_WIDTH, ring))
    shapes.append(("path", CUBE_OUTLINE, GLYPH_WIDTH, line, True))
    for edge in CUBE_EDGES:
        shapes.append(("path", edge, GLYPH_WIDTH, line, False))
    shapes.append(("fill", CUBE_PROFILE, accent))
    return shapes


def icon_primitives():
    """The full-colour glyph and ring as they sit on the night tile."""
    glow_alpha = round(255 * RING_GLOW_OPACITY)
    return glyph_primitives(
        rgba(PAPER), rgba(GLOW), ring=rgba(TEAL), ring_glow=rgba(TEAL, glow_alpha)
    )


def render_primitives(size, shapes, box=None, supersample=None):
    """Draw primitives into a transparent RGBA image of ``size``.

    ``box`` is ``(x, y, side)``: where the 512 unit tile lands, in pixels. By
    default the tile fills a square image.
    """
    width, height = size
    if box is None:
        box = (0.0, 0.0, float(min(width, height)))
    if supersample is None:
        supersample = 8 if box[2] < 96 else SUPERSAMPLE
    x0, y0, side = box
    scale = side / TILE * supersample

    def place(point):
        return (x0 * supersample + point[0] * scale, y0 * supersample + point[1] * scale)

    canvas = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
    for shape in shapes:
        # Each shape gets its own layer so translucent colours composite over
        # what is underneath instead of replacing it.
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        kind = shape[0]
        if kind == "ring":
            _, centre, radius, stroke, colour = shape
            cx, cy = place(centre)
            outer = (radius + stroke / 2.0) * scale
            draw.ellipse(
                (cx - outer, cy - outer, cx + outer, cy + outer),
                outline=colour,
                width=max(1, round(stroke * scale)),
            )
        elif kind == "path":
            _, points, stroke, colour, closed = shape
            placed = [place(point) for point in points]
            if closed:
                placed = placed + placed[:2]
            pixels = max(1, round(stroke * scale))
            draw.line(placed, fill=colour, width=pixels, joint="curve")
            cap = pixels / 2.0
            for px, py in placed:
                draw.ellipse((px - cap, py - cap, px + cap, py + cap), fill=colour)
        else:
            _, points, colour = shape
            draw.polygon([place(point) for point in points], fill=colour)
        canvas.alpha_composite(layer)
    return canvas.resize((width, height), Image.LANCZOS)


def svg_primitives(shapes, indent="  "):
    """Return SVG elements for drawing primitives, in tile units."""
    lines = []
    for shape in shapes:
        kind = shape[0]
        if kind == "ring":
            _, (cx, cy), radius, stroke, colour = shape
            lines.append(
                f'{indent}<circle cx="{cx:g}" cy="{cy:g}" r="{radius:g}" fill="none" '
                f'{svg_stroke(colour)} stroke-width="{stroke:g}"/>'
            )
        elif kind == "path":
            _, points, stroke, colour, closed = shape
            data = " ".join(
                ("M" if index == 0 else "L") + f"{x:.1f} {y:.1f}"
                for index, (x, y) in enumerate(points)
            )
            if closed:
                data += " Z"
            lines.append(
                f'{indent}<path d="{data}" fill="none" {svg_stroke(colour)} '
                f'stroke-width="{stroke:g}" stroke-linecap="round" stroke-linejoin="round"/>'
            )
        else:
            _, points, colour = shape
            lines.append(f'{indent}<path d="{svg_path(points)}" {svg_fill(colour)}/>')
    return "\n".join(lines)


def tile_background(size):
    """Return the night tile: a radial gradient inside a rounded square."""
    ys, xs = np.mgrid[0:size, 0:size].astype(np.float32) + 0.5
    unit = size / TILE
    distance = np.hypot(xs - TILE_GLOW_CENTRE[0] * unit, ys - TILE_GLOW_CENTRE[1] * unit)
    ramp = np.clip(distance / (TILE_GLOW_RADIUS * unit), 0.0, 1.0)[:, :, None]
    colours = np.array(NIGHT_LIT, np.float32) * (1.0 - ramp) + np.array(NIGHT, np.float32) * ramp
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(
        Image.fromarray(colours.astype(np.uint8), "RGB"),
        (0, 0),
        rounded_rect_mask((size, size), size * TILE_RADIUS / TILE),
    )
    return tile


def app_icon(size):
    """The OtherCAD application icon, rendered at ``size`` pixels square."""
    canvas = tile_background(size)
    canvas.alpha_composite(render_primitives((size, size), icon_primitives()))
    return canvas


# --------------------------------------------------------------------------
# Raster helpers
# --------------------------------------------------------------------------

SUPERSAMPLE = 4


def render_polygons(size, shapes, supersample=SUPERSAMPLE):
    """Draw flat coloured polygons into a transparent RGBA image."""
    width, height = size
    canvas = Image.new("RGBA", (width * supersample, height * supersample), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    for points, colour in shapes:
        draw.polygon(
            [(px * supersample, py * supersample) for px, py in points],
            fill=colour,
        )
    return canvas.resize((width, height), Image.LANCZOS)


def rounded_rect_mask(size, radius, supersample=SUPERSAMPLE):
    """Return an 8-bit mask holding an antialiased rounded rectangle."""
    width, height = size
    mask = Image.new("L", (width * supersample, height * supersample), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * supersample - 1, height * supersample - 1),
        radius=radius * supersample,
        fill=255,
    )
    return mask.resize((width, height), Image.LANCZOS)


def linear_gradient(size, start, end, angle=45.0):
    """Return an RGB image holding a linear gradient at ``angle`` degrees."""
    width, height = size
    radians = np.deg2rad(angle)
    xs = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ys = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    ramp = xs * np.cos(radians) + ys * np.sin(radians)
    span = ramp.max() - ramp.min()
    ramp = (ramp - ramp.min()) / (span if span else 1.0)
    ramp = ramp[:, :, None]
    colours = (
        np.array(start, dtype=np.float32) * (1.0 - ramp) + np.array(end, dtype=np.float32) * ramp
    )
    return Image.fromarray(colours.astype(np.uint8), "RGB")


def radial_glow(size, centre, radius, colour, strength):
    """Return an RGBA image holding a soft radial glow used for atmosphere."""
    width, height = size
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)
    distance = np.hypot(xs - centre[0], ys - centre[1]) / float(radius)
    falloff = np.clip(1.0 - distance, 0.0, 1.0) ** 2
    layer = np.zeros((height, width, 4), dtype=np.float32)
    layer[:, :, 0] = colour[0]
    layer[:, :, 1] = colour[1]
    layer[:, :, 2] = colour[2]
    layer[:, :, 3] = falloff * strength
    return Image.fromarray(layer.astype(np.uint8), "RGBA")


ISO_SLOPE = 0.57735  # tan(30 degrees)


def isometric_grid(size, spacing, colour, alpha, supersample=2):
    """Return an RGBA layer of faint construction lines at +/-30 degrees."""
    width, height = size
    big_width, big_height = width * supersample, height * supersample
    layer = Image.new("RGBA", (big_width, big_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    run = big_height / ISO_SLOPE  # horizontal travel over the full height
    step = spacing * supersample / ISO_SLOPE
    for run_sign in (1.0, -1.0):
        start = -run if run_sign > 0 else 0.0
        while start < big_width + run:
            draw.line(
                [(start, 0), (start + run_sign * run, big_height)],
                fill=rgba(colour, alpha),
                width=supersample,
            )
            start += step
    return layer.resize((width, height), Image.LANCZOS)


# --------------------------------------------------------------------------
# Type
# --------------------------------------------------------------------------

_FONT_CANDIDATES = (
    ("C:/Windows/Fonts/bahnschrift.ttf", True),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", False),
    ("/System/Library/Fonts/Supplemental/Futura.ttc", False),
    ("C:/Windows/Fonts/segoeui.ttf", False),
)


def load_font(pixels, weight="Regular"):
    """Load the brand typeface at ``pixels`` em size.

    Bahnschrift is a DIN derivative and carries the technical-drawing feel the
    product is after, and its weight axis gives the wordmark its light and bold
    halves; the other candidates are fallbacks for machines that do not have it
    so the generator still runs.
    """
    for path, variable in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        font = ImageFont.truetype(path, pixels)
        if variable:
            try:
                font.set_variation_by_name(weight)
            except OSError:
                pass
        return font
    raise RuntimeError("no usable font found for the OtherCAD wordmark")


def tracked_width(font, text, tracking):
    """Return the advance width of ``text`` including letter tracking."""
    total = 0.0
    for character in text:
        total += font.getlength(character) + tracking
    return total - tracking if text else 0.0


def draw_tracked(draw, position, text, font, fill, tracking=0.0, anchor="ls"):
    """Draw ``text`` with manual letter tracking and return its advance width."""
    x, y = position
    if anchor.startswith("m"):
        x -= tracked_width(font, text, tracking) / 2
    for character in text:
        draw.text((x, y), character, font=font, fill=fill, anchor="l" + anchor[1])
        x += font.getlength(character) + tracking
    return x - position[0]


# The family wordmark: "Other" in a light weight, then the product suffix in bold.
WORDMARK_PARTS = ("Other", "CAD")
WORDMARK_TRACKING = -0.01  # in ems, as on the brand sheet


def wordmark_width(pixels):
    """Return the advance width of the wordmark set at ``pixels``."""
    tracking = pixels * WORDMARK_TRACKING
    light, bold = load_font(pixels, "Light"), load_font(pixels, "Bold")
    prefix, suffix = WORDMARK_PARTS
    return tracked_width(light, prefix, tracking) + tracking + tracked_width(bold, suffix, tracking)


def draw_wordmark(draw, position, pixels, prefix_colour, suffix_colour):
    """Draw the wordmark with its baseline starting at ``position``; return its width.

    On dark surfaces use PAPER and TEAL, on light ones INK and DEEP_TEAL.
    """
    tracking = pixels * WORDMARK_TRACKING
    prefix, suffix = WORDMARK_PARTS
    x, y = position
    x += draw_tracked(draw, (x, y), prefix, load_font(pixels, "Light"), prefix_colour, tracking)
    x += tracking
    x += draw_tracked(draw, (x, y), suffix, load_font(pixels, "Bold"), suffix_colour, tracking)
    return x - position[0]


# --------------------------------------------------------------------------
# Container formats Pillow cannot write on its own
# --------------------------------------------------------------------------


def png_bytes(image):
    """Return ``image`` encoded as a PNG byte string."""
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _dib_entry(image):
    """Encode an image as the 32-bit DIB payload of an ICO entry.

    Windows accepts PNG payloads for large icons, but shell surfaces and NSIS
    are happiest with plain DIB data, so every size below 256 is written this
    way: a bottom-up BGRA bitmap followed by the legacy 1-bit AND mask.
    """
    width, height = image.size
    pixels = np.array(image.convert("RGBA"), dtype=np.uint8)[::-1]
    bgra = pixels[:, :, [2, 1, 0, 3]].tobytes()

    stride = ((width + 31) // 32) * 4
    mask = np.zeros((height, stride), dtype=np.uint8)
    transparent = pixels[:, :, 3] < 128
    for x in range(width):
        mask[:, x // 8] |= transparent[:, x].astype(np.uint8) << (7 - (x % 8))

    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0, len(bgra), 0, 0, 0, 0)
    return header + bgra + mask.tobytes()


def write_ico(path, images):
    """Write a multi-resolution ``.ico`` from pre-rendered images."""
    images = sorted(images, key=lambda image: image.size[0])
    payloads = [png_bytes(image) if image.size[0] >= 256 else _dib_entry(image) for image in images]

    offset = 6 + 16 * len(images)
    directory = struct.pack("<HHH", 0, 1, len(images))
    for image, payload in zip(images, payloads):
        dimension = 0 if image.size[0] >= 256 else image.size[0]
        directory += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(payload), offset
        )
        offset += len(payload)

    Path(path).write_bytes(directory + b"".join(payloads))


_ICNS_TYPES = (
    ("icp4", 16),
    ("icp5", 32),
    ("ic11", 32),
    ("ic12", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic13", 256),
    ("ic09", 512),
    ("ic14", 512),
)


def write_icns(path, render):
    """Write a macOS ``.icns`` using ``render(size)`` for each needed size."""
    cache = {}
    body = b""
    for ostype, size in _ICNS_TYPES:
        if size not in cache:
            cache[size] = png_bytes(render(size))
        payload = cache[size]
        body += ostype.encode("ascii") + struct.pack(">I", len(payload) + 8) + payload
    Path(path).write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


# --------------------------------------------------------------------------
# SVG helpers
# --------------------------------------------------------------------------


def svg_fill(colour):
    """Return the fill attributes for an RGB or RGBA colour."""
    attributes = f'fill="{hex_of(colour)}"'
    if len(colour) > 3 and colour[3] < 255:
        attributes += f' fill-opacity="{colour[3] / 255:.3f}"'
    return attributes


def svg_stroke(colour):
    """Return the stroke attributes for an RGB or RGBA colour."""
    attributes = f'stroke="{hex_of(colour)}"'
    if len(colour) > 3 and colour[3] < 255:
        attributes += f' stroke-opacity="{colour[3] / 255:.3f}"'
    return attributes


def svg_path(points):
    """Return an SVG path definition for a closed polygon."""
    head = "M {:.3f},{:.3f}".format(*points[0])
    tail = " ".join("L {:.3f},{:.3f}".format(x, y) for x, y in points[1:])
    return f"{head} {tail} Z"


def svg_document(width, height, body, title):
    """Wrap SVG fragments in a minimal, Qt-friendly document."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" version="1.1">\n'
        f"  <title>{title}</title>\n"
        f"{body}\n"
        "</svg>\n"
    )
