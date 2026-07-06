# Case RAG AI 系统架构文档

## 一、项目概述

Case RAG AI 是一个基于 **Qwen-Agent** 框架构建的智能问答系统，结合了文档检索（RAG）、代码解释器、图像生成和 MCP 工具（如 Tavily 搜索）等能力，提供 GUI 和 TUI 两种交互模式。

**核心特点**：
- **语义分析路由器**：根据用户指令语义清晰度智能选择处理模式
- **ReAct 模式**：支持复杂语义的多步推理和工具调用
- **三轮兜底机制**：防止无限循环，确保在无法获取数据时给出明确反馈
- **Elasticsearch 后端检索**：大规模文档场景下性能优于内存检索
- **优雅降级机制**：ES 连接失败时自动降级到文档解析检索
- **配置集中化管理**：敏感信息通过环境变量注入
- **工具扩展机制完善**：支持自定义工具和 MCP 协议工具
- **流式响应输出**：用户体验流畅

## 二、系统架构图

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              用户层 (User Layer)                                  │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────────┐   │
│  │      TUI 交互模式        │    │           GUI 交互模式                    │   │
│  │  命令行终端输入输出        │    │   Web 浏览器 (Gradio)                     │   │
│  │  - 用户输入问题            │    │   - 流式响应显示                         │   │
│  │  - 流式响应输出            │    │   - 文件上传支持                         │   │
│  │  - quit/exit 退出         │    │   - 示例问题快速选择                      │   │
│  └────────────────┬─────────┘    └───────────────────┬────────────────────┘   │
│                   │                                   │                         │
└───────────────────┼───────────────────────────────────┼────────────────────────┘
                    ↓                                   ↓
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         应用层 (Application Layer)                               │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │                        SemanticRouter (语义分析路由器)                      │  │
│  │                                                                           │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │  │
│  │  │   Chat      │    │   Direct    │    │   Complex   │                    │  │
│  │  │ 纯对话模式   │    │ 直接响应模式 │    │ ReAct模式   │                    │  │
│  │  │ 无需调用工具 │    │ 即时调用工具 │    │ 多步推理     │                    │  │
│  │  │ 直接回答     │    │ 获取数据     │    │ 最多3次工具调用│                  │  │
│  │  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                    │  │
│  │         │                  │                  │                            │  │
│  │         ↓                  ↓                  ↓                            │  │
│  │  ┌─────────────────────────────────────────────────────────────────────┐  │  │
│  │  │                       FnCallAgent (函数调用智能体)                   │  │  │
│  │  │                                                                     │  │  │
│  │  │  ┌───────────────────────────────────────────────────────────────┐  │  │  │
│  │  │  │                        LLM (大语言模型)                        │  │  │  │
│  │  │  │  - qwen3-max / qwen-flash (DashScope)                        │  │  │  │
│  │  │  │  - 函数调用判断                                                │  │  │  │
│  │  │  │  - 响应生成                                                    │  │  │  │
│  │  │  └─────────────────────────┬─────────────────────────────────────┘  │  │  │
│  │  │                            │                                         │  │  │
│  │  │  ┌─────────────────────────┼─────────────────────────────────────┐  │  │  │
│  │  │  │                           工具层 (Tools Layer)                 │  │  │  │
│  │  │  │                                                                │  │  │  │
│  │  │  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐  │  │  │  │
│  │  │  │  │  retrieval │ │doc_parser │ │code_interp │ │my_image_gen│  │  │  │  │
│  │  │  │  │ 文档检索    │ │文档解析    │ │代码解释器  │ │图像生成    │  │  │  │  │
│  │  │  │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘  │  │  │  │
│  │  │  │        │              │              │              │          │  │  │  │
│  │  │  │  ┌─────┴──────┐       │              │              │          │  │  │  │
│  │  │  │  │ ES检索/内存 │       │              │              │          │  │  │  │
│  │  │  │  │ 检索后端    │       │              │              │          │  │  │  │
│  │  │  │  └─────┬──────┘       │              │              │          │  │  │  │
│  │  │  │        │              │              │              │          │  │  │  │
│  │  │  │  ┌─────┴──────┐       │              │              │          │  │  │  │
│  │  │  │  │   MCP工具   │       │              │              │          │  │  │  │
│  │  │  │  │ tavily-mcp │       │              │              │          │  │  │  │
│  │  │  │  └────────────┘       │              │              │          │  │  │  │
│  │  │  │                        │              │              │          │  │  │  │
│  │  │  └────────────────────────┴──────────────┴──────────────┴──────────┘  │  │  │
│  │  │                                                                     │  │  │
│  │  └─────────────────────────────────────────────────────────────────────┘  │  │
│  │                                                                           │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
                    ↓                                   ↓
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        数据层 (Data Layer)                                       │
│                                                                                  │
│  ┌──────────────────────────┐    ┌──────────────────────────────────────────┐   │
│  │       文档库 (Docs)       │    │           Elasticsearch                  │   │
│  │  - PDF/TXT 文档          │    │   - qwen_agent_rag_index 索引            │   │
│  │  - 保险条款文档           │    │   - IK 中文分词器                        │   │
│  │  - 产品说明文档           │    │   - 文本分块存储 (chunk_size=500)        │   │
│  └──────────────────────────┘    └──────────────────────────────────────────┘   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                         工作空间 (Workspace)                              │   │
│  │  - code_interpreter/ 代码执行临时文件                                     │   │
│  │  - doc_parser/ 文档解析缓存                                               │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

