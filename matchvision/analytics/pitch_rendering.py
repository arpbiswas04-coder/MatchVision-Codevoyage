"""Dark pitch-style rendering without assigning a partial region to fictitious goals."""
import cv2
import numpy as np


def render_pitch_heatmap(counts, path, title, bounds, sample_count, fps):
    # Histogram is [y][x]. Screen horizontal = lateral y; vertical = longitudinal x.
    length, width = bounds[1] - bounds[0], bounds[3] - bounds[2]
    scale = min(840 / width, 600 / length)
    plot_w, plot_h = max(1, round(width * scale)), max(1, round(length * scale))
    canvas_w, canvas_h = max(1200, plot_w + 370), max(620, plot_h + 230)
    canvas = np.full((canvas_h, canvas_w, 3), (27, 18, 11), np.uint8)
    left, top = 65, 120

    def text(value, x, y, size=.48, color=(193, 209, 198)):
        cv2.putText(canvas, value, (x, y), cv2.FONT_HERSHEY_SIMPLEX, size, color, 1, cv2.LINE_AA)

    text("MATCHVISION / MOVEMENT MAP", 35, 32, .55, (174, 225, 145))
    text(title, 35, 64, .72)
    text("CALIBRATED REGION ONLY - global location on full pitch is unknown", 35, 93)
    field = np.full((plot_h, plot_w, 3), (35, 64, 31), np.uint8)
    stripe = max(1, round(5 * scale))
    for row in range(0, plot_h, 2 * stripe):
        field[row:row + stripe] = (39, 72, 35)
    density = np.flipud(counts.T).astype(np.float32)
    density = cv2.resize(density, (plot_w, plot_h), interpolation=cv2.INTER_LINEAR)
    density = cv2.GaussianBlur(density, (0, 0), sigmaX=max(1, scale * .35))
    maximum = float(density.max())
    density = density / maximum if maximum > 0 else density
    heat = cv2.applyColorMap(np.uint8(np.clip(density * 255, 0, 255)), cv2.COLORMAP_TURBO)
    alpha = (.70 * np.sqrt(density))[..., None]
    field = np.uint8(field * (1 - alpha) + heat * alpha)
    canvas[top:top + plot_h, left:left + plot_w] = field
    # These are measured-region edges, NOT asserted match touch/goal lines.
    cv2.rectangle(canvas, (left, top), (left + plot_w, top + plot_h), (161, 196, 165), 1)
    for fraction in (.25, .5, .75):
        x = left + round(plot_w * fraction)
        cv2.line(canvas, (x, top), (x, top + plot_h), (81, 111, 85), 1)
    text(f"x max {bounds[1]:.2f} m", left, top - 10, .4)
    text(f"x min {bounds[0]:.2f} m", left, top + plot_h + 22, .4)
    text(f"y {bounds[2]:.2f} m", left, top + plot_h + 46, .4)
    text(f"y {bounds[3]:.2f} m", left + max(0, plot_w - 105), top + plot_h + 46, .4)
    text("x / length increases UP; y / width increases RIGHT", 35, canvas_h - 91)
    text(f"{sample_count} samples | {sample_count / fps:.2f} sample-seconds", 35, canvas_h - 64)
    text("Display smoothing only; numeric bins unchanged. Colour scales are independent.", 35, canvas_h - 37, .44)
    text("Original calibration is unvalidated for a new camera view.", 35, canvas_h - 15, .4)

    # Unregistered full-pitch context diagram: never place this analysis's points on it.
    rx, ry, rw, rh = canvas_w - 260, 165, 210, 324
    text("PITCH REFERENCE", rx, ry - 48, .47)
    text("No analysis data mapped", rx, ry - 27, .4)
    cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), (35, 58, 31), -1)
    line = (131, 157, 135)
    cv2.rectangle(canvas, (rx, ry), (rx + rw, ry + rh), line, 1)
    cv2.line(canvas, (rx, ry + rh // 2), (rx + rw, ry + rh // 2), line, 1)
    cv2.circle(canvas, (rx + rw // 2, ry + rh // 2), 28, line, 1)
    for sign in (1, -1):
        edge = ry if sign == 1 else ry + rh
        cv2.rectangle(canvas, (rx + 43, edge), (rx + rw - 43, edge + sign * 51), line, 1)
        cv2.rectangle(canvas, (rx + 76, edge), (rx + rw - 76, edge + sign * 17), line, 1)
        cv2.rectangle(canvas, (rx + 94, edge), (rx + rw - 94, edge - sign * 6), line, 1)
    text("Reference only, not registration", rx - 5, ry + rh + 25, .35)
    if not cv2.imwrite(str(path), canvas):
        raise OSError(f"Could not write heatmap: {path}")
