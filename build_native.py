"""Generate the native, fully parametric FreeCAD keycap set from the measurements.

Reads set_measurements.csv, keys_to_measure.csv and layout.csv. Writes set.FCStd
(spreadsheet "Set" with the values shared by the whole set), one shapes/<shape_id>.FCStd
per distinct shape (spreadsheet "Params" + an expression-driven model whose result is the
object "Keycap"), keyboard.FCStd (every key linked to its shape at its layout position)
and fitted_shapes.csv (fit cache: a shape is refit only when its measurements or the set
values change). After generation the .FCStd files need neither Python nor this script:
edit a cell in Set or Params and recompute. Rerunning overwrites them.

Run it inside the FreeCAD GUI (Python console, or the MCP execute_code tool):
  exec(open('/home/jpcanesin/Documents/3d/keyboard/build_native.py').read())
Visibility is only saved from the GUI; files written by a headless run open with everything hidden.
"""
import csv
import json
import os
import sys

HERE = "/home/jpcanesin/Documents/3d/keyboard"
sys.path.insert(0, HERE)
import FreeCAD as App  # noqa: E402
import Part  # noqa: E402
import Draft  # noqa: E402
import fit_profile  # noqa: E402

V = App.Vector
PITCH = 19.05

# Set-wide values (alias, description). Measured ones come from set_measurements.csv,
# the rest from SET_DEFAULTS.
SET_FIELDS = [
    ("wall", "wall thickness, horizontal"),
    ("lip_height", "straight base height before the slant"),
    ("lip_radius", "corner radius of the straight base"),
    ("corner_radius", "outer vertical corner radius"),
    ("top_thickness", "top thickness, normal to the tilted top"),
    ("block_fillet", "stem edge rounding"),
    ("rib_thickness", "rib thickness"),
    ("rib_fillet", "rib bottom edge rounding"),
    ("side_inner", "horizontal stems: half the gap between them"),
    ("side_len", "horizontal stems: size pointing to the center"),
    ("side_width", "horizontal stems: size across"),
    ("side_tip", "horizontal stems: base to stem tip"),
    ("rib_gap_sides", "horizontal stems: tip to rib start"),
    ("end_inner", "vertical stems: half the gap between them"),
    ("end_len", "vertical stems: size pointing to the center"),
    ("end_width", "vertical stems: size across"),
    ("end_tip", "vertical stems: base to stem tip"),
    ("rib_gap_back", "back vertical stem: tip to rib start"),
    ("rib_gap_front", "front vertical stem: tip to rib start"),
    ("top_margin", "construction: walls built this far above the top"),
    ("bottom_margin", "construction: cavity cut starts this far below the rim"),
    ("rib_overlap", "construction: rib reaches this far into its stem"),
    ("cutter_min_size", "construction: minimum cutter size"),
    ("cutter_length_factor", "construction: dish cylinder length / largest footprint side"),
]

SHAPE_FIELDS = [
    ("base_w", "footprint length, left-right"),
    ("base_d", "footprint width, front-back"),
    ("top_height", "dish bottom height at the key center"),
    ("tilt", "top tilt in degrees; positive = back (-Y) higher"),
    ("dish_sag", "dish dip at the end of the straight part of the higher top edge"),
    ("draft_sides", "left/right wall slant from vertical, degrees"),
    ("draft_back", "back wall slant, degrees"),
    ("draft_front", "front wall slant, degrees"),
    ("stem_rotated", "1 = stems/ribs turned 90 degrees, 0 = normal"),
    ("body_w", "raised part's footprint length, flush left; = base_w when the key has no step"),
    ("step_height", "height of the flat shelf right of the raised part (stepped keys only)"),
]