## 三、项目结构

```
Case_rag_ai/
├── app.py                          # 主入口（项目根目录）
├── .env                            # 环境变量文件
├── .env.example                    # 环境变量示例文件
├── docs/                           # 文档目录（存放待检索的文档）
│   ├── 1-平安商业综合责任保险（亚马逊）.txt
│   ├── 2-雇主责任险.txt
│   ├── 3-平安企业团体综合意外险.txt
│   └── ...（PDF/TXT文档）
├── harness/
│   ├── __init__.py
│   ├── settings.py                 # 配置管理模块（单例模式）
│   └── config.yaml                 # 配置文件（YAML格式）
├── qwen_agent/                     # Qwen-Agent 框架
│   ├── __init__.py
│   ├── agent.py                    # Agent 基类
│   ├── log.py                      # 日志模块
│   ├── settings.py                 # 框架设置
│   ├── multi_agent_hub.py          # 多智能体中心
│   ├── agents/                     # 智能体模块
│   │   ├── __init__.py
│   │   ├── agent.py                # Agent 基类
│   │   ├── assistant.py            # Assistant 智能体（核心）
│   │   ├── fncall_agent.py         # 函数调用智能体
│   │   ├── semantic_router.py      # 语义分析路由器（新增）
│   │   ├── react_chat.py           # ReAct 聊天智能体
│   │   ├── react_optimizer.py      # ReAct 优化智能体
│   │   ├── direct_responder.py     # 直接响应智能体
│   │   ├── virtual_memory_agent.py # 虚拟内存智能体
│   │   ├── memo_assistant.py       # 记忆助手
│   │   ├── article_agent.py        # 文章生成智能体
│   │   ├── group_chat.py           # 群聊智能体
│   │   ├── router.py               # 路由器智能体
│   │   ├── tir_agent.py            # TIR 智能体
│   │   ├── doc_qa/                 # 文档问答智能体
│   │   │   ├── basic_doc_qa.py
│   │   │   ├── parallel_doc_qa.py
│   │   │   └── ...
│   │   ├── keygen_strategies/      # 关键词生成策略
│   │   └── writing/                # 写作工具
│   ├── llm/                        # LLM 模块
│   │   ├── __init__.py             # LLM 工厂函数（get_chat_model）
│   │   ├── base.py                 # LLM 基类
│   │   ├── schema.py               # 消息格式定义
│   │   ├── qwen_dashscope.py       # DashScope 模型适配器
│   │   ├── oai.py                  # OpenAI 兼容适配器
│   │   ├── azure.py                # Azure 适配器
│   │   ├── transformers_llm.py     # Transformers 模型适配器
│   │   ├── openvino.py             # OpenVINO 加速
│   │   ├── function_calling.py     # 函数调用处理
│   │   └── fncall_prompts/         # 函数调用提示词
│   ├── gui/                        # GUI 模块
│   │   ├── __init__.py
│   │   ├── web_ui.py               # WebUI 界面（基于 Gradio）
│   │   ├── gradio_dep.py           # Gradio 依赖
│   │   ├── gradio_utils.py         # Gradio 工具函数
│   │   ├── utils.py                # 通用工具
│   │   └── assets/                 # UI 静态资源
│   ├── memory/                     # 内存管理模块
│   │   ├── __init__.py
│   │   └── memory.py               # 内存管理与文档检索代理
│   ├── tools/                      # 工具模块
│   │   ├── __init__.py
│   │   ├── base.py                 # 工具基类（BaseTool）
│   │   ├── code_interpreter.py     # 代码解释器工具
│   │   ├── doc_parser.py           # 文档解析工具
│   │   ├── retrieval.py            # 默认检索工具
│   │   ├── es_retrieval.py         # ES 检索工具（框架内置）
│   │   ├── web_search.py           # 网页搜索工具
│   │   ├── web_extractor.py        # 网页内容提取工具
│   │   ├── image_gen.py            # 图像生成工具
│   │   ├── storage.py              # 存储工具
│   │   ├── python_executor.py      # Python 执行器
│   │   ├── mcp_manager.py          # MCP 工具管理
│   │   ├── amap_weather.py         # 天气工具
│   │   └── search_tools/           # 搜索工具
│   │       ├── base_search.py
│   │       ├── keyword_search.py
│   │       ├── vector_search.py
│   │       ├── front_page_search.py
│   │       └── hybrid_search.py
│   ├── searcher/                   # 搜索器模块
│   │   ├── __init__.py
│   │   └── elasticsearch_searcher.py # ES 搜索器
│   └── utils/                      # 工具函数模块
│       ├── __init__.py
│       ├── utils.py                # 通用工具函数
│       ├── str_processing.py       # 字符串处理
│       ├── output_beautify.py      # 输出美化
│       ├── parallel_executor.py    # 并行执行器
│       └── tokenization_qwen.py    # Qwen 分词
├── static/                         # 静态资源
│   ├── logo.png
│   └── styles.css
├── tests/                          # 测试目录
│   └── __init__.py
└── workspace/                      # 工作空间（临时文件）
    └── tools/                      # 工具运行时文件
```

