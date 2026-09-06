# Eye overlay generation prompt

This is a strict character-preserving image editing task for one frame in a 72-direction browser-avatar eye sequence.

Attached references, in order:
1. `assistant_master.png`: immutable full-character master and coordinate reference.
2. `assistant_eyes_identity.png`: immutable eye identity and rendering-style reference.
3. `target_[ANGLE].png`: exact gaze target. Do not reproduce the guide.
4. Optional approved neighboring anchor frames for interpolation.

Target output: `[FRAME_NAME]`
Target angle: `[ANGLE]` degrees in screen coordinates (`000=right`, `090=down`, `180=left`, `270=up`).

Create one RGBA PNG eye-replacement overlay. The final canvas must be exactly 1086x1448 pixels and align over the master at coordinates 0,0.

Render only the complete left-eye and right-eye replacement regions needed to cover the original eyes: eyelids, eyelashes, sclera, irises, pupils, highlights, and the minimum surrounding face pixels needed for seamless compositing. Every pixel outside the two eye regions must have alpha 0.

The character must look naturally toward the red target dot. Preserve exactly the original eye outlines, iris diameter and color, pupil diameter, highlight design, eyelid geometry, eyelashes, line-art weight, facial proportions, spacing, and anime rendering style. Both eyes must focus on the same target. Keep pupils inside the sclera and allow natural eyelid occlusion at extreme directions.

Do not change or move the head, face shape, expression, eyebrows, nose, mouth, ears, hair, accessories, clothing, body, pose, lighting, shadows, canvas, scale, or registration. Do not blend neighboring anchors; render one clean pair of eyes. No doubled pupils, doubled highlights, ghosting, extra features, background, white matte, checkerboard, border, text, watermark, cropping, resizing, or recentering.

For `look_center.png`, ignore the angle and center both pupils naturally toward the viewer.

For frames from 320 through 355 degrees, interpolate forward from the approved 315-degree anchor toward 000/360 degrees; do not interpolate backward around the circle.

Save exactly as `[FRAME_NAME]`.
