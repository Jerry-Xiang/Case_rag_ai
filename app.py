# -*- coding: utf-8 -*-
"""
Case RAG AI - 统一入口
语义分析路由器架构：清晰指令走直接响应，模糊语义走ReAct优化
"""

import os
import sys
from pathlib import Path
from qwen_agent.gui import WebUI
from qwen_agent.agents import Assistant
from qwen_agent.agents.semantic_router import SemanticRouter
from qwen_agent.tools.base import BaseTool, register_tool

@register_tool('my_image_gen')
class MyImageGen(BaseTool):
    """自定义图像生成工具"""
    description = 'AI 绘画（图像生成）服务，输入文本描述，返回基于文本信息绘制的图像 URL。'
    parameters = [{
        'name': 'prompt',
        'type': 'string',
        'description': '期望的图像内容的详细描述',
        'required': True
    }]

    def call(self, params: str, **kwargs) -> str:
        import json5
        import urllib.parse
        prompt = json5.loads(params)['prompt']
        prompt = urllib.parse.quote(prompt)
        return json5.dumps(
            {'image_url': f'https://image.pollinations.ai/prompt/{prompt}'},
            ensure_ascii=False)


def init_agent_service():
    """初始化助手服务"""
    print("[DEBUG] init_agent_service: 开始初始化...")
    
    from harness.settings import settings
    print("[DEBUG] init_agent_service: 加载 settings 完成")

    llm_cfg = settings.llm
    if not llm_cfg.get('api_key'):
        llm_cfg['api_key'] = os.getenv('DASHSCOPE_API_KEY', '')
    print("[DEBUG] init_agent_service: LLM 配置完成")
    
    rag_cfg = {
        "rag_backend": "elasticsearch",
        "es": settings.elasticsearch,
        "parser_page_size": settings.retrieval.get('parser_page_size', 500)
    }
    print("[DEBUG] init_agent_service: RAG 配置完成")

    # system_instruction = '''你是一个乐于助人的AI助手。
    #                         在收到用户的请求后，你应该：
    #                         - 首先绘制一幅图像，得到图像的url，
    #                         - 然后运行代码`request.get`以下载该图像的url，
    #                         - 最后从给定的文档中选择一个图像操作进行图像处理。
    #                         用 `plt.show()` 展示图像。
    #                         你总是用中文回复用户。'''

    # # tavily_search 工具从互联网上搜索新闻
    # system_instruction = '''你是一个乐于助人的AI助手。
    #                         在收到用户的请求后，你应该：
    #                         - 请根据用户的问题，优先利用检索工具从本地知识库中查找最相关的信息。
    #                         - 如果本地知识库没有相关信息，再使用 tavily_search 工具从互联网上搜索，显示搜索结果前 5 条。
    #                         - 并结合联网搜索信息给出专业、准确的回答。   
    #                         - 如果需要计算或数据处理，使用 code_interpreter 工具执行代码。                          
    #                         - 如果需要绘制一幅图像，得到图像的url，用 `plt.show()` 展示图像。                                                       
    #                         提示词和回答总是用中文给用户，找不到答案时，回复“我无法回答这个问题”。'''                            

    # tools = ['my_image_gen', 'code_interpreter']
    tools_cfg = ['my_image_gen', 'code_interpreter'
    , {
        "mcpServers": {
            # "baidu-search": {
            #     "command": "npx",
            #     "args": [
            #         "baidu-search-mcp" #测试不能查询今天的新闻
            #         # "max-result=5",
            #         # "fetch-content-count=2",
            #         # "max-content-length=2000"
            #     ]
            # }           
             
            "tavily-mcp": settings.mcp_tools['tavily-mcp']
            
            # "news_search_server": {
            #     "command": "npx",
            #     "args": ["-y", "newsnow-mcp-server"],
            #     "env": {
            #         "BASE_URL": "https://newsnow.busiyi.world"
            #     }
            # }        
                               
        }
    }
    ]    

    # 获取文件夹下所有文件
    file_dir = os.path.join(os.path.dirname(__file__), 'docs')
    files = []
    if os.path.exists(file_dir):
        # 遍历目录下的所有文件
        for file in os.listdir(file_dir):
            file_path = os.path.join(file_dir, file)
            if os.path.isfile(file_path):  # 确保是文件而不是目录
                files.append(file_path)
    # print('files=', files)

    print("[DEBUG] init_agent_service: 开始创建 SemanticRouter...")
    bot = SemanticRouter(
        llm=llm_cfg,
        function_list=tools_cfg,
        files=files,
        rag_cfg=rag_cfg # 开启 RAG 功能 开启走ES检索，否则走默认检索工具
    )
    print("[DEBUG] init_agent_service: SemanticRouter 创建完成")
    return bot


def run_gui():
    """运行 GUI 模式"""
    from harness.settings import settings
    try:
        print("正在启动 Case RAG AI...")
        bot = init_agent_service()

        webui_cfg = settings.webui
        chatbot_config = {
            'prompt.suggestions': [            
                '介绍下雇主责任险',
                '画一只在写代码的熊猫',
                '帮我画一个宇宙飞船' #，然后把它变成黑白的
            ]
        }

        WebUI(bot, chatbot_config=chatbot_config).run(server_port=webui_cfg['server_port'])
    except Exception as e:
        print(f"启动 Web 界面失败: {str(e)}")
        print("请检查网络连接和 API Key 配置")    


def run_tui():
    """运行 TUI 模式"""
    print("Case RAG AI 智能问答系统 (TUI 模式)")
    print("=" * 50)
    print("输入 'quit' 或 'exit' 退出")
    print()
    
    try:
        bot = init_agent_service()
        messages = []

        while True:
            try:
                query = input('用户问题: ').strip()
                
                if query.lower() in ['quit', 'exit', 'q']:
                    print("感谢使用，再见！")
                    break
                    
                if not query:
                    print('请输入有效的问题！')
                    continue
                    
                messages.append({'role': 'user', 'content': query})

                print("正在处理您的请求...")
                
                response = []
                current_index = 0
                
                for response_chunk in bot.run(messages=messages):
                    if response_chunk:
                        for msg in response_chunk:
                            if msg['role'] == 'assistant':
                                new_content = msg.get('content', '')
                                print(new_content[current_index:], end='', flush=True)
                                current_index = len(new_content)
                    
                    response = response_chunk
                
                print()
                messages.extend(response)

            except KeyboardInterrupt:
                print("\n感谢使用，再见！")
                break
            except Exception as e:
                print(f"\n处理请求时出错: {str(e)}")
                print("请重试或输入新的问题")
                messages.pop()
    except Exception as e:
        print(f"初始化失败: {e}")


def main():
    """主入口"""
    import argparse
    parser = argparse.ArgumentParser(description='Case RAG AI')
    parser.add_argument('--mode', choices=['gui', 'tui'], default='gui')
    args = parser.parse_args()

    if args.mode == 'tui':
        run_tui()
    else:
        run_gui()

if __name__ == '__main__':
    main()