## 四、核心架构设计

### 4.1 语义分析路由器（SemanticRouter）

**设计目标**：根据用户指令的语义清晰度，智能选择处理模式，实现高效响应。

**分类策略**：

```
用户提问 → _analyze_semantic() → 分类判断
                                     ↓
    ┌───────────────────────────────┼───────────────────────────────┐
    ↓                               ↓                               ↓
   Chat                         Direct                         Complex
    ↓                               ↓                               ↓
 直接回答                    即时工具调用                    ReAct模式深度分析
(无需工具)                   获取数据                       最多3次工具调用
```

| 分类类型 | 特征 | 处理模式 | 示例 |
|---------|------|---------|------|
| **Chat** | 纯对话、问候、自我介绍 | 直接回答，无需调用工具 | "你好"、"我是谁"、"你叫什么名字" |
| **Direct** | 意图明确，可直接调用工具 | 即时调用工具 → FUNCTION消息 → LLM生成自然语言回答 | "介绍下雇主责任险"、"帮我计算1+1" |
| **Complex** | 意图模糊、存在歧义、需要多步推理 | ReAct 模式深度分析 | "帮我看看那个东西"、"分析一下这个问题" |

**执行流程**：

```
用户提问 → 语义分析 → 分类判断
                        ↓
    ┌──────────────────┼──────────────────┐
    ↓                  ↓                  ↓
   Chat             Direct            Complex
    ↓                  ↓                  ↓
 直接回答        工具调用+LLM总结    ReAct模式
(无需工具)       生成自然语言回答     深度分析
                                     ↓
                              工具调用(最多3次)
                                     ↓
                              检测有效结果?
                                 /    \
                                是     否
                                ↓      ↓
                           生成最终   触发兜底
                            回答      机制
```

