# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Richard Song
"""Procedural PCB and component materials (no image textures)."""
import bpy
import colorsys

PREFIX = "PCBS_"

# key: (label, group, params)
# params: base, metallic, roughness, coat, coat_rough, bump, bump_scale, extra
PRESETS = {
    # --- solder mask ---
    "MASK_GREEN":  ("Solder mask: green",  "mask", dict(base=(0.006, 0.090, 0.022), rough=0.32, coat=1.0, coat_rough=0.06, bump=0.08, scale=900)),
    "MASK_BLACK":  ("Solder mask: matte black", "mask", dict(base=(0.012, 0.012, 0.013), rough=0.55, coat=0.6, coat_rough=0.25, bump=0.06, scale=900)),
    "MASK_BLUE":   ("Solder mask: blue",   "mask", dict(base=(0.004, 0.025, 0.150), rough=0.30, coat=1.0, coat_rough=0.06, bump=0.08, scale=900)),
    # --- finishes / copper ---
    "ENIG":        ("Finish: ENIG gold",   "metal", dict(base=(1.000, 0.766, 0.336), metallic=1.0, rough=0.18, bump=0.05, scale=1500)),
    "HASL":        ("Finish: HASL tin",    "metal", dict(base=(0.820, 0.820, 0.840), metallic=1.0, rough=0.12, bump=0.25, scale=400)),
    "COPPER":      ("Bare copper",         "metal", dict(base=(0.955, 0.637, 0.538), metallic=1.0, rough=0.28, bump=0.05, scale=1500)),
    # --- silkscreen / substrate ---
    "SILK_WHITE":  ("Silkscreen: white",   "plain", dict(base=(0.880, 0.880, 0.860), rough=0.65, bump=0.15, scale=2500)),
    "SILK_BLACK":  ("Silkscreen: black",   "plain", dict(base=(0.015, 0.015, 0.015), rough=0.65, bump=0.15, scale=2500)),
    "FR4":         ("Board edge: FR4",     "plain", dict(base=(0.420, 0.380, 0.200), rough=0.75, bump=0.30, scale=300, sss=0.15)),
    # --- components ---
    "IC_EPOXY":    ("Component: IC epoxy", "plain", dict(base=(0.018, 0.018, 0.020), rough=0.42, bump=0.20, scale=3000)),
    "PLASTIC_BLK": ("Component: black plastic", "plain", dict(base=(0.025, 0.025, 0.025), rough=0.35, bump=0.04, scale=800)),
    "PLASTIC_WHT": ("Component: white plastic", "plain", dict(base=(0.800, 0.790, 0.760), rough=0.40, bump=0.04, scale=800)),
    "CERAMIC":     ("Component: ceramic (MLCC)", "plain", dict(base=(0.420, 0.300, 0.180), rough=0.55, bump=0.10, scale=2000)),
    "TIN":         ("Component: tin leads", "metal", dict(base=(0.850, 0.850, 0.860), metallic=1.0, rough=0.22, bump=0.05, scale=1500)),
    "GOLD_PIN":    ("Component: gold pins", "metal", dict(base=(1.000, 0.766, 0.336), metallic=1.0, rough=0.15, bump=0.02, scale=1500)),
    "ALUMINIUM":   ("Component: aluminium can", "metal", dict(base=(0.910, 0.920, 0.925), metallic=1.0, rough=0.30, bump=0.02, scale=800, aniso=0.6)),
    "LED_CLEAR":   ("Component: clear LED dome", "glass", dict(base=(0.950, 0.950, 0.950), rough=0.05)),
    "MASK_COPPER": ("Copper under solder mask", "mask_cu", dict(rough=0.36, coat=1.0, coat_rough=0.05, bump=0.06, scale=900)),
    "PLASTIC_COLOR": ("Component: glossy plastic (keep colour)", "plastic_color", dict(rough=0.30, bump=0.03, scale=800)),
    "KEEP":        ("Keep original material", "keep", dict()),
}

PRESET_ITEMS = [(k, v[0], "") for k, v in PRESETS.items()]
MASK_KEYS = [k for k, v in PRESETS.items() if v[1] == "mask"]


def _set(node, names, value):
    """Set the first matching input (names differ between Blender versions)."""
    for n in names:
        sock = node.inputs.get(n)
        if sock is not None:
            sock.default_value = value
            return True
    return False