# Derived cells: (alias, formula). Formulas may use any alias above or below them.
DERIVED = [
    ("kx", "tan(draft_sides)"),
    ("kb", "tan(draft_back)"),
    ("kf", "tan(draft_front)"),
    ("body_dx", "(body_w - base_w) / 2"),            # raised part's center, flush with the left edge
    ("half_w", "body_w / 2 + kx * lip_height"),     # wall planes at z=0 (they pass the base band at lip_height)
    ("step_half_w", "base_w / 2 + kx * lip_height"),  # full-footprint side walls, for the shelf
    ("half_b", "base_d / 2 + kb * lip_height"),
    ("half_f", "base_d / 2 + kf * lip_height"),
    ("tan_tilt", "tan(abs(tilt))"),
    ("cos_tilt", "cos(tilt)"),
    ("sin_tilt", "sin(tilt)"),
    ("edge_half", "tilt >= 0 ? half_b : half_f"),   # the higher top edge
    ("edge_k", "tilt >= 0 ? kb : kf"),
    ("edge_z", "(top_height + edge_half * tan_tilt) / (1 + edge_k * tan_tilt)"),
    ("edge_run", "half_w - kx * edge_z - corner_radius"),
    ("dish_radius", "(edge_run ^ 2 + dish_sag ^ 2) / (2 * dish_sag)"),
    ("full_sag", "dish_radius > body_w / 2 ? dish_radius - sqrt(dish_radius ^ 2 - (body_w / 2) ^ 2) : dish_radius"),
    ("wall_top", "top_height + base_d / 2 * tan_tilt + full_sag + top_margin"),
    ("cutter_len", "cutter_length_factor * (base_w > base_d ? base_w : base_d)"),
    ("cutter_size", "cutter_min_size > cutter_len ? cutter_min_size : cutter_len"),
    ("ceil_z", "top_height - top_thickness / cos_tilt"),
    ("reach", "half_w > (half_b > half_f ? half_b : half_f) ? half_w : (half_b > half_f ? half_b : half_f)"),
]


LEGEND_SET_FIELDS = [
    ("font_file", "legend font file (path); point it at another .ttf/.otf to change the font"),
    ("legend_size", "default legend cap height"),
    ("line_gap", "gap between the two lines of a stacked legend"),
    ("legend_depth", "inlay depth, measured perpendicular to the dish"),
]

SET_DEFAULTS = dict(
    lip_radius=1.5, block_fillet=0.35, rib_fillet=0.25,
    top_margin=3.0, bottom_margin=1.0, rib_overlap=0.1, cutter_min_size=200.0, cutter_length_factor=4.0,
    font_file=os.path.join(HERE, "fonts", "Inter-SemiBold.ttf"), legend_size=3.6, line_gap=1.0, legend_depth=0.4,
)
MEASURED = ["bottom_width", "bottom_length", "front_min", "front_max", "back_min", "back_max", "top_width", "top_length"]
STEP = ["step_body_length", "step_height"]  # optional: stepped keys (e.g. a stepped Caps Lock)


def read_set():
    v = {r["parameter"]: float(r["key_1"]) for r in csv.DictReader(open(os.path.join(HERE, "set_measurements.csv")))}
    out = dict(SET_DEFAULTS)
    out.update(
        wall=v["wall_thickness_mm"], lip_height=v["straight_base_height_mm"], corner_radius=v["corner_radius_mm"],
        top_thickness=v["top_thickness_mm"], rib_thickness=v["rib_thickness_mm"],
        side_inner=v["horiz_stem_gap_mm"] / 2, side_len=v["horiz_stem_length_mm"],
        side_width=v["horiz_stem_width_mm"], side_tip=v["horiz_stem_tip_from_base_mm"],
        rib_gap_sides=v["horiz_stem_rib_gap_mm"],
        end_inner=v["vert_stem_gap_mm"] / 2, end_len=v["vert_stem_length_mm"],
        end_width=v["vert_stem_width_mm"], end_tip=v["vert_stem_tip_from_base_mm"],
        rib_gap_back=v["vert_stem_rib_gap_mm"], rib_gap_front=v["vert_stem_rib_gap_mm"],
    )
    return out


def read_shapes():
    shapes = {}
    for r in csv.DictReader(open(os.path.join(HERE, "keys_to_measure.csv"))):
        if r["front_min_mm"]:
            m = {k: float(r[k + "_mm"]) for k in MEASURED}
            m.update({k: float(r[k + "_mm"]) for k in STEP if r.get(k + "_mm")})
            shapes[r["id"]] = dict(m=m, rotated="ROTATED" in r["notes"].upper())
    return shapes


