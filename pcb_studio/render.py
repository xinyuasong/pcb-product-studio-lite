# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Richard Song
"""Render presets tuned for small product scenes on 8 GB GPUs."""
import bpy

QUALITY = {
    "PREVIEW": dict(label="Preview (fast)", samples=32, threshold=0.1, bounces=6),
    "DRAFT":   dict(label="Draft", samples=128, threshold=0.05, bounces=8),
    "FINAL":   dict(label="Final", samples=512, threshold=0.01, bounces=12),
}
QUALITY_ITEMS = [(k, v["label"], "") for k, v in QUALITY.items()]

RESOLUTIONS = {
    "HD":     ("1920 x 1080 (16:9)", 1920, 1080),
    "SQUARE": ("2048 x 2048 (square listing)", 2048, 2048),
}
RES_ITEMS = [(k, v[0], "") for k, v in RESOLUTIONS.items()]


def set_resolution(scene, key):
    _, x, y = RESOLUTIONS[key]
    scene.render.resolution_x = x
    scene.render.resolution_y = y
    scene.render.resolution_percentage = 100


def apply_quality(scene, key, transparent=False):
    q = QUALITY[key]
    scene.render.engine = "CYCLES"
    c = scene.cycles
    c.samples = q["samples"]
    c.use_adaptive_sampling = True
    c.adaptive_threshold = q["threshold"]
    c.use_denoising = True
    try:
        c.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    c.max_bounces = q["bounces"]
    c.glossy_bounces = min(8, q["bounces"])
    c.transmission_bounces = q["bounces"]
    c.caustics_reflective = False
    c.caustics_refractive = False
    c.sample_clamp_indirect = 10.0
    scene.render.use_persistent_data = True
    scene.render.film_transparent = transparent
    bd = bpy.data.objects.get("PCBS_Backdrop")
    if bd is not None:
        bd.is_shadow_catcher = transparent
    _color_management(scene)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"


def _color_management(scene):
    vs = scene.view_settings
    for vt in ("AgX", "Filmic"):
        try:
            vs.view_transform = vt
            break
        except TypeError:
            continue
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Base Contrast", "None"):
        try:
            vs.look = look
            break
        except TypeError:
            continue


def use_gpu(scene):
    """Enable the best GPU backend. Returns a description or None."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return None
    for backend in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.refresh_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend
            scene.cycles.device = "GPU"
            return "%s: %s" % (backend, ", ".join(d.name for d in gpus))
    scene.cycles.device = "CPU"
    return None
