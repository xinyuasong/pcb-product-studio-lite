# SPDX-License-Identifier: GPL-3.0-or-later
# PCB Product Studio - studio lighting, PCB materials and product-shot cameras for KiCad boards.
# Copyright (C) 2026 Richard Song
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version. It is distributed WITHOUT ANY WARRANTY; see
# <https://www.gnu.org/licenses/>.

bl_info = {
    "name": "PCB Product Studio",
    "author": "Richard Song",
    "version": (0, 1, 8),
    "blender": (4, 2, 0),
    "location": "3D Viewport > Sidebar > PCB Studio",
    "description": "Studio lighting, PCB materials and product-shot cameras for circuit boards",
    "category": "Render",
}

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)

from . import materials, studio, render, edition
from .edition import keep, LITE


# ================================================================ properties

class PCBS_SubjectItem(bpy.types.PropertyGroup):
    obj: PointerProperty(type=bpy.types.Object)


class PCBS_MatItem(bpy.types.PropertyGroup):
    mat_name: StringProperty()
    preset: EnumProperty(name="Preset", items=materials.PRESET_ITEMS, default="KEEP")


def _look_update(self, context):
    look = studio.LOOKS[self.look]
    self.backdrop_color = look["backdrop"]


class PCBS_Props(bpy.types.PropertyGroup):
    subject: CollectionProperty(type=PCBS_SubjectItem)
    board: PointerProperty(type=bpy.types.Object, name="Board",
                           description="The board itself (everything else is treated as a component)")
    mats: CollectionProperty(type=PCBS_MatItem)
    mats_index: IntProperty()
    mask: EnumProperty(name="Solder mask", items=keep([(k, materials.PRESETS[k][0].split(": ")[1].capitalize(), "")
                                                       for k in materials.MASK_KEYS], edition.LITE_MASKS),
                       default="MASK_GREEN")
    finish: EnumProperty(name="Pad finish", items=[("HASL", "HASL (tin)", ""), ("ENIG", "ENIG (gold)", ""),
                                                   ("COPPER", "Bare copper", "")], default="HASL")
    look: EnumProperty(name="Look", items=keep(studio.LOOK_ITEMS, edition.LITE_LOOKS), default="STUDIO_SOFT", update=_look_update)
    backdrop_color: FloatVectorProperty(name="Backdrop", subtype="COLOR", size=3, min=0, max=1,
                                        default=(0.62, 0.62, 0.64))
    shot: EnumProperty(name="Shot", items=keep(studio.SHOT_ITEMS, edition.LITE_SHOTS), default="HERO")
    frames: IntProperty(name="Frames", default=120, min=24, max=1200)
    quality: EnumProperty(name="Quality", items=render.QUALITY_ITEMS, default="DRAFT")
    resolution: EnumProperty(name="Size", items=keep(render.RES_ITEMS, edition.LITE_RES), default="HD")
    transparent: BoolProperty(name="Transparent background", default=False,
                              description="Render with alpha; the backdrop becomes a shadow catcher")


# ================================================================ helpers

def _bounds(scene):
    obs = studio.subject_objects(scene)
    lo, hi = studio.world_bounds(obs)
    centre = (lo + hi) / 2.0
    size = max(hi.x - lo.x, hi.y - lo.y, 1e-4)
    return obs, lo, hi, centre, size


def _need_subject(op, scene):
    if not studio.subject_objects(scene):
        op.report({"ERROR"}, "Set the subject first (step 1)")
        return False
    return True


# ================================================================ operators