**关键代码位置**：`qwen_agent/agents/semantic_router.py`

### 4.2 Direct 模式处理流程

**设计目标**：对于意图明确的指令，即时调用工具获取数据，并通过 LLM 生成自然语言回答。

**工作流程**：

```
用户提问 → 语义分析 → Direct类型
                        ↓
              调用LLM获取响应 → 检测工具调用
                        ↓
              _build_tool_args() 自动构建参数
                        ↓
              调用工具（MCP工具30秒超时保护）
                        ↓
              构建FUNCTION消息加入messages
                        ↓
              调用LLM生成最终自然语言回答
                        ↓
              流式输出响应
```

**关键机制**：

| 机制 | 说明 | 代码位置 |
|------|------|---------|
| `_build_tool_args()` | 当工具参数为空时，从用户查询自动填充必填参数 | `semantic_router.py` |
| FUNCTION 消息 | 工具调用结果封装为 FUNCTION 角色消息，供 LLM 总结 | `semantic_router.py` |
| MCP 超时保护 | MCP 工具调用设置 30 秒超时，防止进程卡住 | `mcp_manager.py` |
| LLM 二次总结 | 工具结果通过 LLM 生成自然语言回答，提升体验 | `semantic_router.py` |

### 4.3 ReAct 模式三轮兜底机制

**设计目标**：防止工具调用无限循环，确保在无法获取数据时给出明确反馈。

**工作流程**：

```
第1轮：调用 LLM → 检测工具调用 → 调用工具 → 获取结果
                                              ↓
第2轮：调用 LLM → 检测工具调用 → 调用工具 → 获取结果  
                                              ↓
第3轮：调用 LLM → 检测工具调用 → 调用工具 → 获取结果
                                              ↓
                                    达到3次限制？
                                     /      \
                                    是       否
                                    ↓        ↓
                              触发兜底    继续循环
                              机制        (已限制)
                                    ↓
                              检测有效结果?
                                 /    \
                                是     否
                                ↓      ↓
                           生成最终   触发兜底
                            回答      机制
```

**关键配置**：
- `max_tool_calls = 3`：最大工具调用次数
- `_detect_tool()`：支持函数调用格式和 ReAct 格式的工具调用检测
- `_get_fallback_response()`：生成兜底回复

**工具调用检测格式**：

| 格式类型 | 检测方式 | 示例 |
|---------|---------|------|
| 函数调用格式 | `message.function_call` | `{"name": "retrieval", "arguments": "..."}` |
| ReAct 格式 | `\nAction:` + `\nAction Input:` | `Action: retrieval\nAction Input: {...}` |

**关键代码位置**：`qwen_agent/agents/semantic_router.py:_run()`

### 4.4 检索后端架构

**设计目标**：支持 Elasticsearch 和默认内存两种检索后端，实现优雅降级。

**架构图**：

```
用户提问 → Memory.run() → 判断 rag_backend
                              ↓
                    ┌─────────┴─────────┐
                    ↓                   ↓
              elasticsearch          default
                    ↓                   ↓
           ESRetrievalTool        默认检索工具
                    ↓                   ↓
           尝试连接ES              内存检索
                    ↓                   ↓
           ┌────────┴────────┐
           ↓                 ↓
         成功              失败
           ↓                 ↓
       ES检索          降级到默认
                       内存检索
```

**关键代码位置**：`qwen_agent/memory/memory.py`、`qwen_agent/tools/es_retrieval.py`

### 4.5 工具扩展机制

**设计目标**：支持自定义工具和 MCP 协议工具的灵活扩展。

**工具注册方式**：

```python
# 方式1：使用装饰器注册自定义工具
@register_tool('my_tool')
class MyTool(BaseTool):
    description = '工具描述'
    parameters = [{
        'name': 'param1',
        'type': 'string',
        'description': '参数描述',
        'required': True
    }]
    
    def call(self, params: str, **kwargs) -> str:
        # 工具实现
        pass

# 方式2：通过配置文件注册 MCP 工具（harness/config.yaml）
mcp_tools:
  tavily-mcp:
    command: "npx"
    args: ["-y", "tavily-mcp@0.1.4"]
    env:
      TAVILY_API_KEY: "${TAVILY_API_KEY}"
```

