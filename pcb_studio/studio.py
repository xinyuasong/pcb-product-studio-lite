# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Richard Song
"""Subject detection, backdrop, lighting looks, cameras, turntable and exploded view."""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

COLL_NAME = "PCB Studio"


# ---------------------------------------------------------------- helpers

def studio_collection(scene):
    coll = bpy.data.collections.get(COLL_NAME)
    if coll is None:
        coll = bpy.data.collections.new(COLL_NAME)
    if coll.name not in scene.collection.children:
        try:
            scene.collection.children.link(coll)
        except RuntimeError:
            pass
    return coll


def _remove(name):
    ob = bpy.data.objects.get(name)
    if ob is not None:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and data.users == 0:
            for coll in (bpy.data.lights, bpy.data.cameras, bpy.data.meshes):
                if data.name in coll and coll[data.name] == data:
                    coll.remove(data)
                    break


def _new_object(scene, name, data):
    _remove(name)
    ob = bpy.data.objects.new(name, data)
    studio_collection(scene).objects.link(ob)
    return ob


def subject_objects(scene):
    props = scene.pcbs
    obs = [it.obj for it in props.subject if it.obj is not None and it.obj.name in scene.objects]
    return obs


def world_bounds(objects):
    """World-space bounds, using evaluated transforms so drivers (exploded view) count."""
    lo = Vector((1e18, 1e18, 1e18))
    hi = Vector((-1e18, -1e18, -1e18))
    found = False
    try:
        dg = bpy.context.evaluated_depsgraph_get()
    except Exception:
        dg = None
    for ob in objects:
        if ob.type != "MESH":
            continue
        mw = ob.evaluated_get(dg).matrix_world if dg is not None else ob.matrix_world
        for c in ob.bound_box:
            w = mw @ Vector(c)
            lo = Vector((min(lo[i], w[i]) for i in range(3)))
            hi = Vector((max(hi[i], w[i]) for i in range(3)))
            found = True
    if not found:
        return Vector((0, 0, 0)), Vector((0.05, 0.05, 0.01))
    return lo, hi


KICAD_LAYERS = (("_soldermask", "mask"), ("_silkscreen", "silk"), ("_pad", "pad"),
                ("_copper", "copper"), ("_via", "via"), ("_pcb", "body"))


def layer_role(ob):
    """KiCad 8+ GLB exports name board layers '<board>_soldermask', '<board>_copper', ... ."""
    if ob is None or ob.type != "MESH":
        return None
    for name in (ob.data.name, ob.name):
        n = name.lower()
        if "." in n:
            base, _, tail = n.rpartition(".")
            if tail.isdigit():
                n = base
        for suffix, role in KICAD_LAYERS:
            if n.endswith(suffix):
                return role
    return None


def board_parts(objects, board):
    parts = [o for o in objects if layer_role(o) is not None]
    if board is not None and board not in parts:
        parts.append(board)
    return parts


def detect_board(objects):
    """The board is the KiCad '_PCB' layer if present, else the mesh with the largest flat footprint."""
    for ob in objects:
        if layer_role(ob) == "body":
            return ob
    best, score = None, -1.0
    for ob in objects:
        if ob.type != "MESH":
            continue
        lo, hi = world_bounds([ob])
        d = sorted(hi - lo)
        area = d[1] * d[2]
        thin = d[0] / max(d[2], 1e-9)
        s = area * (1.0 if thin < 0.15 else 0.2)
        if s > score:
            best, score = ob, s
    return best


def top_roots(objects):
    tops = []
    for o in objects:
        r = o
        while r.parent is not None:
            r = r.parent
        if r not in tops:
            tops.append(r)
    return tops


def lay_flat(objects, board):
    """Rotate the whole subject so the board lies in XY with components on top. Returns degrees turned."""
    if board is None:
        return None
    lo, hi = world_bounds([board])
    d = hi - lo
    thin_axis = min(range(3), key=lambda i: d[i])
    slo, shi = world_bounds(objects)
    c = (slo + shi) / 2.0
    rot = Matrix.Identity(4)
    turned = []
    if thin_axis == 0:
        rot = Matrix.Rotation(math.radians(-90), 4, "Y")
        turned.append("Y-90")
    elif thin_axis == 1:
        rot = Matrix.Rotation(math.radians(90), 4, "X")
        turned.append("X+90")
    roots = top_roots(objects)
    T = Matrix.Translation(c)
    Ti = Matrix.Translation(-c)
    if turned:
        for r in roots:
            r.matrix_world = T @ rot @ Ti @ r.matrix_world
        bpy.context.view_layer.update()
    # components should be mostly on top
    blo, bhi = world_bounds([board])
    mid = (blo.z + bhi.z) / 2.0
    above = below = 0.0
    fixed = set(board_parts(objects, board))
    for o in objects:
        if o in fixed or o.type != "MESH":
            continue
        olo, ohi = world_bounds([o])
        vol = max((ohi - olo).x, 1e-9) * max((ohi - olo).y, 1e-9) * max((ohi - olo).z, 1e-9)
        if (olo.z + ohi.z) / 2.0 >= mid:
            above += vol
        else:
            below += vol
    if below > above:
        flip = Matrix.Rotation(math.pi, 4, "X")
        for r in roots:
            r.matrix_world = T @ flip @ Ti @ r.matrix_world
        bpy.context.view_layer.update()
        turned.append("X180")
    return turned