class PCBS_OT_set_subject(bpy.types.Operator):
    """Use the selected objects (or every mesh in the scene) as the board to shoot"""
    bl_idname = "pcbs.set_subject"
    bl_label = "Set subject from selection"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.pcbs
        sel = [o for o in getattr(context, "selected_objects", None) or [] if o.type in {"MESH", "EMPTY"}]
        pool = sel if sel else [o for o in scene.objects if o.type == "MESH" and not o.name.startswith("PCBS_")]
        # include children of selected empties (glTF/VRML imports are nested)
        obs = []
        for o in pool:
            for c in [o] + list(o.children_recursive):
                if c.type == "MESH" and not c.name.startswith("PCBS_") and c not in obs:
                    obs.append(c)
        if not obs:
            self.report({"ERROR"}, "No mesh objects found. Import your board first")
            return {"CANCELLED"}
        props.subject.clear()
        for o in obs:
            props.subject.add().obj = o
        props.board = studio.detect_board(obs)
        for o in obs:   # KiCad GLB: match the mask colour the board was designed with
            if studio.layer_role(o) == "mask" and o.material_slots and o.material_slots[0].material:
                src = o.material_slots[0].material
                orig = o.get("pcbs_original_mats")
                if orig:
                    src = bpy.data.materials.get(orig[0]) or src
                if not src.name.startswith(materials.PREFIX):
                    props.mask = materials.closest_mask(src)
                break
        turned = studio.lay_flat(obs, props.board)
        lo, hi = studio.world_bounds(obs)
        size = max(hi.x - lo.x, hi.y - lo.y)
        msg = "%d objects; board: %s; size %.1f mm" % (len(obs), props.board.name if props.board else "?", size * 1000)
        if turned:
            msg += "; turned flat (%s)" % ", ".join(turned)
        if size > 2.0:
            msg += "  (looks like millimetres used as metres: use 'Fix scale')"
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class PCBS_OT_fix_scale(bpy.types.Operator):
    """Scale the subject by 0.001 (for imports where millimetres became metres)"""
    bl_idname = "pcbs.fix_scale"
    bl_label = "Fix scale (mm to m)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obs = studio.subject_objects(context.scene)
        roots = [o for o in obs if o.parent is None or o.parent not in obs]
        tops = set()
        for o in roots:
            r = o
            while r.parent is not None:
                r = r.parent
            tops.add(r)
        for r in tops:
            r.scale = r.scale * 0.001
            r.location = r.location * 0.001
        context.view_layer.update()
        self.report({"INFO"}, "Scaled %d root object(s) by 0.001" % len(tops))
        return {"FINISHED"}


class PCBS_OT_flip(bpy.types.Operator):
    """Turn the board over (show the other side)"""
    bl_idname = "pcbs.flip"
    bl_label = "Flip board"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import math
        from mathutils import Matrix
        obs = studio.subject_objects(context.scene)
        if not obs:
            return {"CANCELLED"}
        lo, hi = studio.world_bounds(obs)
        c = (lo + hi) / 2.0
        M = Matrix.Translation(c) @ Matrix.Rotation(math.pi, 4, "Y") @ Matrix.Translation(-c)
        for r in studio.top_roots(obs):
            r.matrix_world = M @ r.matrix_world
        context.view_layer.update()
        return {"FINISHED"}


class PCBS_OT_scan_materials(bpy.types.Operator):
    """List the subject's materials with a suggested PCB preset for each"""
    bl_idname = "pcbs.scan_materials"
    bl_label = "Scan materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if not _need_subject(self, scene):
            return {"CANCELLED"}
        props = scene.pcbs
        obs = studio.subject_objects(scene)
        # make sure we scan originals, not our own presets
        mats = []
        for ob in obs:
            originals = ob.get("pcbs_original_mats")
            names = list(originals) if originals else [s.material.name for s in ob.material_slots if s.material]
            for n in names:
                m = bpy.data.materials.get(n)
                if m is not None and m not in mats and not m.name.startswith(materials.PREFIX):
                    mats.append(m)
        parts = set(studio.board_parts(obs, props.board))
        role_of = {}
        board_mats, comp_mats = set(), set()
        for ob in obs:
            originals = ob.get("pcbs_original_mats")
            names = set(originals) if originals else {sl.material.name for sl in ob.material_slots if sl.material}
            role = studio.layer_role(ob)
            if ob in parts:
                board_mats |= names
                if role:
                    for n in names:
                        role_of.setdefault(n, role)
            else:
                comp_mats |= names
        # how much surface each component material covers, relative to the board footprint
        lo, hi = studio.world_bounds(obs)
        board_area = max((hi.x - lo.x) * (hi.y - lo.y), 1e-9)
        area = {}
        for ob in obs:
            if ob in parts or ob.type != "MESH" or ob.data is None:
                continue
            sx, sy, sz = ob.matrix_world.to_scale()
            k = abs(sx * sy + sy * sz + sx * sz) / 3.0
            originals = ob.get("pcbs_original_mats")
            if originals:
                slots = list(originals)      # measure the board's own materials, not our presets
            else:
                slots = [sl.material.name if sl.material else None for sl in ob.material_slots]
            for poly in ob.data.polygons:
                if poly.material_index < len(slots) and slots[poly.material_index]:
                    n = slots[poly.material_index]
                    area[n] = area.get(n, 0.0) + poly.area * k
        props.mats.clear()
        for m in mats:
            it = props.mats.add()
            it.mat_name = m.name
            preset = None
            if m.name in role_of and m.name not in comp_mats:
                preset = materials.preset_for_layer(role_of[m.name], m, props.mask, props.finish)
            if preset is None:
                on_board = m.name in board_mats and m.name not in comp_mats
                preset = materials.guess_preset(m, props.mask, on_board,
                                                area_frac=area.get(m.name, 0.0) / board_area)
            it.preset = preset
        self.report({"INFO"}, "%d materials found" % len(mats))
        return {"FINISHED"}