def write_sheet(sheet, rows, start=1):
    """rows: (alias, value or '=formula', description). Column A label, B value, C note."""
    for i, (alias, value, note) in enumerate(rows, start):
        sheet.set("A%d" % i, alias)
        sheet.set("B%d" % i, str(value))
        sheet.setAlias("B%d" % i, alias)
        sheet.set("C%d" % i, note)
    return start + len(rows)


def expr(obj, prop, formula):
    obj.setExpression(prop, formula)


def rect(doc, name, x, y, z, length, height, fillet):
    """Draft rectangle wire; all arguments are expressions over Params."""
    r = Draft.make_rectangle(1, 1)
    r.Label = name
    r.MakeFace = False
    expr(r, "Length", length)
    expr(r, "Height", height)
    expr(r, "FilletRadius", fillet)
    expr(r, "Placement.Base.x", x)
    expr(r, "Placement.Base.y", y)
    expr(r, "Placement.Base.z", z)
    return r


def box_edges():
    """Edge names of a box: bottom edges, vertical edges, bottom edges along X and along Y."""
    b = Part.makeBox(1, 2, 3)
    bottom, vertical, along_x, along_y = [], [], [], []
    for i, e in enumerate(b.Edges, 1):
        p0, p1 = e.Vertexes[0].Point, e.Vertexes[1].Point
        if p0.z == 0 and p1.z == 0:
            bottom.append("Edge%d" % i)
            (along_x if p0.y == p1.y else along_y).append("Edge%d" % i)
        elif p0.x == p1.x and p0.y == p1.y:
            vertical.append("Edge%d" % i)
    return bottom, vertical, along_x, along_y


BOTTOM, VERTICAL, ALONG_X, ALONG_Y = box_edges()


def filleted_box(doc, name, length, width, height, x, y, z, radius, edges):
    body = doc.addObject("PartDesign::Body", name)
    box = body.newObject("PartDesign::AdditiveBox", name + "Box")
    expr(box, "Length", length)
    expr(box, "Width", width)
    expr(box, "Height", height)
    fil = body.newObject("PartDesign::Fillet", name + "Fillet")
    fil.Base = (box, edges)
    expr(fil, "Radius", radius)
    expr(body, "Placement.Base.x", x)
    expr(body, "Placement.Base.y", y)
    expr(body, "Placement.Base.z", z)
    return body


def tilted_box(doc, name, pivot_z, start_z):
    """Half-space box above the plane at start_z, tilted about X around (0, 0, pivot_z).
    Its corner (-S/2, -S/2, start_z) is rotated by -tilt around the pivot."""
    b = doc.addObject("Part::Box", name)
    for prop in ("Length", "Width", "Height"):
        expr(b, prop, "Params.cutter_size")
    rel = "(%s - %s)" % (start_z, pivot_z)
    expr(b, "Placement.Base.x", "-Params.cutter_size / 2")
    expr(b, "Placement.Base.y", "-Params.cutter_size / 2 * Params.cos_tilt + %s * Params.sin_tilt" % rel)
    expr(b, "Placement.Base.z", "%s + Params.cutter_size / 2 * Params.sin_tilt + %s * Params.cos_tilt" % (pivot_z, rel))
    b.Placement.Rotation.Axis = V(1, 0, 0)
    expr(b, "Placement.Rotation.Angle", "-Params.tilt")
    return b


def show_only(doc, objs):
    """Show objs and hide everything else; needs the GUI to be stored in the file."""
    if not App.GuiUp:
        return
    import FreeCADGui
    gdoc = FreeCADGui.getDocument(doc.Name)
    for o in doc.Objects:
        vo = gdoc.getObject(o.Name)
        if vo is not None and hasattr(vo, "Visibility"):
            vo.Visibility = o in objs


