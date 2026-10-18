"""Generate one STL per key of the keyboard.

Inputs (same folder): keys_to_measure.csv, set_measurements.csv, layout.csv.
Outputs: fitted_shapes.csv (fit cache, one row per distinct shape) and stl/NNN_<row>_<key>.stl.
The parametric FreeCAD files (set.FCStd, shapes/, keyboard.FCStd) come from build_native.py,
which reads fitted_shapes.csv.

Run headless:
  ~/tools/FreeCAD.AppImage freecadcmd -c "exec(open('/home/jpcanesin/Documents/3d/keyboard/build_keyboard.py').read())"
Delete fitted_shapes.csv to force a refit (it is also refit when a shape's measurements change).
Define EXPORT_STL = False before exec() to skip the STL export.
"""
import csv
import json
import os
import shutil
import sys

HERE = "/home/jpcanesin/Documents/3d/keyboard"
sys.path.insert(0, HERE)
import keycap  # noqa: E402
import fit_profile  # noqa: E402

EXPORT_STL = globals().get("EXPORT_STL", True)

MEASURED = ["bottom_width", "bottom_length", "front_min", "front_max", "back_min", "back_max", "top_width", "top_length"]


def read_set():
    v = {r["parameter"]: float(r["key_1"]) for r in csv.DictReader(open(os.path.join(HERE, "set_measurements.csv")))}
    return dict(
        wall=v["wall_thickness_mm"],
        lip_height=v["straight_base_height_mm"],
        corner_radius=v["corner_radius_mm"],
        top_thickness=v["top_thickness_mm"],
        rib_thickness=v["rib_thickness_mm"],
        side_block=dict(inner=v["horiz_stem_gap_mm"] / 2, len=v["horiz_stem_length_mm"],
                        width=v["horiz_stem_width_mm"], bottom=v["horiz_stem_tip_from_base_mm"]),
        end_block=dict(inner=v["vert_stem_gap_mm"] / 2, len=v["vert_stem_length_mm"],
                       width=v["vert_stem_width_mm"], bottom=v["vert_stem_tip_from_base_mm"]),
        rib_gap_sides=v["horiz_stem_rib_gap_mm"],
        rib_gap_back=v["vert_stem_rib_gap_mm"],
        rib_gap_front=v["vert_stem_rib_gap_mm"],
    )


def read_shapes():
    shapes = {}
    for r in csv.DictReader(open(os.path.join(HERE, "keys_to_measure.csv"))):
        if not r["front_min_mm"]:
            continue
        m = {k: float(r[k + "_mm"]) for k in MEASURED}
        shapes[r["id"]] = dict(m=m, rotated="ROTATED" in r["notes"].upper())
    return shapes


def signature(shape, set_params):
    return json.dumps([shape["m"], shape["rotated"], set_params], sort_keys=True)


def main():
    set_params = read_set()
    shapes = read_shapes()
    layout = list(csv.DictReader(open(os.path.join(HERE, "layout.csv"))))

    cache_path = os.path.join(HERE, "fitted_shapes.csv")
    cache = {}
    if os.path.exists(cache_path):
        cache = {r["signature"]: json.loads(r["params"]) for r in csv.DictReader(open(cache_path))}

    # fit each distinct shape once
    fitted, rows = {}, []
    by_sig = {}
    for sid in sorted({k["shape_id"] for k in layout}):
        by_sig.setdefault(signature(shapes[sid], set_params), []).append(sid)
    for sig, ids in by_sig.items():
        shape = shapes[ids[0]]
        if sig in cache:
            p = cache[sig]
            print("cached", ids, flush=True)
        else:
            p, pred = fit_profile.fit(shape["m"], base=set_params)
            p["stem_rotated"] = shape["rotated"]
            err = max(abs(pred[k] - shape["m"][k]) for k in ("front_min", "back_min", "top_width", "top_length"))
            print("fitted", ids, "worst error %.3f mm" % err, flush=True)
        for sid in ids:
            fitted[sid] = p
        rows.append(dict(shape_ids=" ".join(ids), signature=sig, params=json.dumps(p, sort_keys=True)))
    with open(cache_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["shape_ids", "signature", "params"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    if EXPORT_STL:
        export_stl(layout, fitted)


def export_stl(layout, fitted):
    # export each distinct shape once, then copy it for every key that uses it
    out = os.path.join(HERE, "stl")
    os.makedirs(out, exist_ok=True)
    first = {}
    for i, k in enumerate(layout, 1):
        path = os.path.join(out, "%03d_%s_%s.stl" % (i, k["row"], k["key"]))
        sid = k["shape_id"]
        key = json.dumps(fitted[sid], sort_keys=True)
        if key in first:
            shutil.copyfile(first[key], path)
        else:
            s = keycap.export(path, **fitted[sid])
            print("built", sid, "valid", s.isValid(), "solids", len(s.Solids), flush=True)
            first[key] = path
    print("done:", len(layout), "keys in", out, flush=True)


main()