# ---------------------------------------------------------------- backdrop

def build_backdrop(scene, centre, size, floor_z, color):
    """A seamless cyclorama sweep behind the subject (+Y is 'back')."""
    S = size
    w = 30.0 * S          # width along X
    depth = 12.0 * S      # floor in front
    back = 6.0 * S        # distance from centre to start of curve
    radius = 5.0 * S
    height = 14.0 * S
    prof = []
    prof.append((-depth, 0.0))
    prof.append((back, 0.0))
    steps = 16
    for i in range(1, steps + 1):
        a = (math.pi / 2) * i / steps
        prof.append((back + radius * math.sin(a), radius - radius * math.cos(a)))
    prof.append((back + radius, height))

    bm = bmesh.new()
    left, right = [], []
    for (y, z) in prof:
        left.append(bm.verts.new((centre.x - w / 2, centre.y + y, floor_z + z)))
        right.append(bm.verts.new((centre.x + w / 2, centre.y + y, floor_z + z)))
    for i in range(len(prof) - 1):
        bm.faces.new((left[i], right[i], right[i + 1], left[i + 1]))
    me = bpy.data.meshes.new("PCBS_Backdrop")
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    ob = _new_object(scene, "PCBS_Backdrop", me)

    mat = bpy.data.materials.get("PCBS_Backdrop_Mat") or bpy.data.materials.new("PCBS_Backdrop_Mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.55
    mat.diffuse_color = (*color, 1.0)
    me.materials.append(mat)
    return ob


def set_backdrop_color(color, rough=None, spec=None):
    mat = bpy.data.materials.get("PCBS_Backdrop_Mat")
    if mat and mat.node_tree:
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*color, 1.0)
            if rough is not None:
                bsdf.inputs["Roughness"].default_value = rough
            if spec is not None:
                for name in ("Specular IOR Level", "Specular"):
                    if name in bsdf.inputs:
                        bsdf.inputs[name].default_value = spec
                        break
        mat.diffuse_color = (*color, 1.0)


# ---------------------------------------------------------------- lighting looks

# Rims stay well away from az ~145 deg: that is the mirror direction of the default
# hero camera (az -35), where a glossy mask would turn into one big pale reflection.
# Each light: (name, azimuth deg, elevation deg, distance xS, size xS, power factor, colour, spread deg or None)
LOOKS = {
    "STUDIO_SOFT": dict(
        label="Studio soft", backdrop=(0.62, 0.62, 0.64), world=(0.18, 0.18, 0.20), world_strength=0.6,
        lights=[("Key", -45, 55, 4.0, 2.5, 1.00, (1.0, 0.97, 0.93), None),
                ("Fill", 60, 35, 4.5, 3.0, 0.35, (0.93, 0.96, 1.0), None),
                ("Rim", -175, 30, 4.0, 1.5, 0.80, (1.0, 1.0, 1.0), None)]),
}
LOOK_ITEMS = [(k, v["label"], "") for k, v in LOOKS.items()]


def _set_world(scene, color, strength):
    world = bpy.data.worlds.get("PCBS_World") or bpy.data.worlds.new("PCBS_World")
    world.use_nodes = True
    nt = world.node_tree
    bg = nt.nodes.get("Background")
    if bg is None:
        nt.nodes.clear()
        bg = nt.nodes.new("ShaderNodeBackground")
        out = nt.nodes.new("ShaderNodeOutputWorld")
        nt.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = strength
    world.color = color
    scene.world = world


