# PCB Product Studio — quick guide

Studio lighting, circuit-board materials and product-shot cameras for Blender.
Turn a board exported from your PCB tool into a clean product render in a few clicks.

Tested on Blender 4.2 LTS and 5.2. Other versions may work but aren't tested. Renders with Cycles; a GPU is recommended.

*Not affiliated with or endorsed by the Blender Foundation or the KiCad project.
Blender is a registered trademark of the Blender Foundation.*

---

## 1. Install

1. In Blender: **Edit → Preferences → Get Extensions**.
2. Open the drop-down menu at the top right and choose **Install from Disk…**.
3. Pick the `.zip` you downloaded. Don't unzip it.
4. The **PCB Studio** tab appears in the 3D Viewport sidebar. Press **N** if the sidebar is hidden.

To update, install the newer zip the same way. It replaces the old version.

## 2. Export your board as GLB

Any tool that exports a glTF/GLB with the board and its 3D component models should work.
Tested with KiCad 10 (KiCad 8 and 9 also have this command but haven't been tested). On the command line:

```
kicad-cli pcb export glb -f -o myboard.glb --subst-models --include-tracks --include-pads ^
    --include-zones --include-silkscreen --include-soldermask myboard.kicad_pcb
```

On macOS or Linux, use `\` instead of `^` at the end of the first line.

The include options export copper, pads, mask and silkscreen as separate layers. PCB Studio
recognises these layers and gives each one its own material.

**Components missing?** If the export log says *Could not add 3D model*, the footprints point to
model files that aren't on your computer. Check your 3D model path settings in KiCad. Also check
that the referenced files exist, since some libraries ship `.step` files where older boards
reference `.wrl`.

## 3. One-click shot

1. **File → Import → glTF 2.0** and pick your `.glb`.
2. Select the imported objects. Click **Quick product shot**.
3. Press **F12** to render.

Quick product shot detects the board and lays it flat. It then assigns PCB materials, builds a
cyclorama studio, frames a hero camera and sets draft render settings.

## 4. Panels

| Panel | What it does |
|---|---|
| **1. Subject** | **Set subject from selection** picks what gets lit and framed. **Board** is the bare PCB, picked automatically. **Fix scale** helps if the board imported 1000× too big. **Flip** turns the board over. |
| **2. Materials** | Pick the **Solder mask** colour and **Pad finish** (HASL, ENIG or bare copper). **Scan** lists every material with a guessed preset. Change any row, then **Apply**. **Restore** puts the original materials back. |
| **3. Studio** | **Look** sets the lighting style: Studio soft, White e-commerce, Dark hero or Tech glow. **Backdrop** sets the sweep colour. **Build studio** rebuilds the lights and backdrop. |
| **4. Camera and animation** | **Shot**: Hero 3/4, Top-down, Low angle, Front or Macro. **Turntable** makes a 360° spin over *Frames*. **Explode** lifts components off the board, and **Animate** keys the lift. Use the *Explode amount* slider for stills. |
| **5. Render** | Choose **Quality** (Preview, Draft or Final) and **Size** (HD, QHD, 4K, square, 4:5 social or 3:2 photo). **Transparent background** turns the floor into a shadow catcher for PNGs with alpha. **Use GPU** (one click) picks OptiX, CUDA, HIP, oneAPI or Metal. |

## 5. Tips

- **Listing photos:** White e-commerce look, Top-down or Hero shot, Square size, Final quality.
- **Hero banner:** Dark hero look, Hero shot, QHD or 4K. Add an exploded still for a feature image.
- **Videos:** use Turntable with 120–240 frames. Set the output to FFmpeg in Blender's Output properties.
- **Render times:** in our test on an RTX 5060 laptop, a 1080p Draft took about 10–30 seconds. Your time will
  vary with your GPU and board. Final is slower and cleaner. On CPU, use Preview to set up the shot and Final only
  for the last render.
- **Everything stays editable:** the lights, camera and materials are ordinary Blender objects
  named `PCBS_*`. Tweak them by hand after the add-on builds them.

## 6. Editions

| | Lite (free) | Full |
|---|---|---|
| Looks | Studio soft | + White e-commerce, Dark hero, Tech glow |
| Shots | Hero, Top-down | + Low angle, Front, Macro (with depth of field) |
| Solder mask colours | Green, black, blue | + red, white, purple, yellow |
| Exploded view | — | ✓ (still and animated) |
| Turntable | ✓ | ✓ |
| Sizes | HD, Square | + QHD, 4K, 4:5 social, 3:2 photo |

## 7. What this is not

A visualization tool. Renders are not an engineering check of a PCB design (no DRC, electrical or
manufacturing verification).

## 8. Licence

The add-on code is free software under the GNU GPL v3 or later (see `LICENSE`). All materials are
procedural, and the add-on ships no third-party textures, HDRIs or models. Renders you make with
it are yours.

The name "PCB Product Studio" is not licensed under the GPL; forks should use a different name.

## 9. Support

Email pcbproductstudio@gmail.com. Report problems with your Blender version, OS, GPU and, if you can, the `.glb` that misbehaves.
