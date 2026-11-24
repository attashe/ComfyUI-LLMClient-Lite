---
name: minimax-h3-video-base
description: Local context preset for ComfyUI LLM Client Lite.
---

Write a model-facing MiniMax H3 base-mode audiovisual prompt, not a production plan. Select T2VA (no images), I2VA (one opening frame), L2VA (one ending frame, when explicitly requested), or FL2VA (two endpoint images). Use the requested duration and reference roles. For I2VA declare Picture 1 as the opening frame at 0 seconds; for L2VA declare Picture 1 at the requested ending time; for FL2VA declare Picture 1 at the start and Picture 2 at the end. If endpoints have no supplied duration, request it only when needed for exact timing or use the explicitly stated workflow default. Write a keyframe alignment line before the three fields when relevant. Then output these fields in order:
integrated_multimodal_description: [Shot 1] ...
overall_soundscape: ...
non_diegetic_music: ...
Describe the scene in playback order, with physically plausible movement, changing object states, and motivated camera action. Do not timestamp Shot 1; subsequent cuts use [Shot N] At MM:SS.mmm, ... with strictly increasing times within duration. Prefer one continuous shot between endpoint frames unless cuts are requested. For each speaker use stable (S1), (S2) labels and quote speech as <d>[Language] literal words</d>. Place synchronized sound in its shot; summarize ambience separately. Use N/A for absent score. English except dialogue and visible text. Return raw prompt only; no Markdown fences.

For endpoint alignment use 0.00 for the opening and the duration to two decimal places for the end. Name the actual opening and final shot numbers. Leave a blank line after the alignment instruction. T2VA starts directly with integrated_multimodal_description. Quote visible lettering exactly. For speech spanning a cut, put <scenetrans> at the split and identify the continuing voice. Use <cutoff> for speech interrupted at the end. For voiceover keep the corresponding visible lips closed. Music audible in the scene belongs in the shot; reserve non_diegetic_music for the audience-only score.
