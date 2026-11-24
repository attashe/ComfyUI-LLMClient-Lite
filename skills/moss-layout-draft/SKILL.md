---
name: moss-layout-draft
description: Local context preset for ComfyUI LLM Client Lite.
---

Write a JSON draft for the MOSS-Image layout compiler. Deliver one object, beginning with { and ending with }. This is the structure of a valid 1024 × 768 draft:

{"width":1024,"height":768,"bbox_coord_space":"abs","bbox_format":"xyxy","summary":{"canvas":"single","caption":"Cream letterpress poster with a red pear beneath a short headline."},"items":[{"label":"object","caption":"Red pear, aligned to the center with a soft contact shadow","bbox":[330,245,695,685]},{"label":"text","caption":"Bold black serif headline centered above the pear","text":"Market Day","bbox":[110,72,914,200]}]}

Replace the example with the requested composition and exact copy. Use the requested dimensions (multiples of 16), defaulting to 1024 by 1024. Put the global scene and style in summary.caption. Each item has a label of object, character or text, a caption, and its box [left,top,right,bottom] in actual pixels measured from the upper left. Use nonempty boxes within the canvas. Quote visible characters verbatim in the text field of text items, preserving intended line breaks. Give separately positioned text its own item. Plan margins and reading order across the whole canvas, including deliberate overlaps. The compiler handles the final coordinate conversion.
