"""Three ComfyUI V3 nodes. All transport and context logic stays outside this file."""
from __future__ import annotations

import asyncio

from comfy import model_management
from comfy_api.latest import io

from . import client, media, skill_library

PROVIDER = io.Custom("LLMCLIENT_LITE_PROVIDER")
CATEGORY = "LLM Client Lite"


def grow(name, prefix, tooltip, *, video=False):
    # MultiType lets VIDEO and IMAGE batches share a slot on newer ComfyUI builds.
    if video and hasattr(io, "MultiType"):
        template = io.MultiType.Input(prefix.rstrip("_"), [io.Image, io.Video], tooltip=tooltip)
    else:
        template = io.Image.Input(prefix.rstrip("_"), tooltip=tooltip)
    return io.Autogrow.Input(name, optional=True, template=io.Autogrow.TemplatePrefix(
        input=template, prefix=prefix, min=0, max=100))


class LiteLLMProvider(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="LiteLLMProvider", display_name="LLM Provider (Lite)", category=CATEGORY,
            inputs=[
                io.String.Input("base_url", display_name="API address", default="http://127.0.0.1:5000/v1", tooltip="Address as seen from the ComfyUI backend. A bare host uses /v1."),
                io.String.Input("model", display_name="Model ID", default="auto", tooltip="Use auto for a single loaded model, or enter its API model ID."),
                io.String.Input("key_env", display_name="API key variable", default="LLMCLIENT_API_KEY", advanced=True, tooltip="Name of the environment variable containing the key."),
            ], outputs=[PROVIDER.Output(display_name="model")])

    @classmethod
    def execute(cls, base_url, model="auto", key_env="LLMCLIENT_API_KEY"):
        return io.NodeOutput(client.Provider(base_url, model, key_env))


class LiteLLMSkill(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="LiteLLMSkill", display_name="LLM Skill (Lite)", category=CATEGORY,
            inputs=[
                io.Combo.Input("skill", display_name="Instructions", options=skill_library.names(), default=skill_library.NONE),
                io.String.Input("extra", display_name="Project notes", placeholder="Add style, constraints or output requirements…", default="", multiline=True, optional=True),
                io.String.Input("previous", optional=True, force_input=True),
            ], outputs=[io.String.Output(display_name="context")])

    @classmethod
    def fingerprint_inputs(cls, skill=skill_library.NONE, **kwargs):
        # Editing a skill invalidates its cached output even when the dropdown is unchanged.
        return skill_library.fingerprint(skill) if isinstance(skill, str) else float("nan")

    @classmethod
    def execute(cls, skill=skill_library.NONE, extra="", previous=""):
        return io.NodeOutput(skill_library.compose(skill, previous, extra))


class LiteLLMChat(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(node_id="LiteLLMChat", display_name="LLM Chat (Lite)", category=CATEGORY,
            description="OpenAI-compatible prompt generation and vision. Videos are sent as sampled frames.",
            inputs=[
                PROVIDER.Input("model"),
                io.String.Input("prompt", display_name="Prompt", placeholder="Describe the task or ask about your references…", default="", multiline=True),
                io.String.Input("system_prompt", display_name="System instructions", placeholder="Add instructions or connect an LLM Skill…", default="", multiline=True, optional=True, advanced=True),
                io.Int.Input("seed", default=0, min=-1, max=2**32-2, control_after_generate=True),
                grow("images", "image_", "One reference picture per socket (first frame of IMAGE batch)."),
                grow("videos", "video_", "VIDEO or IMAGE frame batch. For IMAGE use video_fps.", video=True),
                io.Float.Input("video_fps", default=24.0, min=0.01, max=240.0, step=0.01, advanced=True),
                io.Float.Input("sample_fps", default=2.0, min=0.01, max=60.0, step=0.1, advanced=True),
                io.Int.Input("max_video_frames", default=12, min=1, max=512, advanced=True),
                io.Int.Input("max_image_edge", default=768, min=0, max=8192, step=64, advanced=True, tooltip="0 = original resolution; never upscale."),
                io.Int.Input("max_visual_items", default=64, min=1, max=2000, advanced=True),
                io.Int.Input("max_payload_mb", default=32, min=1, max=512, advanced=True),
                io.Float.Input("temperature", default=-1.0, min=-1.0, max=4.0, step=0.05, advanced=True, display_mode=io.NumberDisplay.slider),
                io.Float.Input("top_p", default=-1.0, min=-1.0, max=1.0, step=0.05, advanced=True, display_mode=io.NumberDisplay.slider),
                io.Int.Input("top_k", default=-1, min=-1, max=10000, advanced=True),
                io.Int.Input("max_tokens", default=4096, min=-1, max=1000000, advanced=True),
                io.String.Input("reasoning_effort", default="", advanced=True, tooltip="Blank omits this provider-specific field."),
                io.Combo.Input("output_format", options=["text", "json_object"], default="text", advanced=True),
                io.Boolean.Input("stream", default=True, advanced=True),
                io.Int.Input("timeout_seconds", default=300, min=1, max=86400, advanced=True),
                io.Combo.Input("template", display_name="Prompt template", options=skill_library.names(), default=skill_library.NONE, optional=True,
                    tooltip="Apply a local instruction template before any system instructions."),
                io.Combo.Input("reasoning_mode", display_name="Reasoning", options=client.REASONING_MODES, default="Server default", optional=True,
                    tooltip="Reasoning first starts a llama.cpp turn in the thought channel. Explain answer requests a written rationale."),
                io.Int.Input("reasoning_budget", display_name="Reasoning-first token budget", default=128, min=1, max=1000000, optional=True, advanced=True,
                    tooltip="Tokens available for the thought in reasoning-first mode. Leave room within the output token budget for the answer."),
            ], outputs=[io.String.Output(display_name="output"), io.String.Output(display_name="reasoning")])

    @classmethod
    def fingerprint_inputs(cls, seed=0, template=skill_library.NONE, **kwargs):
        if seed is None or seed < 0 or not isinstance(template, str):
            return float("nan")
        return seed if template == skill_library.NONE else (seed, skill_library.fingerprint(template))

    @classmethod
    async def execute(cls, model, prompt, system_prompt="", seed=0, images=None, videos=None,
                      video_fps=24.0, sample_fps=2.0, max_video_frames=12, max_image_edge=768,
                      max_visual_items=64, max_payload_mb=32, temperature=-1.0, top_p=-1.0,
                      top_k=-1, max_tokens=4096, reasoning_effort="", output_format="text",
                      stream=True, timeout_seconds=300, template=skill_library.NONE, reasoning_mode="Server default", reasoning_budget=128):
        check = model_management.throw_exception_if_processing_interrupted
        system_prompt = skill_library.compose(template, extra=system_prompt)
        messages = await asyncio.to_thread(media.build_messages, prompt, system_prompt, images, videos,
            video_fps=video_fps, sample_fps=sample_fps, max_video_frames=max_video_frames,
            max_edge=max_image_edge, max_visual_items=max_visual_items, max_payload_mb=max_payload_mb,
            interrupt=check)
        options = client.request_options(temperature=temperature, top_p=top_p, top_k=top_k,
            max_tokens=max_tokens, seed=seed, reasoning_effort=reasoning_effort, output_format=output_format)
        result = await client.complete(model, messages, options, timeout=timeout_seconds, stream=stream,
                                       interrupt=check, reasoning_mode=reasoning_mode, reasoning_budget=reasoning_budget)
        return io.NodeOutput(result.text, result.reasoning, ui={"answer": [result.text], "reasoning": [result.reasoning],
                             "reasoning_mode": [reasoning_mode]})
