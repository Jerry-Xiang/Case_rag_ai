# -*- coding: utf-8 -*-
"""
语义分析路由器 - SemanticRouter
根据用户指令的语义清晰度，智能选择处理模式：
1. Chat - 纯对话模式：直接回答，无需调用工具
2. Direct - 直接响应模式：即时调用工具获取数据，生成自然语言回答
3. Complex - ReAct模式：多步推理，最多3次工具调用

包含三轮兜底机制：当找不到对应数据时，给用户明确反馈，避免无限循环
"""

import copy
import json
import time
import re
from typing import Dict, Iterator, List, Literal, Optional, Union

from qwen_agent.agents.assistant import Assistant
from qwen_agent.llm import BaseChatModel
from qwen_agent.llm.schema import ASSISTANT, FUNCTION, SYSTEM, USER, Message
from qwen_agent.log import logger
from qwen_agent.settings import MAX_LLM_CALL_PER_RUN
from qwen_agent.tools import BaseTool
from qwen_agent.utils.utils import format_as_text_message


SEMANTIC_ANALYSIS_PROMPT = """你是一个语义分析专家，负责分析用户指令的类型。

请根据以下标准对用户输入进行分类：

【Chat - 纯对话】：
- 用户只是在聊天、问候或自我介绍
- 不需要调用任何工具，可以直接回答
- 例如："你好"、"我是谁"、"你叫什么名字"、"谢谢"、"再见"

【Direct - 清晰明确指令】：
- 用户意图非常明确，不需要进一步追问
- 可以直接调用工具获取数据或直接回答
- 例如："介绍下雇主责任险"、"画一只熊猫"、"帮我计算1+1"

【Complex - 模糊/复杂指令】：
- 用户意图不明确，存在歧义
- 需要多步推理或多工具协作
- 语义不完整，需要补充信息
- 例如："帮我看看那个东西"、"分析一下这个问题"、"关于保险你能说什么"

分类规则：
1. 首先检查是否是纯对话（Chat），如果是，直接回答不需要调用工具
2. 检查是否包含明确的实体、动作和目标
3. 检查是否需要额外的上下文信息
4. 检查是否需要多步推理

请输出以下格式：
Type: Chat 或 Direct 或 Complex
Reason: 简要说明分类理由

注意：只输出上述两行，不要添加其他内容。"""


TOOL_DESC = """工具名称（中文）：{name_for_human}
工具名称（英文）：{name_for_model}
工具描述：{description_for_model}
参数格式：{args_format}
参数：{parameters}"""


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

重要规则：
- 最多只能调用工具 **3 次**，3次后必须给出最终回答
- 如果工具返回"未找到"、"无结果"、"找不到"等表示没有数据的信息，不要继续调用工具，直接给出兜底回答
- 如果经过3次尝试仍无法获取有效数据，必须停止调用工具，给出明确的兜底回答
- 兜底回答格式："抱歉，我无法找到相关信息。"

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