**工具列表**：

| 工具名 | 功能 | 类型 |
|--------|------|------|
| `retrieval` | 文档检索 | 框架内置 |
| `doc_parser` | 文档解析 | 框架内置 |
| `code_interpreter` | Python 代码执行 | 框架内置 |
| `web_search` | 互联网搜索 | 框架内置 |
| `web_extractor` | 网页内容提取 | 框架内置 |
| `image_gen` | AI 图像生成 | 框架内置 |
| `storage` | 数据存储 | 框架内置 |
| `amap_weather` | 天气查询 | 框架内置 |
| `my_image_gen` | 自定义图像生成 | 自定义 |
| `tavily-mcp` | 互联网搜索 | MCP 协议 |

## 五、执行调用流程

### 5.1 启动流程

```
用户启动 → app.py main() → 解析命令行参数 --mode
                                         ↓
                              init_agent_service()
                                         ↓
                              Settings() 加载配置（单例模式）
                                         ↓
                              创建 rag_cfg 配置对象
                                         ↓
                              创建 SemanticRouter 智能体
                                         ↓
                              启动 WebUI 或 TUI 交互循环
```

### 5.2 详细调用链

#### 阶段一：配置加载

```
app.py:init_agent_service()
    ↓
harness.settings.settings          # 导入全局配置实例（单例模式）
    ↓
Settings.__new__()                 # 确保全局唯一实例
    ↓
Settings._load_config()            # 读取 config.yaml
    ↓
yaml.safe_load(f)                  # 解析 YAML 文件
    ↓
Settings._resolve_env_vars()       # 递归解析环境变量 ${ENV_VAR}
    ↓
返回配置对象（含 llm、elasticsearch、mcp_tools 等配置）
```

**配置文件结构**（`harness/config.yaml`）：

| 配置段 | 字段 | 说明 | 默认值 |
|--------|------|------|--------|
| `llm` | `model` | LLM 模型名称 | `qwen-flash` |
| `llm` | `model_type` | 模型类型 | `qwen_dashscope` |
| `llm` | `model_server` | 模型服务 | `dashscope` |
| `llm` | `api_key` | API Key（环境变量） | `${DASHSCOPE_API_KEY}` |
| `llm` | `generate_cfg.top_p` | 生成参数 | `0.9` |
| `retrieval` | `max_ref_token` | 最大引用 Token | `20000` |
| `retrieval` | `parser_page_size` | 解析页面大小 | `500` |
| `retrieval` | `rag_searchers` | 检索策略 | `['keyword_search', 'front_page_search']` |
| `elasticsearch` | `host` | ES 主机 | `https://localhost` |
| `elasticsearch` | `port` | ES 端口 | `9200` |
| `elasticsearch` | `user` | ES 用户名 | `elastic` |
| `elasticsearch` | `password` | ES 密码（环境变量） | `${ES_PASSWORD}` |
| `elasticsearch` | `index_name` | 索引名称 | `qwen_agent_rag_index` |
| `elasticsearch` | `chunk_size` | 文本分块大小 | `500` |
| `webui` | `server_port` | Web 端口 | `7860` |
| `mcp_tools` | `tavily-mcp` | Tavily 搜索 MCP 配置 | 见下文 |

#### 阶段二：智能体初始化

```
SemanticRouter(llm=llm_cfg, function_list=tools_cfg, files=files, rag_cfg=rag_cfg)
    ↓
SemanticRouter.__init__() → Assistant.__init__() → FnCallAgent.__init__(rag_cfg=rag_cfg)
    ↓
FnCallAgent → 创建 Memory 实例（传入 rag_cfg）
    ↓
Memory.__init__(rag_cfg=rag_cfg)
    ↓
判断 rag_backend:
    ├── "elasticsearch" → 尝试加载 ESRetrievalTool
    │                       ├── 成功 → 注册 ES 检索工具
    │                       └── 失败 → 优雅降级，注册默认内存检索工具
    └── "default" → 注册默认内存检索工具
    ↓
注册其他工具（code_interpreter、doc_parser 等）
    ↓
父类 Agent.__init__() 完成初始化
```

