from comfy_api.latest import ComfyExtension

from .nodes import LiteLLMChat, LiteLLMProvider, LiteLLMSkill

WEB_DIRECTORY = "./web"


class LLMClientLiteExtension(ComfyExtension):
    async def get_node_list(self):
        return [LiteLLMProvider, LiteLLMSkill, LiteLLMChat]


async def comfy_entrypoint():
    return LLMClientLiteExtension()
