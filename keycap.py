"""Parametric keycap generator for FreeCAD.

DEFAULTS were reconstructed from an original reference keycap STL (since removed);
the keyboard build overrides them with the measured set values. All dimensions in mm, angles in degrees.
Key frame: rim (open bottom) on Z=0, +Z up, X across the key (left-right),
-Y = back (edge nearest the user, at the bottom of the legend), +Y = front.

Usage
  In FreeCAD (GUI console or macro):
      import sys; sys.path.insert(0, "/home/jpcanesin/Documents/3d/keyboard")
      import keycap; keycap.show(keycap.make_keycap())
  Headless:
      ~/tools/FreeCAD.AppImage freecadcmd -c "import sys; sys.path.insert(0, '.');
          import keycap; keycap.export('k.stl', base_w=27.7)"

Derive other keys by overriding entries of DEFAULTS, e.g.
  make_keycap(base_w=27.5, base_d=18.0, top_height=8.61, tilt=10.15, dish_depth=0.8)
"""
import math
import FreeCAD as App
import Part

V = App.Vector

DEFAULTS = dict(
    # footprint
    base_w=18.167,          # footprint width at the rim (X), measured
    base_d=17.867,          # footprint depth at the rim (Y), measured
    lip_height=0.74,        # vertical band at the base before the draft starts
    lip_radius=1.5,         # corner radius of the base band
    corner_radius=1.414,    # outer vertical corner radius (constant along the draft)
    draft_sides=14.5,       # wall draft from vertical: left and right walls
    draft_back=14.5,        # back wall (-Y)
    draft_front=14.5,       # front wall (+Y)
    wall=1.0,               # wall thickness, measured horizontally
    # top surface (cylindrical dish, curved across X)
    top_height=8.696,       # height of the dish bottom at the key center
    tilt=10.7,              # top tilt about X; positive = back (-Y) higher
    dish_depth=0.4578,      # caliper max - min along the higher top edge; sets the radius per key length
    dish_radius=None,       # set to override dish_depth with an explicit cylinder radius
    top_thickness=1.0,      # dish to ceiling, measured normal to the tilted top
    # mount: 4 blocks around the center, each tied to the nearest wall by a rib
    side_block=dict(inner=2.675, len=1.45, width=1.8, bottom=2.5),   # at +/-X
    end_block=dict(inner=4.275, len=1.08, width=2.4, bottom=1.5),    # at +/-Y
    block_fillet=0.35,
    rib_thickness=0.8,
    rib_fillet=0.25,        # rounds the two long bottom edges of each rib
    # rib starts this far above the tip of the stem it joins
    rib_gap_sides=3.253,
    rib_gap_back=4.689,
    rib_gap_front=3.169,
    stem_rotated=False,     # True turns the whole stem/rib arrangement 90 deg around the center
    # construction margins: any value large enough gives the same key
    top_margin=3.0,         # walls are built this far above the highest point of the top before the dish cut
    bottom_margin=1.0,      # the cavity cut starts this far below the rim
    rib_overlap=0.1,        # how far each rib extends into its stem so the two fuse
    cutter_min_size=200.0,  # minimum size of the tilted half-space cutters
    cutter_length_factor=4.0,  # dish cylinder length as a multiple of the key's largest footprint side
)


def _rounded_rect(hw, yb, yf, r, z):
    """Closed wire at height z: x in [-hw, hw], y in [yb, yf], corner radius r."""
    if r <= 0:
        pts = [V(-hw, yb, z), V(hw, yb, z), V(hw, yf, z), V(-hw, yf, z)]
        return Part.makePolygon(pts + [pts[0]])
    # corner arc centers, counterclockwise from the back-right corner
    centers = [V(hw - r, yb + r, z), V(hw - r, yf - r, z), V(-hw + r, yf - r, z), V(-hw + r, yb + r, z)]
    edges = []
    for i, c in enumerate(centers):
        a0 = -90 + 90 * i
        edges.append(Part.makeCircle(r, c, V(0, 0, 1), a0, a0 + 90))
        a1 = math.radians(a0 + 90)
        off = V(r * math.cos(a1), r * math.sin(a1), 0)
        edges.append(Part.LineSegment(c + off, centers[(i + 1) % 4] + off).toShape())
    return Part.Wire(Part.__sortEdges__(edges))


