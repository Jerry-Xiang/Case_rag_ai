# -*- coding: utf-8 -*-
"""
ReActOptimizer - ReAct优化代理
使用ReAct模式思考和改写模糊语义提示词，选择最清晰的指令获取数据
"""

import json
from typing import Dict, Iterator, List, Literal, Optional, Tuple, Union

from qwen_agent.agents.react_chat import ReActChat, PROMPT_REACT, TOOL_DESC
from qwen_agent.llm import BaseChatModel
from qwen_agent.llm.schema import ASSISTANT, DEFAULT_SYSTEM_MESSAGE, Message
from qwen_agent.tools import BaseTool
from qwen_agent.utils.utils import format_as_text_message, merge_generate_cfgs


PROMPT_REACT_OPTIMIZER = """你是一个语义优化和推理专家。你需要使用ReAct模式来思考和优化用户的模糊语义。

用户输入可能存在以下问题：
1. 语义不完整或模糊
2. 存在歧义
3. 需要多步推理才能理解真实意图
4. 包含多个意图

你的任务：
1. 分析用户输入的语义，识别潜在的真实意图
2. 如果存在多个意图，选择最清晰、最重要的一个
3. 将模糊的语义改写为清晰明确的指令
4. 使用工具获取相关数据
5. 给出最终答案

可用工具：
{tool_descs}

使用格式：
Question: 用户的原始问题
Thought: 分析语义，识别意图，思考需要做什么
Action: 选择的工具，应该是[{tool_names}]中的一个
Action Input: 工具输入（使用改写后的清晰指令）
Observation: 工具执行结果
...（可以重复多次）
Thought: 我已经理解了用户的意图并获取了所需数据，现在可以给出最终答案
Final Answer: 最终回答（包含思考过程和结果）

Begin!

Question: {query}
Thought: """


class ReActOptimizer(ReActChat):
    """ReAct优化代理，思考和改写模糊语义提示词"""

    def __init__(self,
                 function_list: Optional[List[Union[str, Dict, BaseTool]]] = None,
                 llm: Optional[Union[Dict, BaseChatModel]] = None,
                 name: str = 'ReActOptimizer',
                 description: str = 'ReAct优化代理，使用ReAct模式思考和改写模糊语义提示词，选择最清晰的指令获取数据',
                 files: Optional[List[str]] = None,
                 **kwargs):
        system_message = '''你是一个语义优化和推理专家。
当收到模糊、复杂或语义不完整的指令时，你应该：
1. 先分析用户输入，识别潜在的真实意图
2. 如果存在多个意图，选择最清晰、最重要的一个进行处理
3. 将模糊语义改写为清晰明确的指令
4. 使用ReAct模式进行多步推理和工具调用
5. 给出完整的思考过程和最终答案

提示词和回答总是用中文给用户。'''

        super().__init__(
            function_list=function_list,
            llm=llm,
            system_message=system_message,
            name=name,
            description=description,
            files=files,
            **kwargs
        )

    def _prepend_react_prompt(self, messages: List[Message], lang: Literal['en', 'zh']) -> List[Message]:
        tool_descs = []
        for f in self.function_map.values():
            function = f.function
            name = function.get('name', None)
            name_for_human = function.get('name_for_human', name)
            name_for_model = function.get('name_for_model', name)
            assert name_for_human and name_for_model
            args_format = function.get('args_format', '')
            tool_descs.append(
                TOOL_DESC.format(name_for_human=name_for_human,
                                 name_for_model=name_for_model,
                                 description_for_model=function['description'],
                                 parameters=json.dumps(function['parameters'], ensure_ascii=False),
                                 args_format=args_format).rstrip())
        tool_descs = '\n\n'.join(tool_descs)
        tool_names = ','.join(tool.name for tool in self.function_map.values())
        text_messages = [format_as_text_message(m, add_upload_info=True, lang=lang) for m in messages]
        text_messages[-1].content = PROMPT_REACT_OPTIMIZER.format(
            tool_descs=tool_descs,
            tool_names=tool_names,
            query=text_messages[-1].content,
        )
        return text_messages