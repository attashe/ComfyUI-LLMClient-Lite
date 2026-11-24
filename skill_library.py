"""Local Markdown context library. No agent, tools, scripts or network access."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

BUILTIN = Path(__file__).resolve().parent / "skills"
NONE = "(none)"


def catalog():
    roots = [BUILTIN]
    if custom := os.getenv("LLMCLIENT_SKILLS_DIR"):
        roots.append(Path(custom).expanduser())
    found = {}
    for root in roots:
        for path in sorted(root.glob("*/SKILL.md")):
            if path.is_file() and path.parent.name != NONE:
                found[path.parent.name] = path
    return found


def names():
    return [NONE, *sorted(catalog())]


def _read(path):
    name = path.parent.name
    if path.stat().st_size > 256 * 1024:
        raise ValueError(f"Skill {name!r} is too large (limit 256 KiB)")
    text = path.read_text(encoding="utf-8-sig").strip()
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if end is None:
            raise ValueError(f"Unclosed YAML front matter in skill {name!r}")
        text = "\n".join(lines[end + 1:]).strip()
    if not text:
        raise ValueError(f"Skill {name!r} is empty")
    return text


def load(name):
    if name == NONE:
        return ""
    files = catalog()
    path = files.get(name)
    if path is None:
        raise ValueError(f"Unknown skill: {name!r}. Refresh ComfyUI node definitions after adding a skill.")
    text = _read(path)
    if path.parent.parent == BUILTIN and name.startswith("minimax-h3-style-"):
        # Style directions use the same two output formats as the general H3 writer.
        return "\n\n".join((text, "Select ONE format for the clip. Use base for text or endpoint frames only. "
            "Use Ref2VA when an asset supplies identity, style, camera motion, editing or continuation.",
            "Base format:\n" + _read(files["minimax-h3-video-base"]),
            "Ref2VA format:\n" + _read(files["minimax-h3-video-reference"])))
    return text


def fingerprint(name):
    return hashlib.sha256(load(name).encode()).hexdigest()


def compose(name, previous="", extra=""):
    return "\n\n".join(part.strip() for part in (previous, load(name), extra) if part and part.strip())
