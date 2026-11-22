"""Generate multi-resolution Windows ICO for the installer application."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "backend" / "assets" / "app_icon.ico"
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def _draw_rounded_gradient_bg(size: int) -> Image.Image:
    """Create a rounded square canvas with diagonal #2563eb -> #4f46e5 gradient."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = grad.load()
    c1 = (0x25, 0x63, 0xEB)
    c2 = (0x4F, 0x46, 0xE5)
    denom = max(1, (size - 1) * 2)
    for y in range(size):
        for x in range(size):
            t = (x + y) / denom
            r = int(round(c1[0] + (c2[0] - c1[0]) * t))
            g = int(round(c1[1] + (c2[1] - c1[1]) * t))
            b = int(round(c1[2] + (c2[2] - c1[2]) * t))
            px[x, y] = (r, g, b, 255)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    pad = int(round(size * 0.04))
    radius = int(round(size * 0.22))
    mask_draw.rounded_rectangle((pad, pad, size - 1 - pad, size - 1 - pad), radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    return img


def render_icon_master(size: int = 512) -> Image.Image:
    """Render a crisp 512x512 master icon image matching the HeaderBar brand glyph."""
    img = _draw_rounded_gradient_bg(size)
    draw = ImageDraw.Draw(img)

    # Outer isometric package box (centered slightly left/up to leave room for check badge)
    cx = size * 0.47
    cy = size * 0.49
    stroke = max(4, int(round(size * 0.058)))
    white = (255, 255, 255, 255)
    soft_fill = (255, 255, 255, 38)

    dx = size * 0.255
    dy_top = size * 0.145
    dy_side = size * 0.245

    top = (cx, cy - dy_side)
    right = (cx + dx, cy - dy_side + dy_top)
    bottom = (cx, cy + dy_side)
    left = (cx - dx, cy - dy_side + dy_top)
    center = (cx, cy - dy_side + dy_top * 2)
    bot_left = (cx - dx, cy + dy_side - dy_top)
    bot_right = (cx + dx, cy + dy_side - dy_top)

    # Subtle translucent faces for 3D depth
    draw.polygon([top, right, center, left], fill=soft_fill)
    draw.polygon([left, center, bottom, bot_left], fill=(255, 255, 255, 20))

    # Box outer silhouette + inner fold lines
    draw.line([top, right, bot_right, bottom, bot_left, left, top], fill=white, width=stroke, joint="curve")
    draw.line([left, center, right], fill=white, width=stroke, joint="curve")
    draw.line([center, bottom], fill=white, width=stroke)

    # Package tape accent on top face
    tape_a = ((top[0] + left[0]) * 0.5, (top[1] + left[1]) * 0.5)
    tape_b = ((right[0] + center[0]) * 0.5, (right[1] + center[1]) * 0.5)
    draw.line([tape_a, tape_b], fill=(219, 234, 254, 220), width=max(3, int(round(stroke * 0.72))))

    # Bottom-right check badge
    badge_cx = size * 0.70
    badge_cy = size * 0.70
    badge_r = size * 0.175
    # Badge background ring in dark indigo/blue for separation, then bright pill
    draw.ellipse(
        (badge_cx - badge_r * 1.15, badge_cy - badge_r * 1.15, badge_cx + badge_r * 1.15, badge_cy + badge_r * 1.15),
        fill=(49, 46, 129, 240),
    )
    draw.ellipse(
        (badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r),
        fill=(239, 246, 255, 255),
    )
    p1 = (badge_cx - badge_r * 0.44, badge_cy + badge_r * 0.02)
    p2 = (badge_cx - badge_r * 0.12, badge_cy + badge_r * 0.34)
    p3 = (badge_cx + badge_r * 0.46, badge_cy - badge_r * 0.30)
    draw.line([p1, p2, p3], fill=(37, 99, 235, 255), width=max(4, int(round(size * 0.055))), joint="curve")

    return img


def generate_ico(output: Path = DEFAULT_OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    master = render_icon_master(512)
    master.save(output, format="ICO", sizes=ICON_SIZES)
    return output


if __name__ == "__main__":
    out = generate_ico()
    print(f"Generated {out} ({out.stat().st_size} bytes)")
