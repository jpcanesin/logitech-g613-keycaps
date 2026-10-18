"""Fit keycap.py parameters to caliper measurements (see keys_to_measure.csv).

Measurements: bottom width (front-back) and length (left-right), min/max height at the
middle/corners of the front and back top edges, top width and top length.
Fitted: top_height and tilt (from the two mins), side draft (from top length), one shared
front/back draft (from top width). The dish depth is the higher edge's max - min directly.
"""
import math
import keycap


def measure(**p):
    """Simulated caliper readings on a generated key; -Y is the back edge."""
    s = keycap.make_keycap(**p)
    top = max((f for f in s.Faces if f.Area > 50), key=lambda f: f.CenterOfMass.z)
    pts = [q for e in top.Edges for q in e.discretize(Distance=0.02)]
    yb, yf = max(q.y for q in pts), min(q.y for q in pts)
    mid = [q for q in pts if abs(q.x) < 0.05]
    a, b = min(mid, key=lambda q: q.y), max(mid, key=lambda q: q.y)
    # the higher edge's max is the corner peak (sides slope away); the lower edge's max is read near the edge line
    if a.z >= b.z:
        back_max, front_max = max(q.z for q in pts if q.y < 0), max(q.z for q in pts if q.y > yb - 0.3)
    else:
        back_max, front_max = max(q.z for q in pts if q.y < yf + 0.3), max(q.z for q in pts if q.y > 0)
    side = [q for q in pts if abs(q.y) < 0.05]
    return dict(back_min=a.z, back_max=back_max, front_min=b.z, front_max=front_max,
                top_width=a.distanceToPoint(b), top_length=max(q.x for q in side) - min(q.x for q in side))


def fit(m, base=None, iterations=12):
    """m: measurement dict with keys bottom_width, bottom_length, front_min, front_max,
    back_min, back_max, top_width, top_length. base: fixed parameters (the set's values)."""
    back_high = m["back_min"] >= m["front_min"]
    depth = m["back_max"] - m["back_min"] if back_high else m["front_max"] - m["front_min"]
    p = dict(base or {})
    p.update(base_w=m["bottom_length"], base_d=m["bottom_width"], dish_depth=depth, dish_radius=None,
             top_height=(m["back_min"] + m["front_min"]) / 2, tilt=0.0,
             draft_sides=14.5, draft_back=14.5, draft_front=14.5)
    for _ in range(iterations):
        r = measure(**p)
        p["top_height"] += ((m["back_min"] + m["front_min"]) - (r["back_min"] + r["front_min"])) / 2
        p["tilt"] += math.degrees(math.atan(
            ((m["back_min"] - m["front_min"]) - (r["back_min"] - r["front_min"])) / r["top_width"]))
        z_side = (r["back_min"] + r["front_min"]) / 2 + depth
        p["draft_sides"] += math.degrees(math.atan((r["top_length"] - m["top_length"]) / 2 / z_side))
        z_fb = (r["back_min"] + r["front_min"]) / 2
        d = math.degrees(math.atan((r["top_width"] - m["top_width"]) / 2 / z_fb))
        p["draft_back"] += d
        p["draft_front"] += d
    return p, measure(**p)
