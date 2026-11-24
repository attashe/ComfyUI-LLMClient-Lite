# ComfyUI LLM Client Lite

A small, independent rewrite of the provider/chat workflow from [Vex131/ComfyUI-LLMClient](https://github.com/Vex131/ComfyUI-LLMClient). Intended for local LLMs/VLMs that write, rewrite or analyze prompts for ComfyUI. This is a separate pack with new node IDs, not an in-place patch or a registered Manager package.

Three nodes, no extra package installation, no tools/RAG/agent loop, no provider registry or cache files, no temporary media files. Requires a current ComfyUI with V3 `io.Autogrow` (the same mechanism as MiniMax H3 Reference to Video), plus its normal aiohttp, Pillow and torch dependencies. `MultiType` enables native VIDEO inputs when available.

Open [Prompt writer.json](examples/Prompt%20writer.json) for a connected starter workflow. It uses the local server on port 5000 and opens with native reasoning enabled. Run it to inspect the prompt and the model’s reasoning in Chat.

## Install

1. Extract the `ComfyUI-LLMClient-Lite` folder into `ComfyUI/custom_nodes/` (one folder level; `__init__.py` must be directly in it).
2. Restart ComfyUI and refresh the browser. Find `LLM Client Lite` in Add Node.
3. Start your existing OpenAI-compatible LLM/VLM server. For a vision-capable llama.cpp model, load the matching mmproj and use the chat template appropriate for the checkpoint.

Example (adapt paths and inference settings to your model):

```bash
llama-server -m /models/model.gguf --mmproj /models/mmproj.gguf --jinja --host 127.0.0.1 --port 5000
```

If ComfyUI is on a different machine, bind llama-server to the appropriate LAN interface and use the server's LAN address in Provider. Restrict access with a firewall and/or authentication; do not expose an unauthenticated inference server publicly. `localhost` is the machine running the ComfyUI backend, not the browser.

## Nodes

### LLM Provider (Lite)

- `base_url`: change the host/port in one place (default `http://127.0.0.1:5000/v1`). Bare hosts get `/v1` automatically. A nonempty path is treated as the explicit API root, so custom reverse-proxy paths work too.
- `model`: explicit model ID, or `auto` when GET `/models` returns exactly one model. A multi-model server reports its available IDs; select one by typing it here. No background probing or stored model metadata.
- `key_env`: name of an environment variable, not the key. Default `LLMCLIENT_API_KEY`; alternative keys must use names beginning `LLMCLIENT_API_KEY_`. Blank = no auth. Set the variable on the ComfyUI server before starting ComfyUI. For example `export LLMCLIENT_API_KEY_LOCAL='...'` and `key_env=LLMCLIENT_API_KEY_LOCAL`. Workflow files contain only the variable name. As with any HTTP node, use trusted workflows and endpoints; a workflow can route its media or a configured API credential to a different URL.

### LLM Skill (Lite)

Choose a skill from the dropdown. `context` is a normal STRING: connect it to Chat's `system_prompt` (convert the widget to an input in the node menu if needed). `extra` adds project-specific constraints. `previous` accepts the output of another Skill node for composition. Text order: previous context, selected skill, extra. Do not combine two incompatible model-output formats.

| Preset | Output |
|---|---|
| `krea-2` | Natural-language prompt |
| `moss-caption` | Natural-language caption, directly usable |
| `moss-layout-draft` | JSON draft with pixel BBOX; needs MOSS compiler |
| `minimax-h3-image` | Image/edit prompt with Picture references |
| `minimax-h3-video-base` | Base T2VA/I2VA/FL2VA/L2VA three-field prompt |
| `minimax-h3-video-reference` | Six-field Ref2VA prompt |
| `minimax-h3-style-…` | H3 video prompt in one of eight styles (see below) |
| `character-sheet` | Character consistency and multi-view prompt modifier |
| `visual-analysis` | Describe or compare media |
| `ltx-video` | Video prompt in natural language |
| `flux-image` | Image prompt in natural language |

The H3 style presets cover 3D animation, brand promotion, co-op game intros, hand-drawn overlays on live action, minimalist product ads, music videos with lyric typography, paper collage and papercraft stop motion. Select one style directly in Chat. Each includes base and reference prompt instructions. Describe whether a picture is an endpoint or a donor for identity, motion or style. For explicit control of the format, select the base or reference writer.

These are local adaptations of the prompt-writing stages. MiniMax Hub handles additional production steps such as approvals, rendering and assembly in the upstream workflows. Each style file links to the revision it follows. [MiniMax H3 skill catalog](https://github.com/MiniMax-AI/MiniMax-H3/tree/199b7d0e1fd95e7b3eafa8c15eca692534142427/skills)

Add a custom skill by creating a folder with `SKILL.md`:

```text
skills/
  my-project/
    SKILL.md
```

```markdown
---
name: my-project
description: My game art direction
---
Return a prompt for a stylized medieval environment.
Use a muted palette, weathered timber and readable silhouettes.
Keep the final output compatible with the selected target model.
```

New skill names may require refreshing node definitions or restarting ComfyUI. Editing existing contents invalidates the cached Skill node using a content hash. For updates without losing your own presets, set `LLMCLIENT_SKILLS_DIR` to a directory outside this pack before starting ComfyUI; its subfolders override built-in skills of the same name. YAML front matter is removed; the rest is inserted verbatim into context. `references/` and scripts are intentionally not loaded or executed. Put necessary instructions into SKILL.md itself (max 256 KiB per skill).

### LLM Chat (Lite)

Connect Provider to Chat, enter a prompt and choose a **Prompt template**. Chat applies the template first, followed by your system instructions or connected Skill. Wire the first output to Preview as Text or to the next node in your workflow. After execution, the **Answer** and **Reasoning** tabs let you inspect and copy both strings on the node. In Explain answer mode the second tab is labeled **Explanation**.

Open **Settings** for sampling sliders, exact numeric values, media limits and request options. Sampling presets change temperature, top P and top K together. Select **Server default** on any of those controls to omit that parameter. **Apply settings** commits the edits to the workflow. Right-click Chat and choose **Show inline settings** to expose individual widgets for wiring.

| Reasoning mode | Second output |
|---|---|
| Server default | Reasoning supplied by the endpoint, including supported inline thought blocks. Empty when the model supplies only an answer. |
| llama.cpp · reasoning first | Starts the assistant turn in the reasoning channel. Set its token budget in Settings (default 128) and allow space for the final answer in the total output budget. Requires llama.cpp support for reasoning continuation and budgets. |
| llama.cpp · thinking on / off | Sets the template’s `enable_thinking` flag and requests separate reasoning from the llama.cpp parser. The model and chat template determine whether it emits a thought. |
| Explain answer | Requests a brief model-written explanation and a final answer in a single structured response. Requires JSON Schema support. The first socket carries the answer in your chosen format. |

Media sockets use native `Autogrow`: `images.image_0`, `images.image_1`, ... and `videos.video_0`, `videos.video_1`, ... (0–100 sockets in each group). The frontend grows the input list as you connect references. Image slots use one picture per socket (first frame of a batch), consistent with H3 reference image semantics. Split an image batch into separate sockets to preserve individual numbering. Each video slot accepts an IMAGE batch of frames, or native VIDEO on builds with `MultiType`. A VIDEO object provides its own FPS; for IMAGE frame batches set the shared `video_fps` or convert clips to the same frame rate before connecting. On older builds use `Load Video → Get Video Components → videos.video_N` and set/connect its FPS. All media is encoded on the ComfyUI backend, so the external LLM server does not need access to the same filesystem.

References are ordered numerically by slot, skipping empty slots. The LLM receives `<Picture 1>`, `<Picture 2>`, etc., and `<Video 1>`, `<Video 2>`, etc., independently numbered. Keep the same connected reference order in the downstream generation node. The 100-slot capacity of the LLM client does **not** override H3 or other downstream models' own reference limits.

Video is analyzed as timestamped still frames sent via `image_url`, not a native video upload. Native VIDEO decoding may materialize all frames on the ComfyUI host. Audio is not sent. Frame sampling is uniform and preserves first/last frames (unless max_video_frames=1). Fast actions can be missed; increase frame count for temporal analysis. Native `input_video`/`video_url` endpoints and audio are intentionally not implemented to keep the transport common across servers.

Advanced controls:

| Parameter | Default | Meaning |
|---|---:|---|
| `video_fps` | 24 | Actual FPS of IMAGE frame batches |
| `sample_fps` | 2 | Approximate number of frames per second sent |
| `max_video_frames` | 12 | Maximum per video; uniform coverage across entire clip |
| `max_image_edge` | 768 | Long edge limit; 0 retains original resolution; never upscales |
| `max_visual_items` | 64 | Total pictures + selected frames per request; raise deliberately |
| `max_payload_mb` | 32 | Limit on encoded image data, including base64 overhead |
| `temperature`, `top_p`, `top_k` | -1 | Omit for provider defaults (`top_k` is backend-specific) |
| `max_tokens` | 4096 | Output budget; -1 omits setting |
| `reasoning_effort` | empty | Provider default; set a supported value, e.g. `none` on suitable llama.cpp templates |
| `output_format` | text | `json_object` requests strict JSON object mode when supported; client also checks output is an object |
| `stream` | true | SSE streaming transport; output is available after full completion, not a live token widget |
| `timeout_seconds` | 300 | HTTP timeout per operation |
| `seed` | 0 | Fixed seed (normal ComfyUI caching); -1 omits seed and forces rerun; randomize via seed control |

The visual and byte limits are not a token estimator. VLM image-token costs depend on the server and model; too many frames or too large a resolution can still exceed context. A text-only model cannot analyze media. Unsupported request options are not silently retried or dropped; the server error is reported. On cancellation the plugin closes its HTTP request; actual generation abort depends on the backend. Incomplete streams and truncated (`finish_reason=length`) responses fail rather than forwarding a partial prompt to a downstream sampler.

## Example workflows

Open [H3 papercraft.json](examples/H3%20papercraft.json) for a six-second text-to-video prompt using the papercraft style. Its first output is the H3 prompt, ready to connect to a video workflow.

- Text: `LLM Provider → LLM Chat → Preview as Text`, with `LLM Skill(krea-2) → system_prompt`.
- H3 Ref2VA: connect references to both Chat and H3 Reference to Video, in the same order; select `minimax-h3-video-reference` and pass Chat output to H3 prompt. Specify target duration in the user task. For audio references mention known roles in text; the VLM does not hear the audio.
- Character sheet: `LLM Skill(minimax-h3-image) → LLM Skill(character-sheet).previous → Chat.system_prompt`.
- MOSS layout: choose `moss-layout-draft`, set `output_format=json_object`, include canvas width/height in prompt, then feed Chat output to an existing MOSS compiler (e.g. WAS MOSS-Image Compile Prompt) with the same dimensions. The draft is **not** the final model prompt: compilation converts top-left xyxy to centered yxyx. Disable downstream prompt rewriting if it destroys the layout.

The `examples/*.api.json` files contain API-format graphs wrapped as `{ "prompt": {...} }` for `POST /prompt`. Edit filenames and base URL first. API dynamic inputs must be flat dotted names, not nested objects.

```bash
curl -H 'Content-Type: application/json' -d @examples/text.api.json http://127.0.0.1:8188/prompt
```

## Code

```
__init__.py       # V3 extension registration
nodes.py          # three node schemas and execution adapters
client.py         # async HTTP, SSE/JSON, reasoning, model selection, errors
media.py          # resize, sample, JPEG/base64, reference labels
skill_library.py  # skill discovery, reading, composition, cache fingerprint
skills/           # plain Markdown context presets
web/              # Chat settings and reply preview
examples/         # draggable starter workflow and API examples
tests/            # Python unit and local mock HTTP integration tests
```

Run from this directory in an environment with the ComfyUI dependencies:

```bash
python -m unittest discover -s tests -v
```

## Credits

AusBoss inspired the nodes’ visual style and the compact layout of the Chat controls. [ComfyUI-AusBoss](https://github.com/ausboss/ComfyUI-AusBoss)

## References

- [Original project (MIT)](https://github.com/Vex131/ComfyUI-LLMClient)
- [ComfyUI H3 Autogrow implementation](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py)
- [ComfyUI V3 schema and Autogrow](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_api/latest/_io.py)
- [llama.cpp HTTP API](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [LTX-2 prompting](https://ltx.io/blog/prompting-guide-for-ltx-2)
- [FLUX.2 prompting](https://docs.bfl.ai/guides/prompting_guide_flux2)
- [Krea 2 expansion instructions](https://github.com/krea-ai/krea-2/blob/db3984fbc6e13b34c0064990fc2d95ac64d00058/docs/expansion.txt)
- [Krea 2 prompting](https://github.com/krea-ai/krea-2/blob/main/docs/prompting.md)
- [MOSS-Image official skill](https://github.com/OpenMOSS/MOSS-Image/tree/main/skills/moss-image-prompt-enhancer)
- [MiniMax H3 image skill](https://github.com/MiniMax-AI/MiniMax-H3-Image/tree/main/skills/h3-image-prompt-writing)
- [MiniMax H3 video skill](https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills/h3-prompt-writing)
