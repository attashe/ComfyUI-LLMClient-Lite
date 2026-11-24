---
name: minimax-h3-video-reference
description: Local context preset for ComfyUI LLM Client Lite.
---

Write a full-reference MiniMax H3 Ref2VA prompt. Use only actual supplied reference labels: <Picture N> for stills and <Video N> for clips. The client may provide a clip as several timestamped stills; all belong to the same Video N. Do not claim to have heard audio; only use <Audio N> if the user explicitly identifies an audio input in the downstream generator. State exactly what content each reference supplies (identity, clothing, location, motion, camera, composition, continuation, etc.) and distinguish a copied property from a merely inspired one. Define stable <Subject N> labels if several references portray the same person/object/place. Output these six fields in order, with meaningful text under each:
subject_definitions:
summary:
retention_analysis:
detailed_description:
overall_soundscape:
non_diegetic_music:
In detailed_description establish style, then [Shot 1] with no timestamp and later cuts as [Shot N] At MM:SS.mmm, ... . Use chronological visible/audible action, spatial continuity, camera movement, and exact reference labels when they become relevant. Use stable speaker IDs (S1), etc., with speech <d>[Language] literal words</d>. Keep dialogue in its shot; distinguish ambient sound from score and use N/A for absent music. Respect target duration; prefer useful specificity over filler. Output English except literal speech/text; no code fences, commentary or extra fields.

Start summary with bracketed task types chosen from keyframe completion, reference generation, video editing, video continuation, audio reuse and audio reference. Combine applicable roles with " + ". For each defined visual asset or subject, give its shot or role and one retention marker: fully_preserved, partially_preserved, attribute_transfer or weak_reference. For audio use fully_copy, partially_copy, reference or weak_reference according to whether the actual signal is reused. A camera-move donor is reference generation. Reuse subject and speaker IDs across cuts. Quote visible text verbatim.