#### 阶段三：用户交互与响应生成

```
用户提问 → bot.run(messages)
    ↓
SemanticRouter._run(messages)
    ↓
_analyze_semantic(user_query)     # 语义分析分类
    ↓
根据分类选择处理模式:
    ├── Chat → 直接回答，不调用工具
    ├── Direct → 调用 FnCallAgent，即时工具调用
    └── Complex → ReAct 模式，最多3次工具调用
        ↓
        第1轮: LLM → 工具调用 → 获取结果
        ↓
        第2轮: LLM → 工具调用 → 获取结果
        ↓
        第3轮: LLM → 工具调用 → 获取结果
        ↓
        达到3次或无有效结果 → 触发兜底机制
        ↓
        有有效结果 → 生成最终回答
        ↓
流式输出响应
```

## 六、关键设计特点

### 6.1 语义分析路由器
- 根据用户指令的语义清晰度智能选择处理模式
- 支持 Chat、Direct、Complex 三种分类
- 纯对话直接回答，避免不必要的工具调用

### 6.2 ReAct 模式三轮兜底
- 限制工具调用次数为3次，防止无限循环
- 支持函数调用格式和 ReAct 格式的工具调用检测
- 达到3次限制或无有效结果时触发兜底机制
- 提供明确的兜底回复，指导用户调整问题

### 6.3 优雅降级机制
- Memory 在加载 Elasticsearch 失败时自动降级到默认内存检索
- 不会因 ES 服务不可用导致整个系统启动失败
- 提供清晰的日志输出，便于问题定位

### 6.4 配置集中化
- 所有配置统一存储在 `harness/config.yaml`
- 支持环境变量注入，敏感信息不硬编码
- 单例模式确保配置全局一致

### 6.5 工具扩展机制
- 通过 `@register_tool` 装饰器注册自定义工具
- 支持 MCP 协议工具，通过配置文件动态加载
- 工具描述决定 LLM 是否调用该工具

### 6.6 文档检索优化
- 使用 Elasticsearch 替代内存检索，支持大规模文档
- 自动检测文件是否已索引，避免重复处理
- 支持 PDF/TXT 文件格式

### 6.7 流式响应
- TUI 和 GUI 均支持流式输出
- 用户体验流畅，实时看到回答生成过程

## 七、交互模式

### 7.1 GUI 模式（默认）

```
app.py:run_gui()
    ↓
WebUI(bot, chatbot_config=chatbot_config).run()
    ↓
启动 Gradio Web 服务器（端口 7860）
    ↓
用户在浏览器中交互：提问 → 流式响应 → 查看检索文档
```

**GUI 配置**：
- 默认端口：`7860`
- 示例问题：配置在 `chatbot_config['prompt.suggestions']`

**界面特点**：
- 支持文件上传
- 流式响应显示
- 示例问题快速选择
- 检索文档高亮展示

### 7.2 TUI 模式

```
app.py:run_tui()
    ↓
循环：用户输入 → 构建消息 → bot.run(messages)
    ↓
流式输出响应 → 更新消息历史
    ↓
退出条件：输入 'quit'、'exit' 或 'q'
```

## 八、配置说明

### 8.1 配置文件结构

```yaml
llm:
  model: qwen-flash
  model_type: qwen_dashscope
  model_server: dashscope
  api_key: ${DASHSCOPE_API_KEY}
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  generate_cfg:
    temperature: 0.2
    top_p: 0.9
    top_k: 50

retrieval:
  max_ref_token: 20000
  parser_page_size: 500
  rag_searchers:
    - "keyword_search"
    - "front_page_search"

elasticsearch:
  host: https://localhost
  port: 9200
  user: elastic
  password: ${ES_PASSWORD}
  index_name: qwen_agent_rag_index
  chunk_size: 500

webui:
  title: "Case RAG AI 智能问答"
  description: "基于 RAG 的智能问答系统"
  server_name: "0.0.0.0"
  server_port: 7860

mcp_tools:
  tavily-mcp:
    command: "npx"
    args: ["-y", "tavily-mcp@0.1.4"]
    env:
      TAVILY_API_KEY: "${TAVILY_API_KEY}"
    disabled: false
    autoApprove: []
```

