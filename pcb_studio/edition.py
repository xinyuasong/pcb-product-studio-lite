# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Richard Song
"""Which edition this build is. The build script flips LITE for the free download."""
LITE = True

# what the free Lite edition keeps
LITE_LOOKS = ("STUDIO_SOFT",)
LITE_SHOTS = ("HERO", "TOP")
LITE_MASKS = ("MASK_GREEN", "MASK_BLACK", "MASK_BLUE")
LITE_RES = ("HD", "SQUARE")


def keep(items, allowed):
    """Filter enum items to the edition's set (full edition keeps everything)."""
    return [i for i in items if i[0] in allowed] if LITE else list(items)