class PCBS_OT_apply_materials(bpy.types.Operator):
    """Replace the subject's materials with the chosen PCB presets (originals are kept)"""
    bl_idname = "pcbs.apply_materials"
    bl_label = "Apply materials"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if not _need_subject(self, scene):
            return {"CANCELLED"}
        props = scene.pcbs
        if not props.mats:
            bpy.ops.pcbs.scan_materials()
        mapping = {it.mat_name: it.preset for it in props.mats}
        # the mask colour dropdown overrides every mask preset
        for k, v in mapping.items():
            if v in materials.MASK_KEYS:
                mapping[k] = props.mask
        n = materials.apply_mapping(studio.subject_objects(scene), mapping, props.mask)
        self.report({"INFO"}, "%d material slots updated" % n)
        return {"FINISHED"}


class PCBS_OT_restore_materials(bpy.types.Operator):
    """Put the original imported materials back"""
    bl_idname = "pcbs.restore_materials"
    bl_label = "Restore originals"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        n = materials.restore_materials(studio.subject_objects(context.scene))
        self.report({"INFO"}, "%d slots restored" % n)
        return {"FINISHED"}


class PCBS_OT_build_studio(bpy.types.Operator):
    """Add (or rebuild) the backdrop and the chosen lighting look around the subject"""
    bl_idname = "pcbs.build_studio"
    bl_label = "Build studio"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if not _need_subject(self, scene):
            return {"CANCELLED"}
        props = scene.pcbs
        obs, lo, hi, centre, size = _bounds(scene)
        studio.build_backdrop(scene, centre, size, lo.z, tuple(props.backdrop_color))
        studio.build_look(scene, props.look, centre, size, lo.z, tuple(props.backdrop_color))
        return {"FINISHED"}


class PCBS_OT_set_shot(bpy.types.Operator):
    """Place the studio camera for the chosen shot, framed to the subject"""
    bl_idname = "pcbs.set_shot"
    bl_label = "Set camera"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if not _need_subject(self, scene):
            return {"CANCELLED"}
        props = scene.pcbs
        render.set_resolution(scene, props.resolution)
        obs, lo, hi, centre, size = _bounds(scene)
        studio.build_camera(scene, props.shot, centre, size, lo, hi)
        return {"FINISHED"}


class PCBS_OT_turntable(bpy.types.Operator):
    """Animate the camera in a seamless 360 degree loop around the board"""
    bl_idname = "pcbs.turntable"
    bl_label = "Turntable"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if bpy.data.objects.get("PCBS_CamPivot") is None:
            bpy.ops.pcbs.set_shot()
        studio.build_turntable(scene, scene.pcbs.frames)
        return {"FINISHED"}




class PCBS_OT_render_settings(bpy.types.Operator):
    """Apply the render quality, size and background settings"""
    bl_idname = "pcbs.render_settings"
    bl_label = "Apply render settings"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        props = scene.pcbs
        render.set_resolution(scene, props.resolution)
        render.apply_quality(scene, props.quality, props.transparent)
        return {"FINISHED"}


class PCBS_OT_use_gpu(bpy.types.Operator):
    """Render on your NVIDIA/AMD/Intel/Apple GPU (changes Cycles preferences)"""
    bl_idname = "pcbs.use_gpu"
    bl_label = "Use GPU"

    def execute(self, context):
        desc = render.use_gpu(context.scene)
        if desc:
            self.report({"INFO"}, "Rendering on " + desc)
        else:
            self.report({"WARNING"}, "No supported GPU found; using CPU")
        return {"FINISHED"}


