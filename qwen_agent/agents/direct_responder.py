# -*- coding: utf-8 -*-
"""
DirectResponder - 直接响应代理
处理清晰明确的指令，即时响应获取数据
"""

from typing import Dict, Iterator, List, Optional, Union

from qwen_agent.agents.assistant import Assistant
from qwen_agent.llm import BaseChatModel
from qwen_agent.tools import BaseTool


class DirectResponder(Assistant):
    """直接响应代理，处理清晰明确的指令"""

    def __init__(self,
                 function_list: Optional[List[Union[str, Dict, BaseTool]]] = None,
                 llm: Optional[Union[Dict, BaseChatModel]] = None,
                 name: str = 'DirectResponder',
                 description: str = '直接响应代理，处理清晰明确的指令，即时调用工具获取数据并回答',
                 files: Optional[List[str]] = None,
                 rag_cfg: Optional[Dict] = None):
        system_message = '''你是一个高效的直接响应助手。
当收到清晰明确的指令时，你应该：
1. 立即识别用户的意图和需要调用的工具
2. 直接调用相关工具获取数据
3. 使用获取的数据给出简洁准确的回答

提示词和回答总是用中文给用户。'''

        super().__init__(
            function_list=function_list,
            llm=llm,
            system_message=system_message,
            name=name,
            description=description,
            files=files,
            rag_cfg=rag_cfg
        )