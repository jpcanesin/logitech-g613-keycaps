"""Fit a native keycap model (a shapes/*.FCStd document) to caliper measurements.

Measurements (keys_to_measure.csv): bottom width (front-back) and length (left-right),
min/max height at the middle/corners of the front and back top edges, top width and length.
The fit edits the document's Params cells and recomputes: top_height and tilt from the two
mins, dish_sag from the higher edge's max - min, draft_sides from the top length and one
shared front/back draft from the top width.
"""
import math


def measure(shape):
    """Simulated caliper readings on a keycap shape; -Y is the back edge."""
    top = max((f for f in shape.Faces if f.Area > 50), key=lambda f: f.CenterOfMass.z)
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


def edge_depth(r):
    """Dish depth as the caliper reads it: max - min on the higher edge."""
    if r["back_min"] >= r["front_min"]:
        return r["back_max"] - r["back_min"]
    return r["front_max"] - r["front_min"]


def fit(doc, m, iterations=15):
    """doc: a native keycap document (Params sheet + Keycap). m: measurement dict with keys
    bottom_width, bottom_length, front_min, front_max, back_min, back_max, top_width, top_length.
    Returns the fitted Params values and the simulated readings of the result."""
    depth = edge_depth(m)
    v = dict(base_w=m["bottom_length"], base_d=m["bottom_width"], top_height=(m["back_min"] + m["front_min"]) / 2,
             tilt=0.0, dish_sag=depth, draft_sides=14.5, draft_back=14.5, draft_front=14.5)

    def apply():
        for k, x in v.items():
            doc.Params.set(k, repr(x))
        doc.recompute()
        return measure(doc.getObject("Keycap").Shape)

    for _ in range(iterations):
        r = apply()
        v["top_height"] += ((m["back_min"] + m["front_min"]) - (r["back_min"] + r["front_min"])) / 2
        v["tilt"] += math.degrees(math.atan(
            ((m["back_min"] - m["front_min"]) - (r["back_min"] - r["front_min"])) / r["top_width"]))
        v["dish_sag"] *= depth / edge_depth(r)
        z_side = (r["back_min"] + r["front_min"]) / 2 + depth
        v["draft_sides"] += math.degrees(math.atan((r["top_length"] - m["top_length"]) / 2 / z_side))
        z_fb = (r["back_min"] + r["front_min"]) / 2
        d = math.degrees(math.atan((r["top_width"] - m["top_width"]) / 2 / z_fb))
        v["draft_back"] += d
        v["draft_front"] += d
    return v, apply()