def build_material(key, source=None, mask_key=None):
    """Return a PCBS_ material for a preset, creating it if needed.
    PLASTIC_COLOR makes one material per source material so its colour is kept."""
    label, group, p = PRESETS[key]
    name = PREFIX + key
    if group == "mask_cu":
        # tracks/zones under the mask: the mask colour, a little lighter (the classic visible-trace look)
        mk = mask_key or "MASK_GREEN"
        base = PRESETS[mk][2]["base"]
        lift = 0.05 if mk == "MASK_WHITE" else 0.0
        p = dict(p, base=tuple(min(1.0, c * 1.6 + 0.015 + lift) for c in base))
        name = PREFIX + "COPPER_UNDER_" + mk
    if group == "plastic_color" and source is not None:
        name = PREFIX + "PLASTIC_" + source.name
        p = dict(p, base=tuple(_mat_color(source)))
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    nt.links.new(bsdf.outputs[0], out.inputs[0])

    base = p.get("base", (0.8, 0.8, 0.8))
    _set(bsdf, ["Base Color"], (*base, 1.0))
    _set(bsdf, ["Metallic"], p.get("metallic", 0.0))
    _set(bsdf, ["Roughness"], p.get("rough", 0.5))
    if p.get("coat"):
        _set(bsdf, ["Coat Weight", "Clearcoat"], p["coat"])
        _set(bsdf, ["Coat Roughness", "Clearcoat Roughness"], p.get("coat_rough", 0.05))
    if p.get("sss"):
        _set(bsdf, ["Subsurface Weight", "Subsurface"], p["sss"])
        _set(bsdf, ["Subsurface Radius"], (0.002, 0.0015, 0.001))
    if p.get("aniso"):
        _set(bsdf, ["Anisotropic"], p["aniso"])
    if group in ("mask", "mask_cu"):
        # the clear coat carries the gloss; a strong rough base specular washes the colour out
        # into a broad pale sheen at 3/4 angles, so keep the base layer's specular low
        _set(bsdf, ["Specular IOR Level", "Specular"], 0.12)
    if group == "mask" and key not in ("MASK_BLACK", "MASK_WHITE"):
        # real solder mask is slightly translucent: copper traces show through
        _set(bsdf, ["Alpha"], 0.97)
    if group == "glass":
        _set(bsdf, ["Transmission Weight", "Transmission"], 1.0)
        _set(bsdf, ["IOR"], 1.5)

    # Fine procedural micro-surface: noise -> bump (scale is per metre; boards are small)
    if p.get("bump"):
        tex = nt.nodes.new("ShaderNodeTexCoord")
        tex.location = (-650, -200)
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.location = (-450, -200)
        noise.inputs["Scale"].default_value = p.get("scale", 1000)
        _set(noise, ["Detail"], 6.0)
        bump = nt.nodes.new("ShaderNodeBump")
        bump.location = (-200, -200)
        bump.inputs["Strength"].default_value = p["bump"]
        _set(bump, ["Distance"], 0.00005)
        nt.links.new(tex.outputs["Object"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        if p.get("coat"):
            coat_n = bsdf.inputs.get("Coat Normal")
            if coat_n is not None:
                # keep the clear coat smooth so the mask looks glossy
                pass

    mat.diffuse_color = (*base, 1.0)  # viewport colour
    mat.metallic = p.get("metallic", 0.0)
    mat.roughness = p.get("rough", 0.5)
    mat["pcbs_preset"] = key
    return mat


# ---------- guessing presets for imported materials ----------

KEYWORDS = [
    (("silk", "legend", "overlay"), "SILK_WHITE"),
    (("mask", "soldermask", "solder_mask"), "MASK_GREEN"),
    (("enig", "gold", "au"), "ENIG"),
    (("hasl", "tin", "solder", "lead", "pin"), "TIN"),
    (("copper", "pad", "via", "cu"), "COPPER"),
    (("fr4", "substrate", "core", "board", "pcb_body", "edge"), "FR4"),
    (("led", "lens", "glass", "transparent"), "LED_CLEAR"),
    (("ceramic", "capacitor", "cap"), "CERAMIC"),
    (("alu", "aluminium", "aluminum", "can"), "ALUMINIUM"),
    (("epoxy", "ic", "chip", "body", "package"), "IC_EPOXY"),
    (("plastic", "connector", "housing"), "PLASTIC_BLK"),
]


def _to_srgb(c):
    """Linear -> sRGB, so colour guesses match what the user sees in KiCad."""
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _mat_color(mat):
    col = None
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                s = n.inputs.get("Base Color")
                if s is not None and not s.is_linked:
                    col = tuple(s.default_value[:3])
                break
    if col is None:
        col = tuple(mat.diffuse_color[:3])
    return col


def _mat_metallic(mat):
    if mat.use_nodes and mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                s = n.inputs.get("Metallic")
                if s is not None:
                    return s.default_value
    return mat.metallic


def guess_preset(mat, mask_key="MASK_GREEN", on_board=False, area_frac=0.0):
    """Best-effort guess from the material name, then its colour.
    Colours are read as stored (KiCad writes its display colours straight into exports)."""
    name = mat.name.lower().replace("-", "_").replace(" ", "_")
    tokens = set(t for t in name.replace(".", "_").split("_") if t)
    for words, key in KEYWORDS:
        for w in words:
            if (len(w) <= 3 and w in tokens) or (len(w) > 3 and w in name):
                if key == "MASK_GREEN":
                    return mask_key
                if key == "SILK_WHITE" and not on_board:
                    return "PLASTIC_WHT"
                return key
    r, g, b = _mat_color(mat)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if on_board:
        if l > 0.70 and s < 0.30:
            return "SILK_WHITE"
        if 0.07 < h < 0.17 and s > 0.45 and 0.35 < l < 0.75:
            return "ENIG"
        if s < 0.20 and 0.35 < l <= 0.70:
            return "HASL"
        if 0.04 < h < 0.11 and s > 0.35 and 0.30 < l < 0.70:
            return "COPPER"
        if 0.10 < h < 0.20 and l < 0.45 and s < 0.45:
            return "FR4"
        return mask_key
    # components
    if l < 0.13:
        return "IC_EPOXY"
    if l > 0.85 and s < 0.25:
        return "PLASTIC_WHT"
    # a big, warm off-white surface is a natural nylon connector body, not metal
    if area_frac > 0.03 and s >= 0.15 and l > 0.55 and 0.08 < h < 0.22:
        return "PLASTIC_COLOR"
    if s < 0.30 and 0.30 < l <= 0.85:
        return "TIN"
    if 0.07 < h < 0.17 and s > 0.60 and 0.35 < l < 0.65:
        return "GOLD_PIN"
    if 0.06 < h < 0.16 and 0.30 <= s <= 0.75 and l >= 0.55:
        return "CERAMIC"
    return "PLASTIC_COLOR"


MASK_REF = {
    "MASK_GREEN": (0.06, 0.16, 0.11), "MASK_BLACK": (0.03, 0.03, 0.03), "MASK_BLUE": (0.02, 0.10, 0.45),
}


def closest_mask(mat):
    """Pick the mask preset nearest to an imported mask colour (KiCad writes its board colour)."""
    c = _mat_color(mat)
    best, bd = "MASK_GREEN", 1e9
    for k, ref in MASK_REF.items():
        d = sum((a - b) ** 2 for a, b in zip(c, ref))
        if d < bd:
            best, bd = k, d
    return best


def preset_for_layer(role, mat, mask_key, finish_key):
    if role == "mask":
        return mask_key
    if role == "silk":
        if mask_key == "MASK_WHITE":
            return "SILK_BLACK"          # white boards use black silkscreen
        r, g, b = _mat_color(mat)
        return "SILK_BLACK" if (r + g + b) / 3 < 0.3 else "SILK_WHITE"
    if role == "pad":
        return finish_key
    if role in ("copper", "via"):
        return "MASK_COPPER"
    if role == "body":
        return "FR4"
    return None


def collect_materials(objects):
    seen = []
    for ob in objects:
        if ob.type != "MESH":
            continue
        for slot in ob.material_slots:
            m = slot.material
            if m is not None and not m.name.startswith(PREFIX) and m not in seen:
                seen.append(m)
    return seen


def apply_mapping(objects, mapping, mask_key=None):
    """mapping: {original material name: preset key}. Originals are kept for restore."""
    count = 0
    for ob in objects:
        if ob.type != "MESH":
            continue
        originals = list(ob.get("pcbs_original_mats", []))
        if not originals:
            originals = [s.material.name if s.material else "" for s in ob.material_slots]
            ob["pcbs_original_mats"] = originals
        for i, slot in enumerate(ob.material_slots):
            orig_name = originals[i] if i < len(originals) else (slot.material.name if slot.material else "")
            key = mapping.get(orig_name)
            if not key or key == "KEEP":
                continue
            src = bpy.data.materials.get(orig_name)
            new = build_material(key, src, mask_key)
            if slot.link == "OBJECT":
                slot.material = new
            else:
                # assign on the object so shared mesh data is untouched
                slot.link = "OBJECT"
                slot.material = new
            count += 1
    return count


def restore_materials(objects):
    n = 0
    for ob in objects:
        originals = ob.get("pcbs_original_mats")
        if not originals:
            continue
        for i, slot in enumerate(ob.material_slots):
            if i < len(originals) and originals[i]:
                m = bpy.data.materials.get(originals[i])
                if m is not None:
                    slot.link = "OBJECT"
                    slot.material = m
                    slot.link = "DATA"
                    n += 1
        del ob["pcbs_original_mats"]
    return n