def _drafted(hw, hb, hf, kx, kb, kf, r, z0, z1):
    """Ruled loft between two rounded rects. hw/hb/hf: distances from the center to the
    side, back and front wall planes at z=0; kx/kb/kf: tan of each wall's draft."""
    wires = [_rounded_rect(hw - kx * z, -(hb - kb * z), hf - kf * z, r, z) for z in (z0, z1)]
    return Part.makeLoft(wires, True, True)


def _tilted_halfspace_above(z_center, tilt, size, pivot_z=None):
    """Solid filling everything above the plane at z_center, tilted about X around pivot_z."""
    pivot = V(0, 0, z_center if pivot_z is None else pivot_z)
    box = Part.makeBox(size, size, size, V(-size / 2, -size / 2, 0))
    box.translate(V(0, 0, z_center))
    box.rotate(pivot, V(1, 0, 0), -tilt)  # +tilt raises the back (-Y)
    return box


def _block(x0, x1, y0, y1, z0, z1, fillet):
    b = Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))
    if fillet > 0:
        # round the vertical edges and the bottom edges; the top is buried in the ceiling
        edges = [e for e in b.Edges if min(v.Point.z for v in e.Vertexes) < z0 + 1e-6]
        b = b.makeFillet(fillet, edges)
    return b


def _rib(x0, x1, y0, y1, z0, z1, fillet):
    b = Part.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))
    if fillet > 0:
        # the two bottom edges running along the rib
        axis = 0 if (x1 - x0) > (y1 - y0) else 1
        edges = [e for e in b.Edges
                 if max(v.Point.z for v in e.Vertexes) < z0 + 1e-6
                 and abs((e.Vertexes[1].Point - e.Vertexes[0].Point)[axis]) > 1e-6]
        b = b.makeFillet(fillet, edges)
    return b


def _walls(p):
    """Distances from the center to the side, back and front wall planes at z=0, and their slopes."""
    kx, kb, kf = (math.tan(math.radians(p[n])) for n in ("draft_sides", "draft_back", "draft_front"))
    lip_hw, lip_hd = p["base_w"] / 2, p["base_d"] / 2
    # each drafted wall plane passes through the base band at lip_height
    lh = p["lip_height"]
    return lip_hw + kx * lh, lip_hd + kb * lh, lip_hd + kf * lh, kx, kb, kf


def _dish_z(p, R, x, y):
    """Height of the dish surface above (x, y)."""
    t = math.radians(p["tilt"])
    ya, za = R * math.sin(t), p["top_height"] + R * math.cos(t)  # a point on the tilted cylinder axis
    return za + (-math.sqrt(R * R - x * x) - (y - ya) * math.sin(t)) / math.cos(t)


def edge_dish_depth(p, R):
    """Caliper reading max - min along the higher top edge, for dish radius R."""
    hw, hb, hf, kx, kb, kf = _walls(p)
    r = p["corner_radius"]
    back = p["tilt"] >= 0  # the higher edge
    h0, k = (hb, kb) if back else (hf, kf)
    s = -1 if back else 1

    def outline(u, z):
        # u in [0, 1]: from the middle of the edge, along it, around the corner, to the middle of the side
        x_end, y_edge = hw - kx * z, s * (h0 - k * z)
        straight, arc = x_end - r, math.pi / 2 * r
        side = abs(y_edge) - r
        dist = u * (straight + arc + side)
        if dist <= straight:
            return dist, y_edge
        if dist <= straight + arc:
            a = (dist - straight) / r
            return x_end - r + r * math.sin(a), y_edge - s * r * (1 - math.cos(a))
        return x_end, s * (abs(y_edge) - r - (dist - straight - arc))

    def edge_z(u):
        z = p["top_height"]
        for _ in range(40):  # the outline shrinks as the edge rises, so iterate to the meeting point
            x, y = outline(u, z)
            if abs(x) >= R:
                return float("inf")
            z = _dish_z(p, R, x, y)
        return z

    zs = [edge_z(i / 400) for i in range(401)]
    return max(zs) - zs[0]


def _radius_for_depth(p):
    hw = _walls(p)[0]
    lo, hi = hw + 1e-3, 1e7
    for _ in range(100):  # depth falls as the radius grows
        mid = math.sqrt(lo * hi)
        if edge_dish_depth(p, mid) > p["dish_depth"]:
            lo = mid
        else:
            hi = mid
    return math.sqrt(lo * hi)


