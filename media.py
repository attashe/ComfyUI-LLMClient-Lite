"""Convert Comfy IMAGE batches to OpenAI vision content without disk I/O."""
from __future__ import annotations

import base64
import math
from io import BytesIO

from PIL import Image


def ordered_slots(group):
    """Autogrow names are zero-based; sort numerically, ignoring disconnected slots."""
    return [(name, group[name]) for name in sorted(group or {}, key=lambda name: int(name.rsplit('_', 1)[-1]))
            if group[name] is not None]


def sample_indices(count, fps, sample_fps, max_frames):
    if count < 1 or fps <= 0 or sample_fps <= 0 or max_frames < 1:
        raise ValueError("Video needs frames, positive FPS and a positive frame limit")
    if count == 1 or max_frames == 1:
        return [0]
    # Uniform coverage, including the beginning and end, even on long clips.
    n = min(count, max_frames, max(2, math.ceil((count - 1) / fps * sample_fps) + 1))
    return [round(i * (count - 1) / (n - 1)) for i in range(n)]


def image_part(frame, max_edge=768, quality=90):
    if frame.ndim != 3 or frame.shape[-1] not in (1, 3, 4):
        raise ValueError("Expected an HWC image with 1, 3 or 4 channels")
    # Move only the selected frame to CPU; never transfer the full video.
    array = frame.detach().float().cpu().clamp(0, 1).mul(255).round().byte().numpy()
    if array.shape[-1] == 1:
        array = array[..., 0]
    image = Image.fromarray(array).convert("RGB")
    if max_edge:
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    buf = BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": url}}


def _text(text):
    return {"type": "text", "text": text}


def _check_batch(batch, name):
    if batch.ndim != 4 or batch.shape[0] < 1:
        raise ValueError(f"{name}: expected a nonempty IMAGE batch [B,H,W,C]")


def build_messages(prompt, system_prompt="", images=None, videos=None, *, video_fps=24.0,
                   sample_fps=2.0, max_video_frames=12, max_edge=768, max_visual_items=64,
                   max_payload_mb=32, interrupt=None):
    image_slots, video_slots = ordered_slots(images), ordered_slots(videos)
    for name, batch in image_slots:
        _check_batch(batch, name)
    video_plan = []
    for name, source in video_slots:
        if interrupt:
            interrupt()
        if hasattr(source, "get_components"):
            components = source.get_components()
            batch, fps = components.images, float(components.frame_rate)
        else:
            batch, fps = source, video_fps
        _check_batch(batch, name)
        video_plan.append((batch, fps, sample_indices(len(batch), fps, sample_fps, max_video_frames)))
    total = len(image_slots) + sum(len(indices) for _, _, indices in video_plan)
    if total > max_visual_items:
        raise ValueError(f"Request contains {total} visual items; limit is {max_visual_items}. Reduce sampled frames or raise the limit.")
    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    if total == 0:
        return messages + [{"role": "user", "content": prompt}]
    content = [_text(prompt), _text("References follow. Picture and Video numbering is independent and one-based. Video inputs are sampled still frames; audio is not provided.")]
    encoded_bytes = 0

    def append_frame(frame):
        nonlocal encoded_bytes
        if interrupt:
            interrupt()
        part = image_part(frame, max_edge=max_edge)
        encoded_bytes += len(part["image_url"]["url"])
        if encoded_bytes > max_payload_mb * 1024 * 1024:
            raise ValueError("Encoded images exceed max_payload_mb; reduce resolution or frames")
        content.append(part)

    for i, (_, batch) in enumerate(image_slots, 1):
        content.append(_text(f"<Picture {i}>"))
        append_frame(batch[0])  # same convention as MiniMax H3 reference images
    for i, (batch, fps, indices) in enumerate(video_plan, 1):
        content.append(_text(f"<Video {i}>: {len(batch) / fps:.3f}s, {len(indices)} sampled frames in chronological order."))
        for index in indices:
            content.append(_text(f"<Video {i}> frame at {index / fps:.3f}s"))
            append_frame(batch[index])
        content.append(_text(f"End of <Video {i}>."))
    return messages + [{"role": "user", "content": content}]
