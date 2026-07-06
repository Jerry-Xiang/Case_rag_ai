# -*- coding: utf-8 -*-
"""
语义分析路由器 - SemanticRouter
根据用户指令的语义清晰度，智能选择处理模式：
1. 清晰明确的指令 -> 直接响应（即时调用工具）
2. 复杂表达或语义不完整 -> ReAct模式（思考优化）

包含兜底机制：当找不到对应数据时，给用户明确反馈，避免无限循环
"""

import copy
import json
from typing import Dict, Iterator, List, Literal, Optional, Union

from qwen_agent.agents.assistant import Assistant
from qwen_agent.llm import BaseChatModel
from qwen_agent.llm.schema import ASSISTANT, FUNCTION, SYSTEM, Message
from qwen_agent.log import logger
from qwen_agent.settings import MAX_LLM_CALL_PER_RUN
from qwen_agent.tools import BaseTool
from qwen_agent.utils.utils import format_as_text_message


SEMANTIC_ANALYSIS_PROMPT = """你是一个语义分析专家，负责分析用户指令的类型。

请根据以下标准对用户输入进行分类：

【Chat - 纯对话】：
- 用户只是在聊天、问候或自我介绍
- 不需要调用任何工具，可以直接回答
- 例如："你好"、"我是谁"、"你叫什么名字"、"谢谢"、"再见"、"你好吗"

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
3. 如果是模糊或复杂的指令，使用ReAct模式进行思考和优化，然后回答

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

        if analysis_result.get('type') == 'Chat':
            yield [Message(role=ASSISTANT, content=f'💬 检测到纯对话，直接回答...\n\n')]
            for response in super()._run(messages=messages, lang=lang, **kwargs):
                yield response
            return
            
        if analysis_result.get('type') == 'Direct':
            yield [Message(role=ASSISTANT, content=f'🔍 检测到清晰指令，正在直接处理...\n\n')]  
            direct_messages = copy.deepcopy(messages)
            response = []
            
            extra_generate_cfg = {'lang': lang}
            if kwargs.get('seed') is not None:
                extra_generate_cfg['seed'] = kwargs['seed']
            
            output_stream = self._call_llm(messages=direct_messages,
                                           functions=[func.function for func in self.function_map.values()],
                                           extra_generate_cfg=extra_generate_cfg)
            output: List[Message] = []
            for out in output_stream:
                if out:
                    output.extend(out)
            
            logger.info(f'Direct模式LLM返回消息数量: {len(output)}')
            
            if not output:
                logger.info('Direct模式LLM返回空结果')
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                return
            
            response.extend(output)
            direct_messages.extend(output)
            
            use_tool = False
            tool_name = None
            tool_args = None
            
            for out in output:
                use_tool, tool_name, tool_args, _ = self._detect_tool(out)
                logger.info(f'Direct模式检测工具调用: use_tool={use_tool}, tool_name={tool_name}, tool_args={tool_args}')
                if use_tool:
                    break
            
            if use_tool and tool_name:
                logger.info(f'Direct模式调用工具: {tool_name}, 参数: {tool_args}, 参数类型: {type(tool_args)}')
                
                try:
                    tool_args = self._build_tool_args(tool_name, tool_args, user_query)
                    logger.info(f'Direct模式构建后的参数: {tool_args}')
                except Exception as e:
                    logger.error(f'Direct模式参数构建失败: {e}')
                    yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                    return
                
                if tool_args:
                    try:
                        tool_result = self._call_tool(tool_name, tool_args, messages=direct_messages, **kwargs)
                        logger.info(f'Direct模式工具调用结果: {str(tool_result)[:100]}...')
                        
                        if not self._is_empty_result(str(tool_result)):
                            logger.info('Direct模式调用LLM生成最终回答')
                            
                            fn_msg = Message(
                                role=FUNCTION,
                                name=tool_name,
                                content=tool_result,
                            )
                            direct_messages.append(fn_msg)
                            
                            final_output_stream = self._call_llm(messages=direct_messages,
                                                                 functions=[],
                                                                 extra_generate_cfg=extra_generate_cfg)
                            final_output_list: List[Message] = []
                            for out in final_output_stream:
                                if out:
                                    final_output_list.extend(out)
                            if final_output_list:
                                yield response + final_output_list
                            else:
                                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                        else:
                            logger.info('Direct模式工具返回空结果')
                            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                        return
                    except Exception as e:
                        logger.error(f'Direct模式工具调用失败: {e}')
                else:
                    logger.info('Direct模式参数构建为空')
                
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                return
            else:
                logger.info('Direct模式未检测到工具调用，走检索逻辑查询文档')
                
                retrieval_tool_name = None
                for name, func in self.function_map.items():
                    if hasattr(func, 'function') and func.function.get('name') == 'retrieval':
                        retrieval_tool_name = name
                        break
                
                if retrieval_tool_name:
                    try:
                        tool_args = self._build_tool_args(retrieval_tool_name, '', user_query)
                        logger.info(f'Direct模式检索参数: {tool_args}')
                        
                        if tool_args:
                            tool_result = self._call_tool(retrieval_tool_name, tool_args, messages=direct_messages, **kwargs)
                            logger.info(f'Direct模式检索结果: {str(tool_result)[:100]}...')
                            
                            if not self._is_empty_result(str(tool_result)):
                                logger.info('Direct模式调用LLM生成最终回答')
                                
                                fn_msg = Message(
                                    role=FUNCTION,
                                    name=retrieval_tool_name,
                                    content=tool_result,
                                )
                                direct_messages.append(fn_msg)
                                
                                final_output_stream = self._call_llm(messages=direct_messages,
                                                                     functions=[],
                                                                     extra_generate_cfg=extra_generate_cfg)
                                final_output_list: List[Message] = []
                                for out in final_output_stream:
                                    if out:
                                        final_output_list.extend(out)
                                if final_output_list:
                                    yield response + final_output_list
                                else:
                                    yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                            else:
                                logger.info('Direct模式检索返回空结果')
                                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                        else:
                            logger.info('Direct模式检索参数构建为空')
                            yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                    except Exception as e:
                        logger.error(f'Direct模式检索失败: {e}')
                        yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                else:
                    logger.info('Direct模式未找到retrieval工具')
                    yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
                    
        else:
            yield [Message(role=ASSISTANT, content=f'🔍 检测到复杂语义，正在深度分析...\n\n')]
            
            complex_messages = copy.deepcopy(messages)
            response = []
            tool_call_count = 0
            max_tool_calls = 3
            has_valid_result = False
            
            logger.info(f'ReAct 模式开始，用户查询: {user_query}')
            
            while tool_call_count < max_tool_calls:
                tool_call_count += 1
                logger.info(f'ReAct 模式工具调用次数: {tool_call_count}/{max_tool_calls}')
                
                extra_generate_cfg = {'lang': lang}
                if kwargs.get('seed') is not None:
                    extra_generate_cfg['seed'] = kwargs['seed']
                
                logger.info(f'调用LLM，消息数量: {len(complex_messages)}')
                # logger.info(f'调用LLM，消息内容: {complex_messages}')
                output_stream = self._call_llm(messages=complex_messages,
                                               functions=[func.function for func in self.function_map.values()],
                                               extra_generate_cfg=extra_generate_cfg)
                output: List[Message] = []
                for output in output_stream:
                    if output:
                        yield response + output
                
                logger.info(f'LLM返回消息数量: {len(output)}')
                logger.info(f'LLM返回消息内容: {output}')
                if not output:
                    logger.info('LLM返回空结果，退出循环')
                    break
                
                response.extend(output)
                complex_messages.extend(output)
                used_any_tool = False
                tool_name = None
                tool_args = None
                
                for out in output:
                    use_tool, tool_name, tool_args, _ = self._detect_tool(out)
                    logger.info(f'检测工具调用: use_tool={use_tool}, tool_name={tool_name}')
                    
                    if use_tool:
                        used_any_tool = True
                        break
                
                if not used_any_tool:
                    logger.info('未检测到工具调用，直接结束')
                    break
                
                logger.info(f'调用工具: {tool_name}, 参数: {tool_args}')
                
                tool_args = self._build_tool_args(tool_name, tool_args, user_query)
                logger.info(f'ReAct模式构建后的参数: {tool_args}')
                
                if tool_args:
                    tool_result = self._call_tool(tool_name, tool_args, messages=complex_messages, **kwargs)
                else:
                    logger.info(f'ReAct模式工具参数构建失败，跳过工具调用')
                    continue
                logger.info(f'工具调用结果: {str(tool_result)[:100]}...')

                fn_msg = Message(
                    role=FUNCTION,
                    name=tool_name,
                    content=tool_result,
                )
                complex_messages.append(fn_msg)
                response.append(fn_msg)
                yield response
                
                if not self._is_empty_result(str(tool_result)):
                    has_valid_result = True
                    logger.info('检测到有效结果')
            
            logger.info(f'ReAct 模式结束，has_valid_result={has_valid_result}, tool_call_count={tool_call_count}')
            
            if has_valid_result:
                logger.info('调用LLM生成最终回答')
                final_output_stream = self._call_llm(messages=complex_messages,
                                                     functions=[],
                                                     extra_generate_cfg=extra_generate_cfg)
                final_output_list: List[Message] = []
                for out in final_output_stream:
                    if out:
                        final_output_list.extend(out)
                        yield response + [out]
                if final_output_list:
                    response.extend(final_output_list)
            elif tool_call_count >= max_tool_calls:
                logger.info('已达到最大工具调用次数，触发兜底机制')
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
            else:
                yield [Message(role=ASSISTANT, content=self._get_fallback_response(user_query))]
            
            yield response

    def _detect_tool(self, message) -> tuple:
        """支持两种格式的工具调用检测：函数调用格式和 ReAct 格式"""
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
                special_func_token = '\nAction:'
                special_args_token = '\nAction Input:'
                special_obs_token = '\nObservation:'
                i = text.rfind(special_func_token)
                j = text.rfind(special_args_token)
                k = text.rfind(special_obs_token)
                if 0 <= i < j:
                    if k < j:
                        text = text.rstrip() + special_obs_token
                    k = text.rfind(special_obs_token)
                    func_name = text[i + len(special_func_token):j].strip()
                    func_args = text[j + len(special_args_token):k].strip()
                    text = text[:i]
        
        if not text:
            text = ''
        
        return (func_name is not None), func_name, func_args, text

    def _build_tool_args(self, tool_name: str, tool_args, user_query: str) -> Optional[str]:
        """构建工具参数，当参数为空时从用户查询中自动填充"""
        import json
        
        if tool_args and str(tool_args).strip() and str(tool_args).strip() != '{}':
            if isinstance(tool_args, dict):
                return json.dumps(tool_args, ensure_ascii=False)
            elif isinstance(tool_args, str):
                return tool_args
            else:
                return str(tool_args)
        
        if not hasattr(self, 'function_map') or tool_name not in self.function_map:
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

    def _is_empty_result(self, text: str) -> bool:
        """判断是否为空结果或未找到数据"""
        empty_keywords = ['未找到', '无结果', '找不到', '没有相关', '无法回答', 'not found', 'no result', 'no data', 'empty']
        text_lower = text.lower()
        for keyword in empty_keywords:
            if keyword in text or keyword.lower() in text_lower:
                return True
        return len(text.strip()) < 10

    def _get_fallback_response(self, query: str) -> str:
        """生成兜底回复"""
        keywords = self._extract_keywords(query)
        if keywords:
            return f'🤔 抱歉，我无法找到关于「{keywords}」的相关信息。您可以尝试：\n\n1. 提供更具体的关键词\n2. 检查拼写是否正确\n3. 尝试其他相关问题'
        return '🤔 抱歉，我无法找到相关信息。您可以尝试提供更具体的关键词或检查拼写是否正确。'

    def _extract_keywords(self, query) -> str:
        """提取查询中的关键词"""
        import re
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