def make_keycap(**over):
    p = dict(DEFAULTS)
    p.update(over)
    hw, hb, hf, kx, kb, kf = _walls(p)
    w, d = p["base_w"], p["base_d"]
    lip_hw, lip_hd = w / 2, d / 2
    tilt = p["tilt"]
    ta = math.radians(tilt)
    R = p["dish_radius"] or _radius_for_depth(p)
    sag = R - math.sqrt(R ** 2 - (w / 2) ** 2) if R > w / 2 else R
    h_top = p["top_height"] + d / 2 * abs(math.tan(ta)) + sag + p["top_margin"]  # loft height above everything

    # outer body: drafted loft clipped by the vertical base band
    outer = _drafted(hw, hb, hf, kx, kb, kf, p["corner_radius"], 0, h_top)
    band = Part.Face(_rounded_rect(lip_hw, -lip_hd, lip_hd, p["lip_radius"], 0)).extrude(V(0, 0, h_top))
    outer = outer.common(band)

    # dish: cylinder whose axis lies along the tilted Y direction, above the key.
    # Tilt it around its lowest point at the key center so a large radius doesn't swing it off the key.
    th = p["top_height"]
    L = p["cutter_length_factor"] * max(w, d)
    cyl = Part.makeCylinder(R, L, V(0, -L / 2, th + R), V(0, 1, 0))
    cyl.rotate(V(0, 0, th), V(1, 0, 0), -tilt)
    above = _tilted_halfspace_above(th + R, tilt, size=max(p["cutter_min_size"], L), pivot_z=th)
    outer_cut = outer.cut(cyl.fuse(above))

    # cavity: inner drafted body (sharp corners) below the ceiling plane
    ceil_z = p["top_height"] - p["top_thickness"] / math.cos(ta)
    wt = p["wall"]
    inner = _drafted(hw - wt, hb - wt, hf - wt, kx, kb, kf, 0, -p["bottom_margin"], h_top)
    cavity = inner.cut(_tilted_halfspace_above(ceil_z, tilt, size=max(p["cutter_min_size"], L)))
    shell = outer_cut.cut(cavity)

    # mount features, built tall and trimmed to the inside of the outer skin
    sb, eb, f, t = p["side_block"], p["end_block"], p["block_fillet"], p["rib_thickness"]
    rf = p["rib_fillet"]
    zt = h_top
    reach = max(hw, hb, hf)  # ribs run past the nearest wall in either orientation, then get trimmed
    feats = []
    for s in (1, -1):
        xa, xb = sorted((s * sb["inner"], s * (sb["inner"] + sb["len"])))
        feats.append(_block(xa, xb, -sb["width"] / 2, sb["width"] / 2, sb["bottom"], zt, f))
        rx = sorted((s * (sb["inner"] + sb["len"] - p["rib_overlap"]), s * reach))
        feats.append(_rib(rx[0], rx[1], -t / 2, t / 2, sb["bottom"] + p["rib_gap_sides"], zt, rf))
        ya, yb = sorted((s * eb["inner"], s * (eb["inner"] + eb["len"])))
        feats.append(_block(-eb["width"] / 2, eb["width"] / 2, ya, yb, eb["bottom"], zt, f))
        ry = sorted((s * (eb["inner"] + eb["len"] - p["rib_overlap"]), s * reach))
        rib_z = eb["bottom"] + (p["rib_gap_front"] if s > 0 else p["rib_gap_back"])
        feats.append(_rib(-t / 2, t / 2, ry[0], ry[1], rib_z, zt, rf))
    mount = feats[0].multiFuse(feats[1:])
    if p["stem_rotated"]:
        mount.rotate(V(0, 0, 0), V(0, 0, 1), 90)
    mount = mount.common(outer_cut)

    return shell.fuse(mount).removeSplitter()


def show(shape, name="Keycap", doc=None):
    doc = doc or App.ActiveDocument or App.newDocument("Keycap")
    obj = doc.getObject(name) or doc.addObject("Part::Feature", name)
    obj.Shape = shape
    doc.recompute()
    return obj


def export(path, **over):
    """Build a keycap and write it as .step or .stl."""
    s = make_keycap(**over)
    if path.endswith(".stl"):
        import MeshPart
        MeshPart.meshFromShape(Shape=s, LinearDeflection=0.01, AngularDeflection=0.1).write(path)
    else:
        s.exportStep(path)
    return s
