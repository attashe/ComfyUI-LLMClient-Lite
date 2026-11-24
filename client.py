"""Small OpenAI-compatible transport; independent of ComfyUI."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import aiohttp

REASONING_FIRST = "llama.cpp · reasoning first"
REASONING_MODES = ["Server default", REASONING_FIRST, "llama.cpp · thinking on", "llama.cpp · thinking off", "Explain answer"]
THOUGHT_PREFIX = "Brief plan:\n"
BUDGET_MESSAGE = "\nNow give the complete final answer."


@dataclass(frozen=True)
class Provider:
    base_url: str
    model: str = ""
    key_env: str = "LLMCLIENT_API_KEY"

    def __post_init__(self):
        raw = self.base_url.strip()
        if "://" not in raw:
            raw = "http://" + raw
        url = urlsplit(raw)
        if (url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment):
            raise ValueError("Use an HTTP(S) API root, e.g. http://127.0.0.1:5000/v1")
        _ = url.port  # validate port
        path = url.path.rstrip("/") or "/v1"
        object.__setattr__(self, "base_url", urlunsplit((url.scheme, url.netloc, path, "", "")))
        object.__setattr__(self, "model", self.model.strip())
        key_env = self.key_env.strip()
        if key_env and key_env != "LLMCLIENT_API_KEY" and not key_env.startswith("LLMCLIENT_API_KEY_"):
            raise ValueError("Use LLMCLIENT_API_KEY or a name beginning with LLMCLIENT_API_KEY_")
        object.__setattr__(self, "key_env", key_env)

    def headers(self):
        key = os.environ.get(self.key_env, "") if self.key_env else ""
        return {"Authorization": f"Bearer {key}"} if key else {}


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reply:
    text: str
    reasoning: str


async def _check(response):
    if response.status >= 400:
        body = (await response.content.read(4096)).decode("utf-8", errors="replace")
        raise LLMError(f"LLM server HTTP {response.status}: {body}")
    if 300 <= response.status < 400:
        raise LLMError(f"LLM server returned redirect HTTP {response.status}; use its final API URL")


async def _resolve_model(session, provider):
    if provider.model and provider.model.lower() != "auto":
        return provider.model
    async with session.get(provider.base_url + "/models", allow_redirects=False) as response:
        await _check(response)
        data = await response.json(content_type=None)
    ids = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")]
    if len(ids) == 1:
        return ids[0]
    raise LLMError("Set model explicitly; /models returned: " + (", ".join(ids) or "no models"))


def _text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(p.get("text", "") for p in value if isinstance(p, dict) and isinstance(p.get("text"), str))
    return ""


def _choice(packet):
    if packet.get("error"):
        raise LLMError(f"LLM server: {packet['error']}")
    choices = packet.get("choices") or []
    if not choices:
        return None
    return choices[0]


def _parts(message):
    return _text(message.get("content")), _text(message.get("reasoning_content") or message.get("reasoning") or message.get("thinking"))


async def _sse(response):
    """SSE lines are reassembled by aiohttp, including split network chunks."""
    data = []
    async for raw in response.content:
        line = raw.decode("utf-8").rstrip("\r\n")
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
    if data:
        yield "\n".join(data)


async def _read_reply(response, stream):
    text, reasoning = [], []
    finished = False
    reason = None
    if stream and "text/event-stream" in response.headers.get("Content-Type", "").lower():
        async for event in _sse(response):
            if event == "[DONE]":
                finished = True
                break
            choice = _choice(json.loads(event))
            if choice is None:
                continue
            t, r = _parts(choice.get("delta") or choice.get("message") or {})
            text.append(t)
            reasoning.append(r)
            if choice.get("finish_reason") is not None:
                reason = choice["finish_reason"]
                finished = True
        if not finished:
            raise LLMError("LLM stream ended without a completion marker")
    else:
        choice = _choice(await response.json(content_type=None))
        if choice is None:
            raise LLMError("LLM response contained no choices")
        t, r = _parts(choice.get("message") or {})
        text.append(t)
        reasoning.append(r)
        reason = choice.get("finish_reason")
    if reason not in (None, "stop", "eos", "end_turn"):
        raise LLMError(f"LLM did not finish a complete text answer (finish_reason={reason}); check token budget or server settings")
    answer, thought = "".join(text).strip(), "".join(reasoning).strip()
    # Some local templates expose thinking inline instead of as a separate field.
    for opening, closing in (("<think>", "</think>"), ("<|channel>thought\n", "<channel|>")):
        if answer.startswith(opening):
            inline, end, answer = answer[len(opening):].partition(closing)
            if not end:
                raise LLMError("Unclosed reasoning block. Increase the token budget or check the server template.")
            thought, answer = thought or inline.strip(), answer.strip()
            break
    if not answer:
        raise LLMError("LLM returned no final text; check max_tokens and reasoning settings")
    return Reply(answer, thought)


def _system_instruction(messages, instruction):
    if messages and messages[0]["role"] == "system":
        return [{**messages[0], "content": messages[0]["content"] + "\n\n" + instruction}, *messages[1:]]
    return [{"role": "system", "content": instruction}, *messages]


async def _complete(provider, messages, options, timeout, stream, reasoning_mode, reasoning_budget):
    json_answer = options.get("response_format", {}).get("type") == "json_object"
    if reasoning_mode in (REASONING_FIRST, "llama.cpp · thinking on", "llama.cpp · thinking off"):
        thinking = reasoning_mode != "llama.cpp · thinking off"
        options = {**options, "chat_template_kwargs": {"enable_thinking": thinking}, "reasoning_format": "deepseek"}
        if thinking and options.get("reasoning_effort") == "none":
            del options["reasoning_effort"]
        if reasoning_mode == REASONING_FIRST:
            # llama.cpp needs a nonempty reasoning prefix to continue the thought channel.
            messages = _system_instruction(messages, "Plan briefly inside the thought channel. In the final channel give the complete answer from its beginning, including any required headings.")
            messages.append({"role": "assistant", "content": "", "reasoning_content": THOUGHT_PREFIX})
            options.update(continue_final_message="reasoning_content", add_generation_prompt=False,
                           reasoning_budget_tokens=reasoning_budget, reasoning_budget_message=BUDGET_MESSAGE)
    elif reasoning_mode == "Explain answer":
        schema = {"type": "object", "properties": {
            "explanation": {"type": "string", "description": "Briefly explain the basis for the answer."},
            "answer": {"type": "object", "additionalProperties": True} if json_answer else {"type": "string"},
        }, "required": ["explanation", "answer"], "additionalProperties": False}
        options = {**options, "response_format": {"type": "json_schema", "json_schema": {
            "name": "explained_answer", "strict": True, "schema": schema}}}
        instruction = "Respond with a JSON object. In explanation, briefly explain your answer or creative choices. In answer, give the requested final output."
        messages = _system_instruction(messages, instruction)
    elif reasoning_mode != "Server default":
        raise ValueError(f"Unknown reasoning mode: {reasoning_mode}")
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout), headers=provider.headers()) as session:
        model = await _resolve_model(session, provider)
        payload = {**options, "model": model, "messages": messages, "stream": stream}
        async with session.post(provider.base_url + "/chat/completions", json=payload, allow_redirects=False) as response:
            await _check(response)
            reply = await _read_reply(response, stream)
            if reasoning_mode == REASONING_FIRST:
                thought = reply.reasoning.removeprefix(THOUGHT_PREFIX).removesuffix(BUDGET_MESSAGE).strip()
                reply = Reply(reply.text, "" if thought == THOUGHT_PREFIX.strip() else thought)
            if reasoning_mode == "Explain answer":
                data = json.loads(reply.text)
                if not isinstance(data, dict) or not isinstance(data.get("explanation"), str) or not data["explanation"].strip():
                    raise LLMError("Expected a nonempty explanation from the server")
                answer = data.get("answer")
                if not isinstance(answer, dict if json_answer else str) or (not json_answer and not answer.strip()):
                    raise LLMError("Invalid answer in the explained response")
                return Reply(json.dumps(answer, ensure_ascii=False) if json_answer else answer, data["explanation"])
            if json_answer:
                if not isinstance(json.loads(reply.text), dict):
                    raise LLMError("Expected a JSON object from the server")
            return reply


async def complete(provider, messages, options, *, timeout=300, stream=True, interrupt=None,
                   reasoning_mode="Server default", reasoning_budget=128):
    """Cancel the HTTP request on a ComfyUI interrupt; server-side abort is backend dependent."""
    if interrupt is not None:
        interrupt()
    task = asyncio.create_task(_complete(provider, messages, options, timeout, stream, reasoning_mode, reasoning_budget))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.2)
            if interrupt is not None:
                interrupt()
        return await task
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        raise LLMError(f"LLM request failed: {type(exc).__name__}: {exc}") from exc
    finally:
        if not task.done():
            task.cancel()
        # Retrieve exceptions even when interrupted just as the request finishes.
        await asyncio.gather(task, return_exceptions=True)


def request_options(*, temperature=-1, top_p=-1, top_k=-1, max_tokens=-1,
                    seed=-1, reasoning_effort="", output_format="text"):
    values = {"temperature": temperature, "top_p": top_p, "top_k": top_k,
              "max_tokens": max_tokens, "seed": seed}
    options = {key: val for key, val in values.items() if val >= 0}
    if reasoning_effort.strip():
        options["reasoning_effort"] = reasoning_effort.strip()
    if output_format == "json_object":
        options["response_format"] = {"type": "json_object"}
    elif output_format != "text":
        raise ValueError(f"Unknown output_format: {output_format}")
    return options
