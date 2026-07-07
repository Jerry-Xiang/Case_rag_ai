# SemanticRouter 逻辑分离 - Product Requirement Document

## Overview
- **Summary**: 重构SemanticRouter中Direct和Complex模式的处理逻辑，将工具调用分支和检索分支完全分离，避免两条逻辑线同时执行导致的循环调用问题。
- **Purpose**: 解决当前代码中工具调用和检索逻辑混合导致的循环调用、参数解析失败等问题，确保两条逻辑线独立执行。
- **Target Users**: SemanticRouter的使用者和维护者

## Goals
- 将Direct模式的工具调用逻辑和检索逻辑完全分离
- 将Complex模式的工具调用逻辑和检索逻辑完全分离
- 确保两条逻辑线的LLM调用独立，互不影响
- 消除循环调用问题

## Non-Goals (Out of Scope)
- 不修改Chat模式的逻辑
- 不修改语义分析分类逻辑
- 不修改工具定义和注册机制

## Background & Context
当前代码存在以下问题：
1. Direct模式先调用LLM（传入工具列表），LLM返回带有工具调用标记的消息
2. 如果工具调用检测失败（参数解析失败），则走检索分支
3. 检索分支调用LLM生成最终回答时，消息中仍包含之前的工具调用标记
4. LLM继续生成工具调用，导致循环

## Functional Requirements
- **FR-1**: Direct模式下，工具调用分支和检索分支完全独立，不会互相影响
- **FR-2**: Complex模式下，工具调用分支和检索分支完全独立，不会互相影响
- **FR-3**: 工具调用分支：调用LLM判断工具 → 调用工具 → 生成最终回答
- **FR-4**: 检索分支：直接调用检索工具 → 生成最终回答
- **FR-5**: 两条分支的LLM调用参数独立设置

## Non-Functional Requirements
- **NFR-1**: 代码结构清晰，两条分支逻辑易于理解和维护
- **NFR-2**: 避免循环调用，每条分支最多调用LLM 2次（判断+回答）
- **NFR-3**: 错误处理完善，任何分支失败都有兜底机制

## Constraints
- **Technical**: Python 3.10+, Qwen Agent框架
- **Dependencies**: 依赖现有的Agent基类、工具调用机制、LLM调用接口

## Assumptions
- 工具列表中包含retrieval工具用于检索
- LLM支持函数调用格式
- 工具调用检测机制正常工作

## Acceptance Criteria

### AC-1: Direct模式工具调用分支独立执行
- **Given**: 用户输入"帮我画一个宇宙飞船"，语义分析为Direct模式
- **When**: 系统检测到需要调用image_gen工具
- **Then**: 只执行工具调用分支，调用image_gen工具，生成最终回答，不走检索逻辑
- **Verification**: `programmatic` - 日志显示"工具调用分支"，无"检索逻辑"相关日志

### AC-2: Direct模式检索分支独立执行
- **Given**: 用户输入"介绍下雇主责任险"，语义分析为Direct模式
- **When**: 系统未检测到需要调用工具
- **Then**: 只执行检索分支，调用retrieval工具，生成最终回答，不走工具调用逻辑
- **Verification**: `programmatic` - 日志显示"检索逻辑分支"，无"工具调用"相关日志

### AC-3: Complex模式工具调用分支独立执行
- **Given**: 用户输入"分析一下这个问题"，语义分析为Complex模式
- **When**: 系统通过ReAct推理检测到需要调用工具
- **Then**: 只执行工具调用分支，调用工具，生成最终回答，不走检索逻辑
- **Verification**: `programmatic` - 日志显示"工具调用分支"，无"检索逻辑"相关日志

### AC-4: Complex模式检索分支独立执行
- **Given**: 用户输入"关于保险你能说什么"，语义分析为Complex模式
- **When**: 系统通过ReAct推理未检测到需要调用工具
- **Then**: 只执行检索分支，调用retrieval工具，生成最终回答，不走工具调用逻辑
- **Verification**: `programmatic` - 日志显示"检索逻辑分支"，无"工具调用"相关日志

### AC-5: 无循环调用
- **Given**: 任何用户输入
- **When**: 系统处理请求
- **Then**: 不会出现无限循环的工具调用，每条分支最多调用LLM 2次
- **Verification**: `programmatic` - 日志显示LLM调用次数不超过2次

## Open Questions
- [ ] 是否需要在检索分支中也调用LLM进行语义判断？
- [ ] Complex模式的三轮工具调用限制是否需要调整？
