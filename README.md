# Case RAG AI

基于 Qwen-Agent 框架构建的智能问答系统，结合文档检索（RAG）、代码解释器、图像生成和 MCP 工具等能力，提供 GUI 和 TUI 两种交互模式。

## ✨ 特性

- **语义分析路由器**：根据用户指令语义清晰度智能选择处理模式（Chat/Direct/Complex）
- **Direct 模式**：意图明确时即时调用工具，自动构建参数，LLM 生成自然语言回答
- **ReAct 模式**：支持复杂语义的多步推理和工具调用
- **三轮兜底机制**：防止无限循环，确保在无法获取数据时给出明确反馈
- **Elasticsearch 后端检索**：大规模文档场景下性能优于内存检索
- **优雅降级机制**：ES 连接失败时自动降级到文档解析检索
- **MCP 工具超时保护**：MCP 工具调用设置 30 秒超时，防止进程卡住
- **配置集中化管理**：敏感信息通过环境变量注入
- **工具扩展机制完善**：支持自定义工具和 MCP 协议工具
- **流式响应输出**：用户体验流畅

## 📁 项目结构

```
Case_rag_ai/
├── app.py                          # 主入口
├── .env                            # 环境变量文件
├── .env.example                    # 环境变量示例文件
├── docs/                           # 文档目录
│   ├── architecture.md             # 系统架构文档
│   └── ...（待检索的文档）
├── harness/
│   ├── settings.py                 # 配置管理模块
│   └── config.yaml                 # 配置文件
├── qwen_agent/                     # Qwen-Agent 框架
│   ├── agents/                     # 智能体模块
│   │   └── semantic_router.py      # 语义分析路由器
│   ├── llm/                        # LLM 模块
│   ├── gui/                        # GUI 模块
│   ├── memory/                     # 内存管理模块
│   ├── tools/                      # 工具模块
│   └── searcher/                   # 搜索器模块
├── static/                         # 静态资源
└── workspace/                      # 工作空间
```

## 🚀 快速开始

### 环境要求

- Python 3.8+
- 阿里云 DashScope API Key（可选）
- Elasticsearch 7.x+（可选）
- Tavily API Key（可选）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

复制 `.env.example` 为 `.env`，并填写相关配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxx
ES_PASSWORD=your_es_password
TAVILY_API_KEY=tvly-xxxxxxxxxxxx
```

### 运行方式

#### GUI 模式（默认）

```bash
python app.py
```

访问 http://localhost:7860 打开 Web 界面

#### TUI 模式

```bash
python app.py --mode tui
```

## 📖 使用说明

### 语义分析路由器

系统会根据用户指令的语义清晰度自动选择处理模式：

| 模式 | 适用场景 | 示例 |
|------|---------|------|
| **Chat** | 纯对话、问候、自我介绍 | "你好"、"我是谁"、"你叫什么名字" |
| **Direct** | 意图明确，即时调用工具 → LLM生成自然语言回答 | "介绍下雇主责任险"、"帮我计算1+1" |
| **Complex** | 意图模糊、需要多步推理 | "帮我看看那个东西"、"分析一下这个问题" |

### Direct 模式处理流程

对于意图明确的指令，系统会即时调用工具获取数据，并通过 LLM 生成自然语言回答：

1. **调用 LLM**：分析用户指令，确定需要调用的工具
2. **自动构建参数**：`_build_tool_args()` 方法从用户查询中自动填充工具必填参数
3. **调用工具**：执行工具调用（MCP 工具设置 30 秒超时保护）
4. **FUNCTION 消息**：将工具结果封装为 FUNCTION 角色消息
5. **LLM 生成回答**：调用 LLM 将工具结果转换为自然语言回答

### Complex 模式处理流程

对于复杂语义，系统会使用 ReAct 模式进行深度分析，最多调用工具 3 次：

1. **第1轮**：分析语义，调用工具获取数据
2. **第2轮**：根据结果继续分析，调用工具获取更多数据
3. **第3轮**：最终尝试，调用工具获取数据
4. **兜底机制**：达到 3 次限制或无有效结果时，给出明确的兜底回复

### ReAct 模式三轮兜底

对于复杂语义，系统会使用 ReAct 模式进行深度分析，最多调用工具 3 次：

1. **第1轮**：分析语义，调用工具获取数据
2. **第2轮**：根据结果继续分析，调用工具获取更多数据
3. **第3轮**：最终尝试，调用工具获取数据
4. **兜底机制**：达到 3 次限制或无有效结果时，给出明确的兜底回复

### 检索后端

系统支持两种检索后端：

- **Elasticsearch**：大规模文档场景下性能更优
- **默认内存检索**：ES 连接失败时自动降级

## ⚙️ 配置说明

配置文件位于 `harness/config.yaml`：

```yaml
llm:
  model: qwen3-max
  model_type: qwen_dashscope
  api_key: ${DASHSCOPE_API_KEY}

