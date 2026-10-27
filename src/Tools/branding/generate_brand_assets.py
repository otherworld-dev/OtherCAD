# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2026 FuCad contributors

"""Regenerate every OtherCAD brand asset from the definitions in ``brand.py``.

Run it from anywhere after changing the palette or the icon geometry::

    python src/Tools/branding/generate_brand_assets.py

The generated files are committed, so this only needs to run when the identity
itself changes.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from brand import (
    DEEP_TEAL,
    GLOW,
    INK,
    MUTED,
    NIGHT,
    NIGHT_LIT,
    PAPER,
    RING_GLOW_WIDTH,
    RING_RADIUS,
    RING_WIDTH,
    TAGLINE,
    TEAL,
    TILE,
    TILE_GLOW_CENTRE,
    TILE_GLOW_RADIUS,
    TILE_RADIUS,
    app_icon,
    draw_tracked,
    draw_wordmark,
    glyph_primitives,
    hex_of,
    icon_primitives,
    isometric_grid,
    linear_gradient,
    load_font,
    radial_glow,
    render_polygons,
    render_primitives,
    rgba,
    svg_document,
    svg_fill,
    svg_path,
    svg_primitives,
    tracked_width,
    wordmark_width,
    write_icns,
    write_ico,
)

ATTRIBUTION = "Fork of FreeCAD  ·  With thanks to FuCad  ·  LGPL-2.1-or-later"

ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# The watermark behind an empty workspace: the portal ring and glyph, no tile.
WATERMARK_SIZE = 104

# The part of the tile the ring and its glow cover, as a fraction of the tile.
RING_SPAN = (2.0 * RING_RADIUS + RING_GLOW_WIDTH) / TILE


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------


# A sheet of paper with a folded corner, drawn in a 64 unit box. The border is
# a second, slightly larger sheet behind the first so the icon still has an
# edge when it lands on a white file manager background.
PAGE_BORDER = ((12.0, 4.0), (41.0, 4.0), (53.0, 16.0), (53.0, 60.0), (12.0, 60.0))
PAGE = ((13.5, 5.5), (40.38, 5.5), (51.5, 16.62), (51.5, 58.5), (13.5, 58.5))
PAGE_FOLD = ((40.38, 5.5), (51.5, 16.62), (40.38, 16.62))
PROMPT_CHEVRON = (
    (18.0, 24.0),
    (23.0, 24.0),
    (33.0, 36.0),
    (23.0, 48.0),
    (18.0, 48.0),
    (28.0, 36.0),
)
PROMPT_RULE = ((34.0, 43.0), (48.0, 43.0), (48.0, 48.0), (34.0, 48.0))

# Where the glyph sits on the page: the 512 unit tile mapped to this square of
# the 64 unit box, so the cube lands in the open area below the fold.
PAGE_GLYPH_BOX = (6.5, 13.0, 52.0)


def _page_shapes(scale):
    def place(polygon):
        return [(x * scale, y * scale) for x, y in polygon]

    return [
        (place(PAGE_BORDER), rgba(INK)),
        (place(PAGE), rgba(PAPER)),
        (place(PAGE_FOLD), rgba(TEAL)),
    ]


def _page_glyph():
    return glyph_primitives(rgba(INK), rgba(DEEP_TEAL))


def document_icon(size):
    """Icon for ``.FCStd`` documents: the glyph on a sheet of paper."""
    scale = size / 64.0
    canvas = render_polygons((size, size), _page_shapes(scale))
    x, y, side = PAGE_GLYPH_BOX
    canvas.alpha_composite(
        render_primitives((size, size), _page_glyph(), box=(x * scale, y * scale, side * scale))
    )
    return canvas


def script_icon(size):
    """Icon for ``.FCMacro`` scripts: a sheet of paper with a prompt."""
    scale = size / 64.0

    def place(polygon):
        return [(x * scale, y * scale) for x, y in polygon]

    shapes = _page_shapes(scale)
    shapes.append((place(PROMPT_CHEVRON), rgba(INK)))
    shapes.append((place(PROMPT_RULE), rgba(DEEP_TEAL)))
    return render_polygons((size, size), shapes)


# --------------------------------------------------------------------------
# Shared atmosphere for the wide brand surfaces
# --------------------------------------------------------------------------


def _workbench(size, spacing, glow_at=(0.72, 0.62)):
    """The night backdrop: dark gradient, faint construction lines, a teal glow.

    ``glow_at`` is a fraction of the canvas; put it where the ghost icon stands
    so the portal appears to light the bench.
    """
    width, height = size
    canvas = linear_gradient(size, NIGHT_LIT, NIGHT, 52.0).convert("RGBA")
    canvas.alpha_composite(isometric_grid(size, spacing, PAPER, 8))
    canvas.alpha_composite(
        radial_glow(size, (width * glow_at[0], height * glow_at[1]), width * 0.5, TEAL, 26)
    )
    return canvas


def _ghost_icon(canvas, centre, height, alpha=(46, 12, 22, 30)):
    """Composite an oversized, barely-there portal and glyph as a watermark.

    ``centre`` and ``height`` are fractions of the canvas, so the watermark
    keeps the same weight whatever surface it lands on; ``height`` is the
    diameter of the ring's glow. ``alpha`` holds the opacity of the ring, the
    ring's glow, the glyph lines and the accent in that order.
    """
    canvas_width, canvas_height = canvas.size
    side = canvas_height * height / RING_SPAN
    box = (canvas_width * centre[0] - side / 2, canvas_height * centre[1] - side / 2, side)
    shapes = glyph_primitives(
        rgba(PAPER, alpha[2]),
        rgba(GLOW, alpha[3]),
        ring=rgba(TEAL, alpha[0]),
        ring_glow=rgba(TEAL, alpha[1]),
    )
    canvas.alpha_composite(render_primitives(canvas.size, shapes, box=box))


def _lockup(canvas, origin, wordmark_size, tagline_size):
    """Draw the icon, the wordmark and the tagline on a dark surface."""
    draw = ImageDraw.Draw(canvas)
    icon_size = int(round(wordmark_size * 1.45))
    icon_y = int(round(origin[1] - wordmark_size * 0.98))
    canvas.alpha_composite(app_icon(icon_size), (int(round(origin[0])), icon_y))

    text_x = origin[0] + icon_size + wordmark_size * 0.36
    baseline = origin[1] + wordmark_size * 0.06
    draw_wordmark(draw, (text_x, baseline), int(round(wordmark_size)), rgba(PAPER), rgba(TEAL))

    tag_font = load_font(int(round(tagline_size)), "Regular")
    draw_tracked(
        draw,
        (text_x + 1.0, baseline + tagline_size * 2.3),
        TAGLINE,
        tag_font,
        rgba(MUTED),
        tagline_size * 0.26,
    )


def splash(scale=1):
    """Startup splash screen; the version string is painted on it at runtime."""
    size = (640 * scale, 400 * scale)
    canvas = _workbench(size, 30 * scale, glow_at=(0.88, 0.7))
    _ghost_icon(canvas, (0.90, 0.72), 0.80)

    _lockup(canvas, (52 * scale, 150 * scale), 72 * scale, 14 * scale)

    draw = ImageDraw.Draw(canvas)
    footer = load_font(int(round(12 * scale)), "Regular")
    draw_tracked(
        draw,
        (52 * scale, 382 * scale),
        ATTRIBUTION,
        footer,
        rgba(MUTED, 205),
        0.9 * scale,
    )
    return canvas


def about_image(development):
    """Banner shown at the top of the About dialog."""
    size = (552, 189)
    canvas = _workbench(size, 22, glow_at=(0.88, 0.62))
    _ghost_icon(canvas, (0.88, 0.62), 0.80)

    _lockup(canvas, (32, 96), 52, 12)

    draw = ImageDraw.Draw(canvas)
    footer = load_font(11, "Regular")
    draw_tracked(draw, (34, 170), ATTRIBUTION, footer, rgba(MUTED, 205), 0.8)

    if development:
        chip_font = load_font(12, "SemiBold")
        label = "DEVELOPMENT BUILD"
        tracking = 1.6
        width = tracked_width(chip_font, label, tracking)
        left, top = size[0] - width - 46, 14
        draw.rounded_rectangle((left, top, left + width + 24, top + 26), radius=13, fill=rgba(TEAL))
        draw_tracked(draw, (left + 12, top + 18), label, chip_font, rgba(NIGHT), tracking)

    return canvas


def readme_banner():
    """Wide lockup used as the project hero image in the README."""
    size = (1200, 300)
    canvas = _workbench(size, 34, glow_at=(0.84, 0.5))
    _ghost_icon(canvas, (0.84, 0.50), 1.1)
    _lockup(canvas, (88, 158), 96, 19)
    return canvas


# --------------------------------------------------------------------------
# Packaging graphics
# --------------------------------------------------------------------------


def installer_banner():
    """Left-hand panel of the Windows installer wizard."""
    size = (164, 314)
    canvas = _workbench(size, 24, glow_at=(0.5, 0.88))
    _ghost_icon(canvas, (0.50, 0.86), 0.46)

    canvas.alpha_composite(app_icon(76), ((size[0] - 76) // 2, 52))

    draw = ImageDraw.Draw(canvas)
    width = wordmark_width(30)
    draw_wordmark(draw, ((size[0] - width) / 2, 176), 30, rgba(PAPER), rgba(TEAL))

    tag_font = load_font(9, "Regular")
    for index, line in enumerate(("PARAMETRIC 3D", "MODELING")):
        line_width = tracked_width(tag_font, line, 2.0)
        draw_tracked(
            draw,
            ((size[0] - line_width) / 2, 204 + index * 14),
            line,
            tag_font,
            rgba(MUTED),
            2.0,
        )
    return canvas.convert("RGB")


def installer_header():
    """Small logo strip shown in the installer header, on a light background."""
    size = (150, 57)
    canvas = Image.new("RGBA", size, (255, 255, 255, 255))
    canvas.alpha_composite(app_icon(40), (104, 9))

    draw = ImageDraw.Draw(canvas)
    width = wordmark_width(19)
    draw_wordmark(draw, (96 - width, 35), 19, rgba(INK), rgba(DEEP_TEAL))
    return canvas.convert("RGB")


def dmg_background():
    """Backdrop for the macOS disk image, sized around the Finder icon layout."""
    size = (640, 347)
    canvas = linear_gradient(size, (255, 255, 255), PAPER, 70.0).convert("RGBA")
    canvas.alpha_composite(isometric_grid(size, 26, INK, 10))

    canvas.alpha_composite(app_icon(52), (34, 26))
    draw = ImageDraw.Draw(canvas)
    draw_wordmark(draw, (100, 62), 30, rgba(INK), rgba(DEEP_TEAL))
    tag_font = load_font(11, "Regular")
    draw_tracked(draw, (102, 82), TAGLINE, tag_font, rgba(MUTED), 2.4)

    # Finder places the application at x=250 and the Applications link at x=475,
    # so the arrow points across the gap between them.
    arrow_y = 150
    draw.rectangle((330, arrow_y - 4, 388, arrow_y + 4), fill=rgba(DEEP_TEAL))
    draw.polygon(
        [(384, arrow_y - 18), (410, arrow_y), (384, arrow_y + 18)],
        fill=rgba(DEEP_TEAL),
    )

    hint_font = load_font(13, "Regular")
    hint = "DRAG OTHERCAD INTO YOUR APPLICATIONS FOLDER"
    hint_width = tracked_width(hint_font, hint, 2.2)
    draw_tracked(draw, ((size[0] - hint_width) / 2, 296), hint, hint_font, rgba(MUTED), 2.2)
    return canvas.convert("RGB")


# --------------------------------------------------------------------------
# Vector masters
# --------------------------------------------------------------------------


def app_icon_svg():
    """Vector master of the application icon, laid out like the family icons."""
    size = int(TILE)
    cx, cy = TILE_GLOW_CENTRE
    body = (
        "  <defs>\n"
        f'    <radialGradient id="bg" gradientUnits="userSpaceOnUse" cx="{cx:g}" cy="{cy:g}"'
        f' r="{TILE_GLOW_RADIUS:g}">\n'
        f'      <stop offset="0" stop-color="{hex_of(NIGHT_LIT)}"/>\n'
        f'      <stop offset="1" stop-color="{hex_of(NIGHT)}"/>\n'
        "    </radialGradient>\n"
        "  </defs>\n"
        f'  <rect width="{size}" height="{size}" rx="{TILE_RADIUS:g}" fill="url(#bg)"/>\n'
        f"{svg_primitives(icon_primitives())}"
    )
    return svg_document(size, size, body, "OtherCAD")


def document_icon_svg():
    """Vector master of the ``.FCStd`` document icon."""
    page = [(PAGE_BORDER, INK), (PAGE, PAPER), (PAGE_FOLD, TEAL)]
    x, y, side = PAGE_GLYPH_BOX
    body = "\n".join(
        f'  <path d="{svg_path(points)}" {svg_fill(colour)}/>' for points, colour in page
    )
    body += (
        f'\n  <g transform="translate({x:g} {y:g}) scale({side / TILE:g})">\n'
        f"{svg_primitives(_page_glyph(), indent='    ')}\n"
        "  </g>"
    )
    return svg_document(64, 64, body, "OtherCAD document")


def _watermark_shapes(colour):
    return glyph_primitives(colour, colour, ring=colour)


def _watermark_box():
    """Where the tile lands so the ring, without its glow, fills the watermark."""
    side = WATERMARK_SIZE * TILE / (2.0 * RING_RADIUS + RING_WIDTH)
    return ((WATERMARK_SIZE - side) / 2, (WATERMARK_SIZE - side) / 2, side)


def background_svg(colour, opacity):
    """Vector master of the watermark shown behind an empty workspace."""
    x, y, side = _watermark_box()
    body = (
        f'  <g opacity="{opacity}" transform="translate({x:.3f} {y:.3f}) '
        f'scale({side / TILE:.5f})">\n'
        f"{svg_primitives(_watermark_shapes(rgba(colour)), indent='    ')}\n"
        "  </g>"
    )
    return svg_document(WATERMARK_SIZE, WATERMARK_SIZE, body, "OtherCAD")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


class Writer:
    """Writes generated assets below ``repo`` and reports what it produced."""

    def __init__(self, repo):
        self.repo = repo
        self.count = 0

    def _prepare(self, name):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _done(self, path):
        self.count += 1
        print(f"  {path.relative_to(self.repo).as_posix()}")

    def image(self, name, image):
        path = self._prepare(name)
        if path.suffix == ".bmp":
            image.convert("RGB").save(path, format="BMP")
        else:
            image.save(path, format="PNG", optimize=True)
        self._done(path)

    def text(self, name, content):
        path = self._prepare(name)
        path.write_text(content, encoding="utf-8", newline="\n")
        self._done(path)

    def ico(self, name, images):
        path = self._prepare(name)
        write_ico(path, images)
        self._done(path)

    def icns(self, name, render):
        path = self._prepare(name)
        write_icns(path, render)
        self._done(path)


def generate(repo):
    out = Writer(repo)
    icons = "src/Gui/Icons"
    stylesheets = "src/Gui/Stylesheets"

    print("application icons")
    out.text(f"{icons}/othercad.svg", app_icon_svg())
    out.text(f"{icons}/othercad-doc.svg", document_icon_svg())
    for size in (16, 32, 48, 64):
        out.image(f"{icons}/othercad-icon-{size}.png", app_icon(size))
    out.image(f"{icons}/othercad-doc.png", document_icon(64))

    print("splash and about")
    out.image(f"{icons}/othercadsplash.png", splash(1))
    out.image(f"{icons}/othercadsplash_2x.png", splash(2))
    out.image(f"{icons}/othercadabout.png", about_image(False))
    out.image(f"{icons}/othercadaboutdev.png", about_image(True))

    print("workspace watermarks")
    watermarks = (
        ("background_othercad", TEAL, 0.20),
        ("background_othercad_dark", PAPER, 0.14),
        ("background_othercad_light", INK, 0.16),
    )
    for name, colour, opacity in watermarks:
        for folder in ("images_classic", "images_dark-light"):
            out.text(f"{stylesheets}/{folder}/{name}.svg", background_svg(colour, opacity))
        tint = rgba(colour, round(opacity * 255))
        pixels = (WATERMARK_SIZE, WATERMARK_SIZE)
        image = render_primitives(pixels, _watermark_shapes(tint), box=_watermark_box())
        out.image(f"{stylesheets}/images_classic/{name}.png", image)

    print("windows")
    windows_icons = [app_icon(size) for size in ICON_SIZES]
    out.ico("src/Main/icon.ico", windows_icons)
    out.ico("package/WindowsInstaller/icons/OtherCAD.ico", windows_icons)
    out.image("package/WindowsInstaller/graphics/banner.bmp", installer_banner())
    out.image("package/WindowsInstaller/graphics/header.bmp", installer_header())
    out.ico("src/Doc/sphinx/_static/favicon.ico", [app_icon(size) for size in (16, 32, 48)])

    print("macos")
    resources = "src/MacAppBundle/OtherCAD.app/Contents/Resources"
    out.icns(f"{resources}/othercad.icns", app_icon)
    out.icns(f"{resources}/othercad-doc.icns", document_icon)
    out.icns(f"{resources}/othercad-script.icns", script_icon)
    out.image("src/MacAppBundle/DiskImage/background.png", dmg_background())

    print("project")
    out.image(".github/images/othercad-banner.png", readme_banner())

    print(f"\n{out.count} files written")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="repository root (defaults to the checkout this script lives in)",
    )
    arguments = parser.parse_args()
    generate(arguments.repo.resolve())


if __name__ == "__main__":
    main()