def build_shape(path, shape_id, vals, set_doc_name):
    """vals: one value per SHAPE_FIELDS alias."""
    doc = App.newDocument(shape_id.replace("-", "_"))
    doc.saveAs(path)  # cross-document expressions need a saved owner document
    sheet = doc.addObject("Spreadsheet::Sheet", "Params")
    rows = [(a, "=%s#Set.%s" % (set_doc_name, a), "from set.FCStd: " + d) for a, d in SET_FIELDS]
    rows += [(a, repr(vals[a]), d) for a, d in SHAPE_FIELDS]
    rows += [(a, "=" + f, "derived") for a, f in DERIVED]
    write_sheet(sheet, rows)
    doc.recompute()

    P = "Params."
    # outer body: ruled loft between rounded rects, clipped by the straight base band
    def outer_at(z):
        return dict(x="%sbody_dx - (%shalf_w - %skx * %s)" % (P, P, P, z), y="-(%shalf_b - %skb * %s)" % (P, P, z), z=z,
                    length="2 * (%shalf_w - %skx * %s)" % (P, P, z),
                    height="%shalf_b - %skb * %s + %shalf_f - %skf * %s" % (P, P, z, P, P, z),
                    fillet=P + "corner_radius")
    lo = rect(doc, "OuterBottom", **outer_at("0"))
    hi = rect(doc, "OuterTop", **outer_at(P + "wall_top"))
    loft = doc.addObject("Part::Loft", "OuterLoft")
    loft.Sections = [lo, hi]
    loft.Solid, loft.Ruled = True, True
    lip = rect(doc, "BaseRect", "%sbody_dx - %sbody_w / 2" % (P, P), "-%sbase_d / 2" % P, "0", P + "body_w",
               P + "base_d", P + "lip_radius")
    band = doc.addObject("Part::Extrusion", "BaseBand")
    band.Base = lip
    band.Solid = True
    band.DirMode = "Custom"
    band.Dir = V(0, 0, 1)
    expr(band, "LengthFwd", P + "wall_top")
    outer = doc.addObject("Part::MultiCommon", "Outer")
    outer.Shapes = [loft, band]

    # dish: cylinder along the tilted Y axis; its lowest line passes through (0, 0, top_height)
    cyl = doc.addObject("Part::Cylinder", "DishCylinder")
    expr(cyl, "Radius", P + "dish_radius")
    expr(cyl, "Height", P + "cutter_len")
    expr(cyl, "Placement.Base.x", P + "body_dx")
    expr(cyl, "Placement.Base.y", "%sdish_radius * %ssin_tilt - %scutter_len / 2 * %scos_tilt" % (P, P, P, P))
    expr(cyl, "Placement.Base.z",
         "%stop_height + %sdish_radius * %scos_tilt + %scutter_len / 2 * %ssin_tilt" % (P, P, P, P, P))
    cyl.Placement.Rotation.Axis = V(1, 0, 0)
    expr(cyl, "Placement.Rotation.Angle", "-90 - %stilt" % P)
    above = tilted_box(doc, "AboveDish", P + "top_height", "(%stop_height + %sdish_radius)" % (P, P))
    tool = doc.addObject("Part::MultiFuse", "DishTool")
    tool.Shapes = [cyl, above]
    outer_cut = doc.addObject("Part::Cut", "OuterCut")
    outer_cut.Base, outer_cut.Tool = outer, tool

    # cavity: inner drafted body with sharp corners, below the ceiling plane
    def inner_at(z):
        return dict(x="%sbody_dx - (%shalf_w - %swall - %skx * %s)" % (P, P, P, P, z),
                    y="-(%shalf_b - %swall - %skb * %s)" % (P, P, P, z), z=z,
                    length="2 * (%shalf_w - %swall - %skx * %s)" % (P, P, P, z),
                    height="%shalf_b - %swall - %skb * %s + %shalf_f - %swall - %skf * %s" % (P, P, P, z, P, P, P, z),
                    fillet="0")
    ilo = rect(doc, "InnerBottom", **inner_at("(-%sbottom_margin)" % P))
    ihi = rect(doc, "InnerTop", **inner_at(P + "wall_top"))
    iloft = doc.addObject("Part::Loft", "InnerLoft")
    iloft.Sections = [ilo, ihi]
    iloft.Solid, iloft.Ruled = True, True
    ceil = tilted_box(doc, "AboveCeiling", P + "ceil_z", P + "ceil_z")
    cavity = doc.addObject("Part::Cut", "Cavity")
    cavity.Base, cavity.Tool = iloft, ceil
    shell = doc.addObject("Part::Cut", "Shell")
    if vals["body_w"] < vals["base_w"]:
        # stepped key: a hollow full-footprint shelf up to step_height, merged with the raised part
        def step_at(z, inset):
            return dict(x="-(%sstep_half_w - %s - %skx * %s)" % (P, inset, P, z),
                        y="-(%shalf_b - %s - %skb * %s)" % (P, inset, P, z), z=z,
                        length="2 * (%sstep_half_w - %s - %skx * %s)" % (P, inset, P, z),
                        height="%shalf_b - %s - %skb * %s + %shalf_f - %s - %skf * %s" % (P, inset, P, z, P, inset, P, z),
                        fillet=P + "corner_radius" if inset == "0" else "0")
        sl = doc.addObject("Part::Loft", "StepLoft")
        sl.Sections = [rect(doc, "StepBottom", **step_at("0", "0")), rect(doc, "StepTop", **step_at(P + "step_height", "0"))]
        sl.Solid, sl.Ruled = True, True
        srect = rect(doc, "StepBaseRect", "-%sbase_w / 2" % P, "-%sbase_d / 2" % P, "0", P + "base_w", P + "base_d",
                     P + "lip_radius")
        sband = doc.addObject("Part::Extrusion", "StepBaseBand")
        sband.Base = srect
        sband.Solid = True
        sband.DirMode = "Custom"
        sband.Dir = V(0, 0, 1)
        expr(sband, "LengthFwd", P + "step_height")
        step = doc.addObject("Part::MultiCommon", "StepOuter")
        step.Shapes = [sl, sband]
        si = doc.addObject("Part::Loft", "StepCavity")
        si.Sections = [rect(doc, "StepInnerBottom", **step_at("(-%sbottom_margin)" % P, P + "wall")),
                       rect(doc, "StepInnerTop", **step_at("(%sstep_height - %stop_thickness)" % (P, P), P + "wall"))]
        si.Solid, si.Ruled = True, True
        outer_all = doc.addObject("Part::MultiFuse", "OuterWithStep")
        outer_all.Shapes = [outer_cut, step]
        cavity_all = doc.addObject("Part::MultiFuse", "CavityWithStep")
        cavity_all.Shapes = [cavity, si]
        shell.Base, shell.Tool = outer_all, cavity_all
    else:
        shell.Base, shell.Tool = outer_cut, cavity

    # stems and ribs in the normal orientation; a clone turns them when stem_rotated = 1
    feats = []
    for s, tag in ((1, "Pos"), (-1, "Neg")):
        sx = "%s(%sside_inner)" % ("" if s > 0 else "-", P)
        feats.append(filleted_box(
            doc, "SideStem" + tag, P + "side_len", P + "side_width", "%swall_top - %sside_tip" % (P, P),
            sx if s > 0 else "-(%sside_inner + %sside_len)" % (P, P), "-%sside_width / 2" % P, P + "side_tip",
            P + "block_fillet", BOTTOM + VERTICAL))
        rib_start = "(%sside_inner + %sside_len - %srib_overlap)" % (P, P, P)
        feats.append(filleted_box(
            doc, "SideRib" + tag, "%sreach - %s" % (P, rib_start), P + "rib_thickness",
            "%swall_top - %sside_tip - %srib_gap_sides" % (P, P, P),
            rib_start if s > 0 else "-" + P + "reach", "-%srib_thickness / 2" % P,
            "%sside_tip + %srib_gap_sides" % (P, P), P + "rib_fillet", ALONG_X))
        feats.append(filleted_box(
            doc, "EndStem" + tag, P + "end_width", P + "end_len", "%swall_top - %send_tip" % (P, P),
            "-%send_width / 2" % P, P + "end_inner" if s > 0 else "-(%send_inner + %send_len)" % (P, P),
            P + "end_tip", P + "block_fillet", BOTTOM + VERTICAL))
        rib_start = "(%send_inner + %send_len - %srib_overlap)" % (P, P, P)
        gap = P + ("rib_gap_front" if s > 0 else "rib_gap_back")
        feats.append(filleted_box(
            doc, "EndRib" + tag, P + "rib_thickness", "%sreach - %s" % (P, rib_start),
            "%swall_top - %send_tip - %s" % (P, P, gap),
            "-%srib_thickness / 2" % P, rib_start if s > 0 else "-" + P + "reach",
            "%send_tip + %s" % (P, gap), P + "rib_fillet", ALONG_Y))
    mount = doc.addObject("Part::MultiFuse", "Mount")
    mount.Shapes = feats
    turned = Draft.make_clone(mount)
    turned.Label = "MountTurned"
    turned.Placement.Rotation.Axis = V(0, 0, 1)
    expr(turned, "Placement.Rotation.Angle", "%sstem_rotated * 90" % P)
    expr(turned, "Placement.Base.x", P + "body_dx")  # stems centered on the raised part
    trimmed = doc.addObject("Part::MultiCommon", "MountTrimmed")
    trimmed.Shapes = [turned, outer_cut]

    result = doc.addObject("Part::MultiFuse", "Keycap")
    result.Shapes = [shell, trimmed]
    result.Refine = True
    doc.recompute()
    show_only(doc, [result])
    doc.save()
    return doc, result