retrieval:
  max_ref_token: 20000
  parser_page_size: 500
  rag_searchers: ['keyword_search', 'front_page_search']

elasticsearch:
  host: https://localhost
  port: 9200
  user: elastic
  password: ${ES_PASSWORD}
  index_name: qwen_agent_rag_index

webui:
  server_port: 7860

mcp_tools:
  tavily-mcp:
    command: "npx"
    args: ["-y", "tavily-mcp@0.1.4"]
    env:
      TAVILY_API_KEY: "${TAVILY_API_KEY}"
```

## 🔧 工具列表

| 工具名 | 功能 | 类型 |
|--------|------|------|
| `retrieval` | 文档检索 | 框架内置 |
| `doc_parser` | 文档解析 | 框架内置 |
| `code_interpreter` | Python 代码执行 | 框架内置 |
| `web_search` | 互联网搜索 | 框架内置 |
| `image_gen` | AI 图像生成 | 框架内置 |
| `tavily-mcp` | 互联网搜索 | MCP 协议 |

## 📝 示例问题

- "介绍下雇主责任险"
- "帮我查询几天股市情况"
- "画一只熊猫"
- "帮我计算1+1"
- "你好"
- "我是谁"

## 🐛 常见问题

### Elasticsearch 连接失败

系统会自动降级到默认内存检索，不会影响正常使用。检查 `elasticsearch.host` 和 `elasticsearch.port` 配置是否正确。

### API Key 未设置

设置 `DASHSCOPE_API_KEY` 环境变量，或在配置文件中直接指定。

### 端口被占用

修改 `harness/config.yaml` 中的 `webui.server_port` 配置。

## 📄 许可证

本项目采用 **Apache 2.0 License** 许可证，与 Qwen-Agent 框架保持一致。

详细许可证文本请参见 [LICENSE](LICENSE) 文件。

## 🛠️ 技术栈

| 分类 | 技术 | 版本 | 许可证 |
|------|------|------|--------|
| 框架 | Qwen-Agent | 0.0.34 | Apache 2.0 |
| UI | Gradio | 5.23.1 | Apache 2.0 |
| LLM API | DashScope | 1.25.17 | Apache 2.0 |
| 文档检索 | Elasticsearch | 9.4.1 | Elastic License |
| 文档处理 | PyMuPDF | 1.27.2.3 | AGPL |
| 文档处理 | pdfplumber | 0.11.9 | MIT |
| 向量检索 | sentence-transformers | 5.6.0 | Apache 2.0 |
| 向量检索 | FAISS | 1.13.2 | MIT |
| MCP 协议 | mcp | 1.12.4 | MIT |
| 语言 | Python | 3.8+ | PSF License |

## 📊 核心依赖

```bash
# 核心框架
qwen-agent==0.0.34
gradio==5.23.1
dashscope==1.25.17

# 文档处理
PyMuPDF==1.27.2.3
pdfplumber==0.11.9
python-docx==1.2.0

# 检索后端
elasticsearch==9.4.1

# 配置管理
PyYAML==6.0.3
python-dotenv==1.2.2

# 向量检索
sentence-transformers==5.6.0
faiss-cpu==1.13.2

# MCP 协议
mcp==1.12.4
```

## 🤝 贡献指南

### 代码规范

- 代码风格遵循 PEP 8
- 使用类型注解
- 提交信息格式：`type(scope): description`
  - `feat`: 新功能
  - `fix`: 修复 Bug
  - `docs`: 文档更新
  - `refactor`: 重构
  - `test`: 测试
  - `chore`: 构建/工具

### 提交流程

1. Fork 项目
2. 创建分支：`git checkout -b feature/your-feature`
3. 提交代码：`git commit -m "feat: 添加新功能"`
4. 推送到远程：`git push origin feature/your-feature`
5. 创建 Pull Request

## 🙏 致谢

- **Qwen-Agent**：阿里巴巴达摩院提供的大模型智能体框架
- **DashScope**：阿里云提供的大模型服务平台
- **Gradio**：快速构建 Web UI 的开源框架
- **Elasticsearch**：分布式搜索引擎
- **Tavily**：AI 搜索 API

## 📬 联系方式

- 项目地址：请替换为实际的 GitHub 仓库地址
- 问题反馈：请在 GitHub Issues 中提交问题
- 邮件：请替换为实际的联系邮箱

**注意**：请将上述占位符替换为真实的项目信息后再提交到 GitHub。

## 📋 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0.0 | 2026-07-06 | 初始版本，包含语义分析路由器、ReAct模式、ES检索 |

---

*项目维护时间：2026-07-06*