class SemanticRouter(Assistant):
    """语义分析路由器，根据用户指令类型选择处理模式"""

    def __init__(self,
                 function_list: Optional[List[Union[str, Dict, BaseTool]]] = None,
                 llm: Optional[Union[Dict, BaseChatModel]] = None,
                 name: str = 'SemanticRouter',
                 description: str = '语义分析路由器，智能选择处理模式',
                 files: Optional[List[str]] = None,
                 rag_cfg: Optional[Dict] = None,
                 **kwargs):
        system_message = '''你是一个智能语义分析助手。
当收到用户指令时，你应该：
1. 分析指令的语义清晰度
2. 如果是清晰明确的指令，直接调用相关工具获取数据并回答
- 查询保险相关信息，优先利用检索工具retriever从本地知识库中查找最相关的信息。
- 如果需要联网搜索，使用 tavily_search 工具从互联网上搜索，显示搜索结果前 5 条。                             
- 如果需要绘制一幅图像，得到图像的url，用 `plt.show()` 展示图像。 
3. 如果是模糊或复杂的指令，使用ReAct模式进行思考和优化，然后回答
-先分析用户输入，识别潜在的真实意图
-如果存在多个意图，选择最清晰、最重要的一个进行处理
-将模糊语义改写为清晰明确的指令
-使用ReAct模式进行多步推理和工具调用
-给出完整的思考过程和最终答案

重要规则：
- 如果工具返回"未找到"、"无结果"、"找不到"等表示没有数据的信息，不要继续调用工具
- 如果经过多次尝试仍无法获取有效数据，必须停止调用工具，给出明确的兜底回答
- 兜底回答格式："抱歉，我无法找到关于{用户问题关键词}的相关信息。"

提示词和回答总是用中文给用户。'''

        super().__init__(
            function_list=function_list,
            llm=llm,
            system_message=system_message,
            name=name,
            description=description,
            files=files,
            rag_cfg=rag_cfg,
            **kwargs
        )
        
        self.files = files or []
        self.max_tool_calls = 3

    def _run(self, messages: List[Message], lang: str = 'en', **kwargs) -> Iterator[List[Message]]:
        if not messages:
            yield [Message(role=ASSISTANT, content='请输入您的问题')]
            return

        last_message = messages[-1]
        user_query = last_message.content
        
        if isinstance(user_query, list):
            user_query = ' '.join(str(q) for q in user_query)
        elif not isinstance(user_query, str):
            user_query = str(user_query)

        analysis_result = self._analyze_semantic(user_query, lang=lang)
        logger.info(f'语义分析结果: {analysis_result}')

        extra_generate_cfg = {'lang': lang}
        if kwargs.get('seed') is not None:
            extra_generate_cfg['seed'] = kwargs['seed']

        if analysis_result.get('type') == 'Chat':
            yield from self._handle_chat_mode(messages, user_query, extra_generate_cfg)
        elif analysis_result.get('type') == 'Direct':
            yield from self._handle_direct_mode(messages, user_query, extra_generate_cfg, **kwargs)
        else:
            yield from self._handle_complex_mode(messages, user_query, extra_generate_cfg, **kwargs)

    def _handle_chat_mode(self, messages: List[Message], user_query: str, 
                          extra_generate_cfg: dict) -> Iterator[List[Message]]:
        """Chat模式：纯对话，直接调用LLM回答，不走工具调用和检索逻辑"""
        logger.info('Chat模式：直接调用LLM回答，不走工具调用和检索逻辑')
        
        final_output_stream = self._call_llm(messages=messages,
                                             functions=[],
                                             extra_generate_cfg=extra_generate_cfg)
        final_output_list: List[Message] = []
        for out in final_output_stream:
            if out:
                final_output_list.extend(out)
                yield out
        if not final_output_list:
            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]

    def _handle_direct_mode(self, messages: List[Message], user_query: str,
                            extra_generate_cfg: dict, **kwargs) -> Iterator[List[Message]]:
        """Direct模式：清晰明确指令，即时调用工具获取数据，生成自然语言回答

        流程：调用LLM判断工具 → 调用工具 → FUNCTION消息 → LLM生成最终回答
        """
        logger.info('Direct模式：开始处理')

        logger.info(f'Direct模式：原始消息: {messages}')
        # 只保留系统消息和最新的用户查询，清除之前的所有消息
        direct_messages = []
        latest_user_msg = None
        for msg in messages:
            logger.info(f'当前消息: {msg}')
            if msg.role == SYSTEM:
                direct_messages.append(msg)
            elif msg.role == USER:
                # 判断是否有值
                if msg.content and str(msg.content).strip():
                    latest_user_msg = msg
                    logger.info(f'Direct模式：保留最新的用户查询: {latest_user_msg}')
        if latest_user_msg is not None:    # 保留最新的用户查询
            direct_messages.append(latest_user_msg)    

        logger.info(f'Direct模式：清理后的消息: {direct_messages}')
        
        tool_name, tool_args = self._detect_tool_call(direct_messages, extra_generate_cfg)
        
        if tool_name:
            logger.info(f'Direct模式：检测到工具调用，工具名称: {tool_name}')
            yield from self._execute_tool_and_summarize(tool_name, tool_args, user_query,
                                                         direct_messages, extra_generate_cfg, **kwargs)
        else:
            logger.info('Direct模式：未检测到工具调用，走检索逻辑')
            yield from self._execute_retrieval_and_summarize(user_query, direct_messages,
                                                              extra_generate_cfg, **kwargs)

    def _handle_complex_mode(self, messages: List[Message], user_query: str,
                             extra_generate_cfg: dict, **kwargs) -> Iterator[List[Message]]:
        """Complex模式：模糊/复杂指令，使用ReAct模式进行多步推理
        
        流程：ReAct推理（最多3次工具调用）→ 检测有效结果 → 生成最终回答
        
        当未检测到工具调用时，继续下一轮让LLM改写语义后再尝试，最多3轮后退出。
        """
        logger.info('Complex模式：开始处理')
        
        logger.info(f'Complex模式：原始消息: {messages}')
        # 只保留系统消息和最新的用户查询，清除之前的所有消息
        complex_messages = []
        latest_user_msg = None
        for msg in messages:
            if msg.role == SYSTEM:
                complex_messages.append(msg)
            elif msg.role == USER:
                # 判断是否有值
                if msg.content and str(msg.content).strip():
                    latest_user_msg = msg
        if latest_user_msg is not None:    # 保留最新的用户查询
            complex_messages.append(latest_user_msg)    
        logger.info(f'Complex模式：清理后的消息: {complex_messages}')
        
        tool_call_count = 0
        has_valid_result = False
        last_tool_name = None
        last_tool_result = None
        response_messages = []
        
        tool_call_count = 0
        has_valid_result = False
        last_tool_name = None
        last_tool_result = None
        response_messages = []
        
        while tool_call_count < self.max_tool_calls:
            tool_call_count += 1
            logger.info(f'Complex模式：第 {tool_call_count}/{self.max_tool_calls} 轮工具调用')
            
            # 让LLM改写语义并选择相似度最高的版本
            complex_messages = self._rewrite_query_and_select_best(complex_messages, user_query)
            logger.info(f'Complex模式：改写后的消息: {complex_messages}')

            # 只保留系统消息和最新的用户查询，清除之前的所有消息
            complex_messages1 = []
            for msg in complex_messages:
                if msg.role == SYSTEM:
                    complex_messages1.append(msg)
                elif msg.role == USER:
                    complex_messages1.append(msg) 
            logger.info(f'Complex模式：清理后的消息: {complex_messages1}')            
            
            tool_name, tool_args = self._detect_tool_call(complex_messages1, extra_generate_cfg)
            
            if not tool_name:
                logger.info('Complex模式：未检测到工具调用，继续下一轮让LLM改写语义')
                if tool_call_count >= self.max_tool_calls:
                    logger.info('Complex模式：已达到最大轮数，退出循环')
                    break
                continue
            
            logger.info(f'Complex模式：检测到工具调用，工具名称: {tool_name}')
            
            try:
                tool_result = self._execute_tool(tool_name, tool_args, user_query,
                                                 complex_messages, extra_generate_cfg, **kwargs)
                logger.info(f'Complex模式：工具 {tool_name} 返回结果: {tool_result}')
                fn_msg = Message(role=FUNCTION, name=tool_name, content=tool_result)
                complex_messages.append(fn_msg)
                response_messages.append(fn_msg)
                
                if not self._is_empty_result(tool_result):
                    has_valid_result = True
                    last_tool_name = tool_name
                    last_tool_result = tool_result
                    logger.info('Complex模式：检测到有效结果')
                    
                    if not self._requires_llm_post_process(tool_name):
                        logger.info(f'Complex模式：工具 {tool_name} 不需要LLM后处理，直接返回结果')
                        yield from self._format_tool_result(tool_name, tool_result)
                        return
                    break
                else:
                    logger.info('Complex模式：工具返回空结果，继续下一轮')
            except Exception as e:
                logger.error(f'Complex模式工具调用失败: {e}')
                if tool_call_count >= self.max_tool_calls:
                    logger.info('Complex模式：已达到最大轮数，退出循环')
                    break
                continue
        
        if has_valid_result:
            if self._requires_llm_post_process(last_tool_name):
                logger.info('Complex模式：调用LLM生成最终回答')
                yield from self._generate_final_answer(user_query, complex_messages, extra_generate_cfg)
            else:
                yield from self._format_tool_result(last_tool_name, last_tool_result)
        else:
            logger.info('Complex模式：未获取有效结果，触发兜底机制')
            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]

    def _detect_tool_call(self, messages: List[Message], extra_generate_cfg: dict) -> tuple:
        """调用LLM获取工具调用决策，检测函数调用格式或ReAct格式的工具调用
        
        返回：(tool_name, tool_args)
        """
        logger.info('调用LLM获取工具调用决策')
        
        output_stream = self._call_llm(messages=messages,
                                       functions=[func.function for func in self.function_map.values()],
                                       extra_generate_cfg=extra_generate_cfg)
        output: List[Message] = []
        for out in output_stream:
            if out:
                output.extend(out)
        
        if not output:
            logger.info('LLM返回空结果，未检测到工具调用')
            return None, None
        
        for out in output:
            use_tool, tool_name, tool_args, _ = self._parse_tool_call(out)
            if use_tool and tool_name:
                logger.info(f'检测到工具调用: {tool_name}')
                return tool_name, tool_args
        
        logger.info('未检测到工具调用')
        return None, None

    def _parse_tool_call(self, message) -> tuple:
        """解析工具调用，支持函数调用格式和ReAct格式"""
        func_name = None
        func_args = None
        text = ''
        
        if hasattr(message, 'function_call') and message.function_call:
            func_name = message.function_call.name
            func_args = message.function_call.arguments
            text = message.content or ''
        elif hasattr(message, 'content'):
            text = message.content
            if isinstance(text, str):
                i = text.rfind('\nAction:')
                j = text.rfind('\nAction Input:')
                k = text.rfind('\nObservation:')
                if 0 <= i < j:
                    if k < j:
                        text = text.rstrip() + '\nObservation:'
                    k = text.rfind('\nObservation:')
                    func_name = text[i + len('\nAction:'):j].strip()
                    func_args = text[j + len('\nAction Input:'):k].strip()
        
        return (func_name is not None), func_name, func_args, text

    def _execute_tool_and_summarize(self, tool_name: str, tool_args, user_query: str,
                                     messages: List[Message], extra_generate_cfg: dict,
                                     **kwargs) -> Iterator[List[Message]]:
        """执行工具调用并生成最终回答（Direct模式专用）
        
        对于my_image_gen工具，直接返回结果，不需要LLM解释。
        对于tavily搜索工具，需要调用LLM提炼信息后显示给用户。
        """
        logger.info(f'执行工具调用：{tool_name}')
        
        try:
            tool_args = self._build_tool_args(tool_name, tool_args, user_query)
            
            if tool_name == 'retrieval':
                files = kwargs.get('files', getattr(self, 'files', []))
                if tool_args:
                    try:
                        args_dict = json.loads(tool_args)
                    except:
                        args_dict = {}
                    args_dict['files'] = files
                    args_dict['query'] = user_query
                    tool_args = json.dumps(args_dict, ensure_ascii=False)
                else:
                    tool_args = json.dumps({'query': user_query, 'files': files}, ensure_ascii=False)
            
            if not tool_args:
                logger.info('参数构建为空')
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                return
            
            tool_result = self._call_tool(tool_name, tool_args, messages=messages, **kwargs)
            logger.info(f'工具调用结果: {str(tool_result)[:200]}...')
            
            if not self._requires_llm_post_process(tool_name):
                logger.info(f'工具 {tool_name} 不需要LLM后处理，直接返回结果')
                yield from self._format_tool_result(tool_name, tool_result)
            else:
                if tool_name == 'retrieval' and tool_result != '':
                    pass
                else:    
                    # 对于需要LLM后处理的工具，如果结果为空则返回fallback
                    if self._is_empty_result(tool_result):
                        logger.info('工具返回空结果')
                        yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                        return
                
                logger.info('调用LLM生成最终回答')
                yield from self._generate_final_answer_with_tool_result(user_query, messages,
                                                                       tool_name, tool_result,
                                                                       extra_generate_cfg)
        except Exception as e:
            logger.error(f'工具调用失败: {e}')
            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]

    def _execute_retrieval_and_summarize(self, user_query: str, messages: List[Message],
                                          extra_generate_cfg: dict, **kwargs) -> Iterator[List[Message]]:
        """执行检索并生成最终回答（Direct模式专用）
        
        只保留最新的用户查询和系统消息，确保检索基于当前问题。
        """
        logger.info('执行检索逻辑')
        
        retrieval_tool_name = self._find_retrieval_tool()
        if not retrieval_tool_name:
            logger.info('未找到retrieval工具，直接调用LLM回答')
            yield from self._generate_final_answer(user_query, messages, extra_generate_cfg)
            return
        
        try:
            files = kwargs.get('files', getattr(self, 'files', []))
            tool_args = json.dumps({'query': user_query, 'files': files}, ensure_ascii=False)
            logger.info(f'检索参数: {tool_args}')
            
            tool_result = self._call_tool(retrieval_tool_name, tool_args, messages=messages, **kwargs)
            logger.info(f'检索结果: {str(tool_result)[:500]}...')
            
            if self._is_empty_result(tool_result):
                logger.info('检索返回空结果')
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                return
            
            logger.info('调用LLM生成最终回答')
            yield from self._generate_final_answer_with_tool_result(user_query, messages,
                                                                     retrieval_tool_name, tool_result,
                                                                     extra_generate_cfg)
        except Exception as e:
            logger.error(f'检索失败: {e}')
            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]

    def _execute_tool(self, tool_name: str, tool_args, user_query: str,
                      messages: List[Message], extra_generate_cfg: dict,
                      **kwargs) -> str:
        """执行工具调用，返回工具结果"""
        tool_args = self._build_tool_args(tool_name, tool_args, user_query)
        
        if tool_name == 'retrieval':
            files = kwargs.get('files', getattr(self, 'files', []))
            if tool_args:
                try:
                    args_dict = json.loads(tool_args)
                except:
                    args_dict = {}
                args_dict['files'] = files
                args_dict['query'] = user_query
                tool_args = json.dumps(args_dict, ensure_ascii=False)
            else:
                tool_args = json.dumps({'query': user_query, 'files': files}, ensure_ascii=False)
        
        if not tool_args:
            return '工具参数构建失败'
        
        return self._call_tool(tool_name, tool_args, messages=messages, **kwargs)

    def _generate_final_answer(self, user_query: str, messages: List[Message],
                               extra_generate_cfg: dict) -> Iterator[List[Message]]:
        """生成最终回答"""
        final_output_stream = self._call_llm(messages=messages,
                                             functions=[],
                                             extra_generate_cfg=extra_generate_cfg)
        final_output_list: List[Message] = []
        for out in final_output_stream:
            if out:
                final_output_list.extend(out)
                yield out
        if not final_output_list:
            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]

    def _generate_final_answer_with_tool_result(self, user_query: str, messages: List[Message],
                                                 tool_name: str, tool_result: str,
                                                 extra_generate_cfg: dict) -> Iterator[List[Message]]:
        """结合工具结果生成最终回答
        
        只保留系统消息、当前用户查询和工具结果，确保回答基于最新数据。
        """
        system_msg = None
        for msg in messages:
            if msg.role == SYSTEM:
                system_msg = msg
                break
        
        fn_msg = Message(role=FUNCTION, name=tool_name, content=tool_result)
        user_msg = Message(role=USER, content=user_query)
        
        final_messages = []
        if system_msg:
            final_messages.append(system_msg)
        final_messages.append(user_msg)
        final_messages.append(fn_msg)
        
        yield from self._generate_final_answer(user_query, final_messages, extra_generate_cfg)

    def _format_tool_result(self, tool_name: str, tool_result) -> Iterator[List[Message]]:
        """格式化工具结果并返回"""
        if tool_name == 'my_image_gen':
            image_content = self._parse_image_result(str(tool_result))
            yield [Message(role=ASSISTANT, content=image_content)]
        elif tool_name == 'retrieval':
            formatted_result = self._format_retrieval_result(tool_result)
            yield [Message(role=ASSISTANT, content=formatted_result)]
        else:
            yield [Message(role=ASSISTANT, content=str(tool_result))]
    
    def _format_retrieval_result(self, tool_result) -> str:
        """格式化检索工具返回的结果"""
        if not tool_result:
            return '未找到相关信息'
        
        if isinstance(tool_result, list):
            formatted = '根据检索到的资料，为您整理如下：\n\n'
            for i, item in enumerate(tool_result, 1):
                if isinstance(item, dict):
                    url = item.get('url', '')
                    text = item.get('text', '')
                    if isinstance(text, list):
                        text = '\n'.join(text)
                    if url or text:
                        formatted += f'【来源 {i}】'
                        if url:
                            formatted += f' {url}\n'
                        if text:
                            formatted += f'{text}\n\n'
                else:
                    formatted += f'【来源 {i}】{str(item)}\n\n'
            return formatted.strip()
        
        return str(tool_result)

    def _find_retrieval_tool(self) -> Optional[str]:
        """查找检索工具"""
        for name, func in self.function_map.items():
            if hasattr(func, 'function') and func.function.get('name') == 'retrieval':
                return name
        return None

    def _build_tool_args(self, tool_name: str, tool_args, user_query: str) -> Optional[str]:
        """构建工具参数，当参数为空时从用户查询中自动填充"""
        if tool_args and str(tool_args).strip() and str(tool_args).strip() != '{}':
            if isinstance(tool_args, dict):
                return json.dumps(tool_args, ensure_ascii=False)
            elif isinstance(tool_args, str):
                return tool_args
            else:
                return str(tool_args)
        
        if tool_name not in self.function_map:
            logger.warning(f'工具 {tool_name} 不存在于 function_map 中')
            return None
        
        func_def = self.function_map[tool_name].function
        parameters = func_def.get('parameters', {})
        
        required_fields = []
        properties = {}
        
        if isinstance(parameters, list):
            for param in parameters:
                if param.get('required', False):
                    required_fields.append(param['name'])
                properties[param['name']] = {'type': param.get('type', 'string')}
        elif isinstance(parameters, dict):
            required_fields = parameters.get('required', [])
            properties = parameters.get('properties', {})
        
        if not required_fields:
            return '{}'
        
        args_dict = {}
        for field in required_fields:
            if field in properties:
                field_type = properties[field].get('type', 'string')
                if field_type == 'string':
                    args_dict[field] = user_query
        
        if args_dict:
            return json.dumps(args_dict, ensure_ascii=False)
        
        return None

    def _is_empty_result(self, text) -> bool:
        """判断是否为空结果或未找到数据"""
        if not text:
            return True
            
        if isinstance(text, list):
            if len(text) == 0:
                return True
            for item in text:
                if isinstance(item, dict):
                    url = item.get('url', '')
                    text_content = item.get('text', '')
                    if url or text_content:
                        return False
                elif isinstance(item, str):
                    if item.strip():
                        return False
            return True
            
        text_str = str(text).strip()
        if len(text_str) < 5:
            return True
            
        if text_str == '[]':
            return True
            
        try:
            parsed_data = json.loads(text_str)
            if isinstance(parsed_data, list):
                if len(parsed_data) == 0:
                    return True
                for item in parsed_data:
                    if isinstance(item, dict):
                        url = item.get('url', '')
                        text_content = item.get('text', '')
                        if isinstance(text_content, list):
                            text_content = ''.join(text_content)
                        if url or text_content:
                            return False
                    elif isinstance(item, str):
                        if item.strip():
                            return False
                return True
            elif isinstance(parsed_data, dict):
                if not parsed_data:
                    return True
                for key, value in parsed_data.items():
                    if isinstance(value, list) and value:
                        return False
                    elif isinstance(value, str) and value.strip():
                        return False
                    elif value:
                        return False
                return True
        except (json.JSONDecodeError, TypeError):
            pass
            
        text_lower = text_str.lower()
        if 'error' in text_lower and 'occurred' in text_lower:
            return True
            
        if len(text_str) < 50:
            empty_keywords = ['未找到', '无结果', '找不到', '没有相关', '无法回答', 
                             'not found', 'no result', 'no data', 'empty']
            for keyword in empty_keywords:
                if keyword in text_str or keyword.lower() in text_lower:
                    return True
            
        return False

    def _requires_llm_post_process(self, tool_name: str) -> bool:
        """判断工具调用后是否需要LLM解释和压缩结果
        
        my_image_gen工具直接返回结果，不需要LLM解释。 
        tavily搜索工具需要调用LLM提炼信息后显示给用户。
        """
        tools_without_post_process = ['my_image_gen'] #, 'retrieval' , 'code_interpreter'
        return tool_name not in tools_without_post_process

    def _parse_image_result(self, tool_result: str) -> str:
        """解析图片工具返回的JSON，提取image_url"""
        try:
            import json5
            result = json5.loads(tool_result)
            image_url = result.get('image_url', '')
            if image_url:
                return f'![图片]({image_url})'
        except Exception as e:
            logger.error(f'解析图片工具结果失败: {e}')
        return str(tool_result)

    def _get_fallback_response(self, query: str) -> str:
        """生成兜底回复"""
        keywords = self._extract_keywords(query)
        if keywords:
            return f'🤔 抱歉，我无法找到关于「{keywords}」的相关信息。您可以尝试：\n\n1. 提供更具体的关键词\n2. 检查拼写是否正确\n3. 尝试其他相关问题'
        return '🤔 抱歉，我无法找到相关信息。您可以尝试提供更具体的关键词或检查拼写是否正确。'

    def _extract_keywords(self, query) -> str:
        """提取查询中的关键词"""
        if isinstance(query, list):
            query = ' '.join(str(q) for q in query)
        elif not isinstance(query, str):
            query = str(query)
        keywords = re.findall(r'[\u4e00-\u9fa5]+', query)
        if keywords:
            return '、'.join(keywords[:3])
        return ''

    def _analyze_semantic(self, query: str, lang: str = 'en') -> Dict:
        """分析用户指令的语义类型"""
        chat_keywords = ['你好', '您好', '嗨', '哈喽', 'hello', 'hi', '嘿', '嘿呀', 
                         '再见', '拜拜', 'bye', '谢谢', '感谢', 'thanks', 'thank you',
                         '你是谁', '你叫什么', '名字', '自我介绍', '你好吗', '最近好吗']
        
        query_lower = query.strip().lower()
        for keyword in chat_keywords:
            if keyword in query or keyword.lower() in query_lower:
                logger.info(f'快速匹配到纯对话关键词: {keyword}')
                return {'type': 'Chat', 'reason': '快速匹配到纯对话关键词'}

        prompt = SEMANTIC_ANALYSIS_PROMPT
        messages = [
            Message(role=SYSTEM, content=prompt),
            Message(role='user', content=query)
        ]

        try:
            response = list(self._call_llm(messages=messages, stream=False))
            if response:
                last_chunk = response[-1]
                if isinstance(last_chunk, list) and last_chunk:
                    result_text = last_chunk[-1].content
                elif hasattr(last_chunk, 'content'):
                    result_text = last_chunk.content
                else:
                    result_text = str(last_chunk)
                return self._parse_analysis_result(result_text)
        except Exception as e:
            logger.warning(f"语义分析失败: {e}")
        
        return {'type': 'Complex', 'reason': '分析失败，默认按复杂语义处理'}

    def _parse_analysis_result(self, text: str) -> Dict:
        """解析语义分析结果"""
        lines = text.strip().split('\n')
        result = {'type': 'Complex', 'reason': '未识别的分析结果'}

        for line in lines:
            line = line.strip()
            if line.startswith('Type:'):
                result['type'] = line.split(':', 1)[1].strip()
            elif line.startswith('Reason:'):
                result['reason'] = line.split(':', 1)[1].strip()

        if result['type'] not in ['Chat', 'Direct', 'Complex']:
            result['type'] = 'Complex'

        return result

    def _optimize_messages_with_react(self, messages: List[Message], lang: Literal['en', 'zh']) -> List[Message]:
        """使用ReAct模式优化消息"""
        tool_descs = []
        if hasattr(self, 'function_map'):
            for f in self.function_map.values():
                function = f.function
                name = function.get('name', None)
                name_for_human = function.get('name_for_human', name)
                name_for_model = function.get('name_for_model', name)
                if name_for_human and name_for_model:
                    args_format = function.get('args_format', '')
                    tool_descs.append(
                        TOOL_DESC.format(name_for_human=name_for_human,
                                         name_for_model=name_for_model,
                                         description_for_model=function['description'],
                                         parameters=json.dumps(function['parameters'], ensure_ascii=False),
                                         args_format=args_format).rstrip())
        tool_descs = '\n\n'.join(tool_descs)
        tool_names = ','.join(tool.name for tool in self.function_map.values()) if hasattr(self, 'function_map') else ''

        text_messages = [format_as_text_message(m, add_upload_info=True, lang=lang) for m in messages]
        if text_messages:
            text_messages[-1].content = PROMPT_REACT_OPTIMIZER.format(
                tool_descs=tool_descs,
                tool_names=tool_names,
                query=text_messages[-1].content,
            )
        return text_messages

    def _rewrite_query_and_select_best(self, messages: List[Message], original_query: str) -> List[Message]:
        """让LLM改写语义并选择相似度最高的版本
        
        Args:
            messages: 当前消息列表
            original_query: 原始查询语句
            
        Returns:
            包含改写后语义的最新消息列表
        """
        logger.info('开始改写语义并选择相似度最高的版本')
        
        # 构造改写提示词
        rewrite_prompt = f"""
请将以下用户查询改写成5个不同版本的语义表达，每个版本都应该保持原意但用不同的方式表述。
原始查询: "{original_query}"

要求：
1. 保持查询的核心含义不变
2. 每个版本都应该是一个完整的句子
3. 版本之间要有明显差异
4. 用中文回答
5. 如果存在多个意图，选择最清晰、最重要的一个进行处理

请按以下格式输出：
1. [改写版本1]
2. [改写版本2]
3. [改写版本3]
4. [改写版本4]
5. [改写版本5]

请直接输出改写结果，不要添加额外说明。
        """.strip()
        logger.info(f'当前消息列表: {messages}')  
        logger.info(f'改写前的消息列表: {copy.deepcopy(messages)}')  
        
        # 创建临时消息列表用于改写（必须深拷贝，避免修改原始消息列表）
        rewrite_messages = copy.deepcopy(messages)
        rewrite_messages.append(Message(role=USER, content=rewrite_prompt))
        logger.info(f'改写后的消息列表: {rewrite_messages}')  
        
        try:
            # 调用LLM获取改写结果
            rewrite_stream = self._call_llm(
                messages=rewrite_messages,
                functions=[],
                extra_generate_cfg={}
            )
            
            # 收集LLM回复
            rewrite_response = ""
            for chunk in rewrite_stream:
                if chunk:
                    rewrite_response += chunk[0].content if chunk[0].content else ""
            
            # 解析改写结果
            rewritten_versions = []
            lines = rewrite_response.strip().split('\n')
            for line in lines:
                if line.strip().startswith(('1.', '2.', '3.', '4.', '5.')):
                    # 提取版本内容
                    content = line.split('.', 1)[1].strip()
                    if content:
                        rewritten_versions.append(content)
            
            # 如果解析失败，尝试另一种方式
            if not rewritten_versions:
                # 尝试按换行分割
                for line in lines:
                    if line.strip() and not line.startswith(('1.', '2.', '3.', '4.', '5.')):
                        rewritten_versions.append(line.strip())
            
            # 限制最多5个版本
            rewritten_versions = rewritten_versions[:5]
            
            logger.info(f'LLM改写后的语义版本（前5个）:')
            for i, version in enumerate(rewritten_versions, 1):
                logger.info(f'{i}. {version}')
            
            # 选择第一个版本作为最新消息
            if rewritten_versions:
                new_message = Message(role=USER, content=rewritten_versions[0])
                # 替换最后一个用户消息（通常是原始查询）
                if rewrite_messages and rewrite_messages[-1].role == USER:
                    rewrite_messages[-1] = new_message
                else:
                    rewrite_messages.append(new_message)
                
                logger.info(f'选择相似度最高的版本作为最新消息: "{rewritten_versions[0]}"')
                return rewrite_messages
            else:
                logger.warning('LLM未返回有效的改写版本，使用原始查询')
                return messages
                
        except Exception as e:
            logger.error(f'语义改写失败: {e}')
            # 出错时返回原始消息
            return messages