def build_look(scene, look_key, centre, size, floor_z, backdrop_color=None):
    look = LOOKS[look_key]
    for ob in list(bpy.data.objects):
        if ob.name.startswith("PCBS_Light_"):
            _remove(ob.name)
    S = size
    target = Vector((centre.x, centre.y, floor_z + 0.1 * S))
    for (name, az, el, dist, lsize, pf, col, spread) in look["lights"]:
        a, e = math.radians(az), math.radians(el)
        # azimuth 0 = in front of the subject (-Y), positive = to the right (+X)
        d = dist * S
        pos = target + Vector((d * math.cos(e) * math.sin(a), -d * math.cos(e) * math.cos(a), d * math.sin(e)))
        lt = bpy.data.lights.new("PCBS_Light_" + name, "AREA")
        lt.shape = "DISK" if spread else "RECTANGLE"
        lt.size = lsize * S
        if not spread:
            lt.size_y = lsize * S * 0.6
        lt.color = col
        lt.energy = 25.0 * pf * d * d   # scale with distance^2 so looks are size-independent
        if spread:
            try:
                lt.spread = math.radians(spread)
                # a narrow spread concentrates the same power; compensate so looks stay balanced
                lt.energy *= 1.0 - math.cos(math.radians(spread) / 2.0)
            except AttributeError:
                pass
        ob = _new_object(scene, "PCBS_Light_" + name, lt)
        ob.location = pos
        direction = target - pos
        ob.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    _set_world(scene, look["world"], look["world_strength"])
    color = backdrop_color if backdrop_color is not None else look["backdrop"]
    set_backdrop_color(color, look.get("floor_rough", 0.55), look.get("floor_spec", 0.5))
    return look


# ---------------------------------------------------------------- camera

SHOTS = {
    "HERO":  dict(label="Hero 3/4",        az=-35, el=32, lens=85,  fstop=0,   fill=0.80),
    "TOP":   dict(label="Top-down",        az=0,   el=89.5, lens=85, fstop=0,  fill=0.85),
}
SHOT_ITEMS = [(k, v["label"], "") for k, v in SHOTS.items()]


def build_camera(scene, shot_key, centre, size, lo, hi):
    shot = SHOTS[shot_key]
    pivot = bpy.data.objects.get("PCBS_CamPivot")
    if pivot is None:
        pivot = _new_object(scene, "PCBS_CamPivot", None)
        pivot.empty_display_size = size * 0.3
    pivot.location = centre
    pivot.rotation_euler = (0, 0, 0)

    cam_data = bpy.data.cameras.get("PCBS_Camera") or bpy.data.cameras.new("PCBS_Camera")
    cam = bpy.data.objects.get("PCBS_Camera")
    if cam is None:
        cam = _new_object(scene, "PCBS_Camera", cam_data)
    cam.parent = pivot
    cam.matrix_parent_inverse = Matrix.Identity(4)
    cam_data.lens = shot["lens"]
    cam_data.sensor_width = 36.0
    cam_data.clip_start = size * 0.01
    cam_data.clip_end = size * 200.0

    a, e = math.radians(shot["az"]), math.radians(shot["el"])
    direction = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    from bpy_extras.object_utils import world_to_camera_view
    dist = (hi - lo).length * 2.0
    for _ in range(6):
        cam.location = direction * dist
        cam.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        ext = 0.0
        for c in corners:
            v = world_to_camera_view(scene, cam, c)
            ext = max(ext, abs(v.x - 0.5) * 2, abs(v.y - 0.5) * 2)
        if ext <= 1e-6:
            break
        # perspective: on-screen size ~ 1/distance; aim for 'fill' of the frame
        dist *= ext / shot["fill"] if shot["fill"] <= 1.0 else ext
    if shot["fill"] > 1.0:   # macro: move in closer than the full-board framing
        dist /= shot["fill"]
        cam.location = direction * dist
    # 'fill' < 1 leaves a margin around the board
    dof = cam_data.dof
    if shot["fstop"] > 0:
        dof.use_dof = True
        dof.focus_object = pivot
        dof.aperture_fstop = shot["fstop"]
        dof.aperture_blades = 7
    else:
        dof.use_dof = False
    scene.camera = cam
    return cam


# ---------------------------------------------------------------- turntable

def build_turntable(scene, frames):
    pivot = bpy.data.objects.get("PCBS_CamPivot")
    if pivot is None:
        return False
    pivot.animation_data_clear()
    scene.frame_start = 1
    scene.frame_end = frames
    pivot.rotation_euler = (0, 0, 0)
    pivot.keyframe_insert("rotation_euler", index=2, frame=1)
    pivot.rotation_euler = (0, 0, 2 * math.pi)
    pivot.keyframe_insert("rotation_euler", index=2, frame=frames + 1)
    _linear(pivot)
    return True


def _iter_fcurves(idblock):
    ad = idblock.animation_data
    if ad is None or ad.action is None:
        return []
    act = ad.action
    if hasattr(act, "fcurves") and len(getattr(act, "fcurves", [])):
        return list(act.fcurves)
    # Blender 4.4+/5.x layered actions
    curves = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            slot = ad.action_slot
            try:
                bag = strip.channelbag(slot)
            except Exception:
                bag = None
            if bag is not None:
                curves.extend(bag.fcurves)
    return curves


def _linear(idblock):
    for fc in _iter_fcurves(idblock):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