### 8.2 配置优先级规则

| 优先级 | 来源 | 示例 |
|--------|------|------|
| 1 | 命令行参数 | `--mode`, `--docs-path` |
| 2 | 代码传入的 cfg | `SemanticRouter(llm=llm_cfg, rag_cfg=rag_cfg)` |
| 3 | `harness/config.yaml` | `elasticsearch.password` |
| 4 | 环境变量 | `${ES_PASSWORD}`, `${DASHSCOPE_API_KEY}`, `${TAVILY_API_KEY}` |
| 5 | 代码默认值 | `'https://localhost'`, `9200`, `500` |

## 九、环境变量清单

| 变量名 | 用途 | 示例值 |
|--------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key | `sk-xxxxxxxxxxxx` |
| `ES_PASSWORD` | Elasticsearch 密码 | `your_es_password` |
| `TAVILY_API_KEY` | Tavily 搜索 API Key | `tvly-xxxxxxxxxxxx` |

**设置方式**：

```bash
# Linux/Mac
export DASHSCOPE_API_KEY=sk-xxxxxxxxxxxx
export ES_PASSWORD=your_es_password
export TAVILY_API_KEY=tvly-xxxxxxxxxxxx

# Windows PowerShell
$env:DASHSCOPE_API_KEY="sk-xxxxxxxxxxxx"
$env:ES_PASSWORD="your_es_password"
$env:TAVILY_API_KEY="tvly-xxxxxxxxxxxx"
```

## 十、运行命令

```bash
# GUI 模式（默认）
python app.py

# TUI 模式
python app.py --mode tui
```

## 十一、常见错误及解决方案

### 11.1 ValueError: Invalid model cfg

**原因**：`model_type` 配置无效或无法自动推导

**解决方案**：确保 `model_type` 为有效值之一（`qwen_dashscope`、`oai`、`azure`、`transformers` 等）

### 11.2 Elasticsearch 连接失败

**原因**：ES 服务未启动或配置错误

**解决方案**：
1. 确保 Elasticsearch 服务运行
2. 检查 `elasticsearch.host` 和 `elasticsearch.port` 配置
3. 设置 `ES_PASSWORD` 环境变量
4. 系统会自动降级到默认内存检索

### 11.3 API Key 未设置

**原因**：`DASHSCOPE_API_KEY` 环境变量未配置

**解决方案**：设置环境变量或在配置文件中直接指定

### 11.4 TypeError: expected string or bytes-like object

**原因**：`last_message.content` 可能是列表类型

**解决方案**：`semantic_router.py` 已添加类型检查，自动处理列表类型

### 11.5 ReAct 模式无限循环

**原因**：工具调用次数未限制或检测逻辑有问题

**解决方案**：`semantic_router.py` 已添加三轮兜底机制

### 11.6 MCP 工具调用超时

**原因**：MCP 工具（如 tavily-mcp）调用无超时限制，进程卡住会导致系统阻塞

**解决方案**：`mcp_manager.py` 已为 MCP 工具调用添加 30 秒超时保护，超时后返回明确的错误提示

### 11.7 工具参数为空

**原因**：LLM 返回的工具调用参数为空字符串

**解决方案**：`semantic_router.py` 的 `_build_tool_args()` 方法会自动从用户查询中填充工具必填参数

## 十二、扩展建议

1. **添加更多工具**：通过 `@register_tool` 装饰器扩展功能
2. **支持更多文件格式**：在文档解析工具中添加 DOCX/XLSX/PPTX 等解析
3. **优化检索算法**：使用混合检索（关键词 + 向量）
4. **添加日志系统**：记录用户提问和系统响应
5. **支持多模型切换**：通过配置动态选择不同 LLM
6. **添加文件更新检测**：基于文件修改时间或哈希值检测更新
7. **添加更多 MCP 工具**：在 `config.yaml` 的 `mcp_tools` 段中配置

---

*文档生成时间：2026-07-06*