class PCBS_OT_quick_shot(bpy.types.Operator):
    """One click: subject, materials, studio, hero camera and draft render settings"""
    bl_idname = "pcbs.quick_shot"
    bl_label = "Quick product shot"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        scene = context.scene
        if not studio.subject_objects(scene):
            bpy.ops.pcbs.set_subject()
        if not studio.subject_objects(scene):
            return {"CANCELLED"}
        bpy.ops.pcbs.scan_materials()
        bpy.ops.pcbs.apply_materials()
        bpy.ops.pcbs.build_studio()
        bpy.ops.pcbs.set_shot()
        bpy.ops.pcbs.render_settings()
        self.report({"INFO"}, "Ready: press F12 to render")
        return {"FINISHED"}


# ================================================================ UI

class PCBS_UL_mats(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        m = bpy.data.materials.get(item.mat_name)
        row = layout.row(align=True)
        if m is not None:
            row.prop(m, "diffuse_color", text="")
        row.label(text=item.mat_name)
        row.prop(item, "preset", text="")


class PCBS_PT_main(bpy.types.Panel):
    bl_label = "PCB Product Studio"
    bl_idname = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        col = self.layout.column()
        col.scale_y = 1.4
        col.operator("pcbs.quick_shot", icon="RENDER_STILL")
        self.layout.label(text="Import your board (File > Import > glTF), select it, click above.")
        if LITE:
            box = self.layout.box()
            box.label(text="Lite edition", icon="INFO")
            box.label(text="Full: 4 looks, 5 shots, exploded view,")
            box.label(text="7 mask colours, 4K and social sizes.")


class PCBS_PT_subject(bpy.types.Panel):
    bl_label = "1. Subject"
    bl_parent_id = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        l = self.layout
        l.operator("pcbs.set_subject", icon="RESTRICT_SELECT_OFF")
        l.label(text="%d objects in subject" % len([i for i in p.subject if i.obj]))
        l.prop(p, "board")
        row = l.row(align=True)
        row.operator("pcbs.fix_scale", icon="FULLSCREEN_EXIT")
        row.operator("pcbs.flip", icon="FILE_REFRESH")


class PCBS_PT_materials(bpy.types.Panel):
    bl_label = "2. Materials"
    bl_parent_id = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        l = self.layout
        l.prop(p, "mask")
        l.prop(p, "finish")
        row = l.row(align=True)
        row.operator("pcbs.scan_materials", icon="VIEWZOOM")
        row.operator("pcbs.apply_materials", icon="MATERIAL")
        l.template_list("PCBS_UL_mats", "", p, "mats", p, "mats_index", rows=4)
        l.operator("pcbs.restore_materials", icon="LOOP_BACK")


class PCBS_PT_studio(bpy.types.Panel):
    bl_label = "3. Studio"
    bl_parent_id = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        l = self.layout
        l.prop(p, "look")
        l.prop(p, "backdrop_color")
        l.operator("pcbs.build_studio", icon="LIGHT_AREA")


class PCBS_PT_camera(bpy.types.Panel):
    bl_label = "4. Camera and animation"
    bl_parent_id = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        l = self.layout
        l.prop(p, "shot")
        l.operator("pcbs.set_shot", icon="CAMERA_DATA")
        l.separator()
        l.prop(p, "frames")
        l.operator("pcbs.turntable", icon="FILE_REFRESH")


class PCBS_PT_render(bpy.types.Panel):
    bl_label = "5. Render"
    bl_parent_id = "PCBS_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "PCB Studio"

    def draw(self, context):
        p = context.scene.pcbs
        l = self.layout
        l.prop(p, "quality")
        l.prop(p, "resolution")
        l.prop(p, "transparent")
        row = l.row(align=True)
        row.operator("pcbs.render_settings", icon="SETTINGS")
        row.operator("pcbs.use_gpu", icon="MEMORY")
        l.operator("render.render", text="Render image (F12)", icon="RENDER_STILL")


classes = (PCBS_SubjectItem, PCBS_MatItem, PCBS_Props,
           PCBS_OT_set_subject, PCBS_OT_fix_scale, PCBS_OT_flip, PCBS_OT_scan_materials, PCBS_OT_apply_materials,
           PCBS_OT_restore_materials, PCBS_OT_build_studio, PCBS_OT_set_shot, PCBS_OT_turntable,
           PCBS_OT_render_settings, PCBS_OT_use_gpu,
           PCBS_OT_quick_shot, PCBS_UL_mats,
           PCBS_PT_main, PCBS_PT_subject, PCBS_PT_materials, PCBS_PT_studio, PCBS_PT_camera, PCBS_PT_render)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.pcbs = PointerProperty(type=PCBS_Props)


def unregister():
    del bpy.types.Scene.pcbs
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