# shape values each key's Legend sheet mirrors, to place the text and follow the dish
SHAPE_REFS = ["body_dx", "half_w", "kx", "half_b", "kb", "half_f", "kf", "top_height", "tilt", "sin_tilt",
              "cos_tilt", "dish_radius", "cutter_len", "wall_top", "bottom_margin"]
JUSTIFY = {"center": ("Middle-Center", 0, 0), "left": ("Middle-Left", -1, 0), "right": ("Middle-Right", 1, 0),
           "top": ("Top-Center", 0, 1)}


def build_key(path, doc_name, label, shape_result, set_doc_name, lg):
    """One physical key: its shape's Keycap with the legend inlaid. Results: Cap and Inlay
    (or just Cap, a link to the shape, when the key has no legend)."""
    doc = App.newDocument(doc_name)
    doc.saveAs(path)
    body = doc.addObject("App::Link", "Body")
    body.setLink(shape_result)
    lines = [t for t in (lg["line1"], lg["line2"]) if t]
    if not lines:
        body.Label = "Cap"
        doc.recompute()
        show_only(doc, [body])
        doc.save()
        return doc, body, None
    justify, ax, ay = JUSTIFY[lg["align"]]
    S = shape_result.Document.Name
    rows = [(a, "=%s#Set.%s" % (set_doc_name, a), "from set.FCStd") for a, _ in LEGEND_SET_FIELDS]
    rows += [(a, "=%s#Params.%s" % (S, a), "from the shape") for a in SHAPE_REFS]
    rows += [("line1", "'" + lines[0], "top line (or the only line)"),
             ("line2", "'" + (lines[1] if len(lines) > 1 else ""), "bottom line of a stacked legend"),
             ("align_x", repr(ax), "-1 = left margin, 0 = centered, 1 = right margin"),
             ("align_y", repr(ay), "1 = margin from the front (top of the legend) edge, 0 = centered"),
             ("margin", repr(float(lg["margin_mm"] or 0)), "distance from the aligned edge"),
             ("size", lg["size_mm"] or "=legend_size", "cap height")]
    rows += [(a, "=" + f, "derived") for a, f in [
        ("edge_x", "half_w - kx * top_height"),             # top outline, measured at the dish bottom height
        ("left_edge", "body_dx - edge_x"),
        ("right_edge", "body_dx + edge_x"),
        ("back_edge", "-(half_b - kb * top_height)"),
        ("front_edge", "half_f - kf * top_height"),
        ("anchor_x", "align_x < 0 ? left_edge + margin : (align_x > 0 ? right_edge - margin : body_dx)"),
        ("anchor_y", "align_y > 0 ? front_edge - margin : (back_edge + front_edge) / 2"),
        ("line_step", "size + line_gap"),
    ]]
    sheet = doc.addObject("Spreadsheet::Sheet", "Legend")
    write_sheet(sheet, rows)
    doc.recompute()

    L = "Legend."
    prisms = []
    for i in range(len(lines)):
        t = Draft.make_shapestring(String="x", FontFile=App.getDocument(set_doc_name).Set.get("font_file"), Size=1.0)
        t.Label = "Line%d" % (i + 1)
        t.JustificationReference = "Cap Height"
        t.Justification = justify
        expr(t, "FontFile", L + "font_file")
        expr(t, "String", L + "line%d" % (i + 1))
        expr(t, "Size", L + "size")
        expr(t, "Placement.Base.x", L + "anchor_x")
        offset = "" if len(lines) == 1 else (" + %sline_step / 2" % L if i == 0 else " - %sline_step / 2" % L)
        expr(t, "Placement.Base.y", L + "anchor_y" + offset)
        ext = doc.addObject("Part::Extrusion", "Line%dPrism" % (i + 1))
        ext.Base = t
        ext.Solid = True
        ext.DirMode = "Custom"
        ext.Dir = V(0, 0, 1)
        expr(ext, "LengthFwd", L + "wall_top")
        prisms.append(ext)

    # the layer within legend_depth below the dish: between the dish cylinder and one legend_depth larger
    def dish_cylinder(name, radius):
        c = doc.addObject("Part::Cylinder", name)
        expr(c, "Radius", radius)
        expr(c, "Height", L + "cutter_len")
        expr(c, "Placement.Base.x", L + "body_dx")
        expr(c, "Placement.Base.y", "%sdish_radius * %ssin_tilt - %scutter_len / 2 * %scos_tilt" % (L, L, L, L))
        expr(c, "Placement.Base.z",
             "%stop_height + %sdish_radius * %scos_tilt + %scutter_len / 2 * %ssin_tilt" % (L, L, L, L, L))
        c.Placement.Rotation.Axis = V(1, 0, 0)
        expr(c, "Placement.Rotation.Angle", "-90 - %stilt" % L)
        return c
    layer = doc.addObject("Part::Cut", "InlayLayer")
    layer.Base = dish_cylinder("DepthCylinder", "%sdish_radius + %slegend_depth" % (L, L))
    layer.Tool = dish_cylinder("DishCylinder", L + "dish_radius")
    text = prisms[0]
    if len(prisms) > 1:
        text = doc.addObject("Part::MultiFuse", "TextPrisms")
        text.Shapes = prisms
    legend = doc.addObject("Part::MultiCommon", "Inlay")
    legend.Shapes = [text, layer]
    cap = doc.addObject("Part::Cut", "Cap")
    cap.Base, cap.Tool = body, legend
    cap.Refine = True
    doc.recompute()
    show_only(doc, [cap, legend])
    if App.GuiUp:
        import FreeCADGui
        FreeCADGui.getDocument(doc.Name).getObject(legend.Name).ShapeColor = (0.95, 0.95, 0.95)
    doc.save()
    return doc, cap, legend


