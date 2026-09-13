# Mannequin motion in the browser

Horizontal dragging physically turns a kinematic mannequin about the center of its body bounds. Vertical dragging changes viewing elevation about that same fixed pivot; scroll/pinch zooms. Pan controls and modifier-based panning are removed. While paused, dragging inspects the frozen body and cloth without changing their physical state.

The mesh and contact solver share the same yaw transform. SDF/BVH queries transform into body space, normals transform back, and contact friction subtracts body surface displacement. Cloth positions and velocities remain in world space, so acceleration and reversals produce inertia. Each physics substep has its own aligned uniform slot; queued writes cannot collapse intermediate poses into one teleport. Angular speed and acceleration are bounded. Motion waits for the initial sewing stage; Reset returns both body and cloth to their initial state.

Validation: eight Node tests pass (fixed pivot, mouse/modifier/touch/keyboard input, pause inspection, bounded motion, controller lifecycle, collar placement). Fourteen live GPU kernel fixtures pass, including moving-contact friction and rotated contact normals. The default dress shirt ran 300 settling frames followed by 600 frames of turns/reversals/settling in the in-app browser. Mean: 12.32 ms/frame. All samples finite. Peak cloth deviation from a rigidly rotated starting drape: 10.13 mm RMS. Velocity settled from 0.608 m/s during reversal to 0.0058 m/s. Raw report: `benchmarks/webgpu/results/2026-09-13-motion.json`.

This is an upright turntable interaction, not skeletal walking or arm articulation. No backend GPU is used.
