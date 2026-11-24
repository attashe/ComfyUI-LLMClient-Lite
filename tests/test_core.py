import asyncio
import base64
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import torch
from aiohttp import web
from PIL import Image

import client
import media
import skill_library


class CoreTests(unittest.TestCase):
    def test_provider_url(self):
        self.assertEqual(client.Provider('localhost:9001').base_url, 'http://localhost:9001/v1')
        self.assertEqual(client.Provider('https://example.org/custom/v1/').base_url, 'https://example.org/custom/v1')
        for bad in ['file:///tmp/file', 'http://user:pass@localhost', 'http://localhost:99999', 'http://localhost?x=y']:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                client.Provider(bad)
        with self.assertRaises(ValueError):
            client.Provider('localhost', key_env='OTHER_SECRET')

    def test_key(self):
        with patch.dict(os.environ, {'LLMCLIENT_API_KEY': 'test-key'}):
            self.assertEqual(client.Provider('localhost').headers(), {'Authorization': 'Bearer test-key'})
            self.assertEqual(client.Provider('localhost', key_env='').headers(), {})

    def test_request_options(self):
        self.assertEqual(client.request_options(), {})
        self.assertEqual(client.request_options(seed=3, output_format='json_object', reasoning_effort='none'),
            {'seed': 3, 'response_format': {'type': 'json_object'}, 'reasoning_effort': 'none'})

    def test_text_only(self):
        self.assertEqual(media.build_messages('hi', 'system'), [{'role':'system','content':'system'}, {'role':'user','content':'hi'}])

    def test_sample(self):
        self.assertEqual(media.sample_indices(240, 24, 2, 12)[0], 0)
        self.assertEqual(media.sample_indices(240, 24, 2, 12)[-1], 239)
        self.assertEqual(len(media.sample_indices(240, 24, 2, 12)), 12)
        self.assertEqual(media.sample_indices(1, 24, 2, 12), [0])
        self.assertEqual(media.sample_indices(3, 24, 60, 12), [0,1,2])
        self.assertEqual(media.sample_indices(3, 24, 60, 1), [0])

    def test_order_numbering_and_native_video(self):
        red = torch.zeros(2, 32, 64, 3); red[..., 0] = 1
        green = torch.zeros(1, 32, 64, 3); green[..., 1] = 1
        clip = torch.zeros(25, 8, 8, 3)
        video = SimpleNamespace(get_components=lambda: SimpleNamespace(images=clip, frame_rate=25))
        result = media.build_messages('test', '', {'image_10':green, 'image_2':red, 'image_3':None},
                                      {'video_7':video}, max_edge=16, max_video_frames=3)
        parts = result[0]['content']
        labels = [part['text'] for part in parts if part['type']=='text']
        self.assertIn('<Picture 1>', labels); self.assertIn('<Picture 2>', labels)
        self.assertIn('<Video 1> frame at 0.960s', labels)
        self.assertNotIn('<Picture 3>', labels)
        urls = [part['image_url']['url'] for part in parts if part['type']=='image_url']
        self.assertEqual(len(urls), 5)
        img = Image.open(io.BytesIO(base64.b64decode(urls[0].split(',',1)[1])))
        self.assertEqual(img.size, (16,8))
        self.assertGreater(img.getpixel((0,0))[0], 240)

    def test_limits(self):
        batch = torch.zeros(4, 16, 16, 3)
        with self.assertRaisesRegex(ValueError, 'visual items'):
            media.build_messages('x', videos={'video_0':batch}, max_visual_items=1)
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            media.build_messages('x', images={'image_0':batch[:0]})
        with self.assertRaisesRegex(ValueError, 'max_payload_mb'):
            media.build_messages('x', images={'image_0':batch}, max_payload_mb=0)

    def test_skills(self):
        self.assertGreaterEqual(len(skill_library.names()), 11)
        self.assertIn('Krea 2', skill_library.load('krea-2'))
        self.assertEqual(skill_library.compose('(none)', 'base', 'extra'), 'base\n\nextra')
        with self.assertRaises(ValueError):
            skill_library.load('../../secret')
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LLMCLIENT_SKILLS_DIR':temp}):
            path = Path(temp)/'krea-2'/'SKILL.md'; path.parent.mkdir()
            path.write_text('---\nname: example\n---\nOne', encoding='utf-8')
            self.assertEqual(skill_library.load('krea-2'), 'One')
            before = skill_library.fingerprint('krea-2')
            path.write_text('Two', encoding='utf-8')
            self.assertNotEqual(before, skill_library.fingerprint('krea-2'))

    def test_h3_style_context(self):
        styles = [name for name in skill_library.names() if name.startswith('minimax-h3-style-')]
        self.assertEqual(len(styles), 8)
        for name in styles:
            context = skill_library.load(name)
            self.assertIn('integrated_multimodal_description:', context)
            self.assertIn('retention_analysis:', context)
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'LLMCLIENT_SKILLS_DIR': temp}):
            before = skill_library.fingerprint(styles[0])
            path = Path(temp) / 'minimax-h3-video-base' / 'SKILL.md'
            path.parent.mkdir()
            path.write_text('Revised format')
            self.assertNotEqual(before, skill_library.fingerprint(styles[0]))


class HTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.model_ids = ['test-model']
        self.release = asyncio.Event()
        self.mode = 'normal'
        app = web.Application()
        app.router.add_get('/v1/models', self.models)
        app.router.add_post('/v1/chat/completions', self.chat)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.provider = client.Provider(f'http://127.0.0.1:{self.runner.addresses[0][1]}', key_env='')

    async def asyncTearDown(self):
        self.release.set()
        await self.runner.cleanup()

    async def models(self, request):
        return web.json_response({'data':[{'id':name} for name in self.model_ids]})

    async def chat(self, request):
        payload = await request.json()
        self.requests.append(payload)
        if self.mode == 'error':
            return web.json_response({'error':'not supported'}, status=400)
        if self.mode == 'wait':
            await self.release.wait()
            return web.json_response({'choices':[{'message':{'content':'late'}, 'finish_reason':'stop'}]})
        if self.mode == 'json':
            return web.json_response({'choices':[{'message':{'content':'{"ok":true}'}, 'finish_reason':'stop'}]})
        if self.mode == 'bad_json':
            return web.json_response({'choices':[{'message':{'content':'[1]'}, 'finish_reason':'stop'}]})
        if self.mode == 'gemma':
            return web.json_response({'choices':[{'message':{'content':'<|channel>thought\nnotes<channel|>final'}, 'finish_reason':'stop'}]})
        if payload.get('response_format', {}).get('type') == 'json_schema':
            self.assertEqual(payload['messages'][0]['role'], 'system')
            schema = payload['response_format']['json_schema']['schema']
            answer = {'ok': True} if schema['properties']['answer']['type'] == 'object' else 'done'
            body = json.dumps({'explanation': 'checked', 'answer': answer})
            return web.json_response({'choices':[{'message':{'content':body}, 'finish_reason':'stop'}]})
        if not payload['stream']:
            return web.json_response({'choices':[{'message':{'content':'<think>private</think>answer'},'finish_reason':'stop'}]})
        response = web.StreamResponse(headers={'Content-Type':'text/event-stream'})
        await response.prepare(request)
        thought = 'think '
        if payload.get('continue_final_message') == 'reasoning_content':
            thought = payload['messages'][-1]['reasoning_content'] + thought + payload['reasoning_budget_message']
        for delta, reason in [({'reasoning_content':thought},None), ({'content':'hel'},None), ({'content':'lo'},None)]:
            event = ('data: '+json.dumps({'choices':[{'delta':delta,'finish_reason':reason}]})+'\n\n').encode()
            # Split a single SSE event at an arbitrary TCP chunk boundary.
            await response.write(event[:17]); await response.write(event[17:])
        if self.mode != 'truncated':
            await response.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        await response.write_eof()
        return response

    async def call(self, **kwargs):
        return await client.complete(self.provider, [{'role':'user','content':'test'}], {}, **kwargs)

    async def test_stream_auto(self):
        result = await self.call()
        self.assertEqual(result, client.Reply('hello', 'think'))
        self.assertEqual(self.requests[0]['model'], 'test-model')

    async def test_non_stream(self):
        self.assertEqual(await self.call(stream=False), client.Reply('answer','private'))

    async def test_llama_thinking_controls(self):
        self.mode = 'gemma'
        for setting, enabled in [('on', True), ('off', False)]:
            result = await self.call(stream=False, reasoning_mode='llama.cpp · thinking ' + setting)
            self.assertEqual(result, client.Reply('final', 'notes'))
            self.assertEqual(self.requests[-1]['chat_template_kwargs'], {'enable_thinking': enabled})
            self.assertEqual(self.requests[-1]['reasoning_format'], 'deepseek')
        await self.call()
        self.assertNotIn('chat_template_kwargs', self.requests[-1])

    async def test_explained_answer(self):
        messages = [{'role':'system', 'content':'Original'}, {'role':'user', 'content':'A task'}]
        for fmt in ['text', 'json_object']:
            result = await client.complete(self.provider, messages, client.request_options(output_format=fmt),
                                           reasoning_mode='Explain answer')
            self.assertEqual(result.reasoning, 'checked')
            if fmt == 'text':
                self.assertEqual(result.text, 'done')
            else:
                self.assertEqual(json.loads(result.text), {'ok': True})
            self.assertTrue(self.requests[-1]['messages'][0]['content'].startswith('Original'))
            self.assertEqual(messages[0]['content'], 'Original')

    async def test_start_in_reasoning(self):
        result = await self.call(reasoning_mode=client.REASONING_FIRST, reasoning_budget=48)
        self.assertEqual(result, client.Reply('hello', 'think'))
        request = self.requests[-1]
        self.assertEqual(request['reasoning_budget_tokens'], 48)
        self.assertEqual(request['continue_final_message'], 'reasoning_content')
        self.assertFalse(request['add_generation_prompt'])
        self.assertEqual(request['messages'][-1], {'role':'assistant', 'content':'', 'reasoning_content':client.THOUGHT_PREFIX})

    async def test_model_ambiguity(self):
        self.model_ids = ['a','b']
        with self.assertRaisesRegex(client.LLMError, 'a, b'):
            await self.call()
        self.provider = client.Provider(self.provider.base_url, 'b', '')
        await self.call()
        self.assertEqual(self.requests[0]['model'], 'b')

    async def test_json_mode(self):
        self.mode = 'json'
        args = (self.provider,[{'role':'user','content':'JSON'}], {'response_format':{'type':'json_object'}})
        self.assertEqual(json.loads((await client.complete(*args)).text), {'ok':True})
        self.mode = 'bad_json'
        with self.assertRaisesRegex(client.LLMError, 'JSON object'):
            await client.complete(*args)

    async def test_http_error(self):
        self.mode = 'error'
        with self.assertRaisesRegex(client.LLMError, 'HTTP 400'):
            await self.call()

    async def test_truncation(self):
        self.mode = 'truncated'
        with self.assertRaisesRegex(client.LLMError, 'completion marker'):
            await self.call()

    async def test_interrupt(self):
        self.mode = 'wait'
        def interrupt():
            if self.requests:
                raise RuntimeError('interrupted')
        with self.assertRaisesRegex(RuntimeError, 'interrupted'):
            await asyncio.wait_for(self.call(interrupt=interrupt), 2)

    async def test_timeout(self):
        self.mode = 'wait'
        with self.assertRaisesRegex(client.LLMError, 'TimeoutError'):
            await self.call(timeout=0.1)


if __name__ == '__main__':
    unittest.main()