def main():
    set_vals = read_set()
    shapes = read_shapes()
    layout = list(csv.DictReader(open(os.path.join(HERE, "layout.csv"))))

    set_doc = App.newDocument("set")
    sheet = set_doc.addObject("Spreadsheet::Sheet", "Set")
    write_sheet(sheet, [(a, set_vals[a] if isinstance(set_vals[a], str) else repr(set_vals[a]), d)
                        for a, d in SET_FIELDS + LEGEND_SET_FIELDS])
    set_doc.recompute()
    set_doc.saveAs(os.path.join(HERE, "set.FCStd"))

    cache_path = os.path.join(HERE, "fitted_shapes.csv")
    cache = {}
    if os.path.exists(cache_path):
        cache = {r["signature"]: json.loads(r["params"]) for r in csv.DictReader(open(cache_path))}

    # one shape file per distinct measurement; keys with identical measurements share it
    def signature(sid):
        shape_set = {a: set_vals[a] for a, _ in SET_FIELDS}  # legend settings don't affect the shape
        return json.dumps([shapes[sid]["m"], shapes[sid]["rotated"], shape_set], sort_keys=True)
    groups = {}
    for k in layout:
        groups.setdefault(signature(k["shape_id"]), []).append(k["shape_id"])
    out = os.path.join(HERE, "shapes")
    os.makedirs(out, exist_ok=True)
    built, rows = {}, []
    for sig, sids in groups.items():
        sid = sids[0]
        shape = shapes[sid]
        rot = 1 if shape["rotated"] else 0
        if sig in cache:
            vals = cache[sig]
            vals.setdefault("body_w", vals["base_w"])  # entries cached before stepped keys existed
            vals.setdefault("step_height", 0.0)
            doc, result = build_shape(os.path.join(out, sid + ".FCStd"), sid, vals, set_doc.Name)
            note = "cached"
        else:
            m = shape["m"]
            start = dict(base_w=m["bottom_length"], base_d=m["bottom_width"],
                         top_height=(m["back_min"] + m["front_min"]) / 2, tilt=0.0,
                         dish_sag=fit_profile.edge_depth(m), draft_sides=14.5, draft_back=14.5, draft_front=14.5,
                         stem_rotated=rot, body_w=m.get("step_body_length", m["bottom_length"]),
                         step_height=m.get("step_height", 0.0))
            doc, result = build_shape(os.path.join(out, sid + ".FCStd"), sid, start, set_doc.Name)
            vals, pred = fit_profile.fit(doc, m)
            vals.update(stem_rotated=rot, body_w=start["body_w"], step_height=start["step_height"])
            err = max(abs(pred[c] - m[c]) for c in ("front_min", "back_min", "top_width", "top_length"))
            note = "fitted, worst error %.3f mm" % err
        show_only(doc, [result])
        doc.save()
        print("shape", sid, note, "valid", result.Shape.isValid(), "solids", len(result.Shape.Solids), flush=True)
        for x in sorted(set(sids)):
            built[x] = result
        rows.append(dict(shape_ids=" ".join(sorted(set(sids))), signature=sig, params=json.dumps(vals, sort_keys=True)))
    with open(cache_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["shape_ids", "signature", "params"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    # one file per physical key: the shape with its legend inlaid
    legends = {r["key"]: r for r in csv.DictReader(open(os.path.join(HERE, "legends.csv")))}
    key_dir = os.path.join(HERE, "keys")
    os.makedirs(key_dir, exist_ok=True)
    parts = []
    for i, k in enumerate(layout, 1):
        name = "%03d_%s_%s" % (i, k["row"], k["key"])
        doc, cap, legend = build_key(os.path.join(key_dir, name + ".FCStd"), "K%03d" % i, name,
                                     built[k["shape_id"]], set_doc.Name, legends[k["key"]])
        parts.append((k, cap, legend))
        if legend is not None and not (cap.Shape.isValid() and legend.Shape.isValid() and legend.Shape.Volume > 0):
            print("WARNING legend problem on", name, flush=True)
    print("keys:", len(parts), "key files in", key_dir, flush=True)

    master = App.newDocument("Keyboard")
    master.saveAs(os.path.join(HERE, "keyboard.FCStd"))
    for k, cap, legend in parts:
        x = (float(k["x_u"]) + float(k["w_u"]) / 2) * PITCH
        y = -(float(k["y_u"]) + float(k["h_u"]) / 2) * PITCH  # rows run toward the user (-Y)
        for obj, suffix in ((cap, ""), (legend, "_legend")):
            if obj is None:
                continue
            link = master.addObject("App::Link", "Key")
            link.setLink(obj)
            link.Label = "%s_%s%s" % (k["row"], k["key"], suffix)
            link.Placement = App.Placement(V(x, y, 0), App.Rotation())
    master.recompute()
    show_only(master, [o for o in master.Objects if o.TypeId == "App::Link"])
    master.save()
    print("master: keyboard.FCStd with", len(layout), "linked keys", flush=True)


main()
