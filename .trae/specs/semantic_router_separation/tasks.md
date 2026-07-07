# SemanticRouter 逻辑分离 - Implementation Plan

## [x] Task 1: 重构Direct模式工具调用分支
- **Priority**: high
- **Depends On**: None
- **Description**: 
  - 重构Direct模式的工具调用分支，确保独立执行
  - 流程：调用LLM判断工具 → 调用工具 → 清理消息 → 生成最终回答
  - 确保工具调用分支不涉及检索逻辑
- **Acceptance Criteria Addressed**: AC-1, AC-5
- **Test Requirements**:
  - `programmatic` TR-1.1: 输入"帮我画一个宇宙飞船"，日志显示"工具调用分支"，无"检索逻辑"相关日志
  - `programmatic` TR-1.2: LLM调用次数不超过2次
  - `human-judgement` TR-1.3: 代码结构清晰，工具调用分支逻辑独立

## [x] Task 2: 重构Direct模式检索分支
- **Priority**: high
- **Depends On**: Task 1
- **Description**: 
  - 重构Direct模式的检索分支，确保独立执行
  - 流程：直接调用retrieval工具 → 清理消息 → 生成最终回答
  - 确保检索分支不涉及工具调用逻辑（除retrieval工具外）
- **Acceptance Criteria Addressed**: AC-2, AC-5
- **Test Requirements**:
  - `programmatic` TR-2.1: 输入"介绍下雇主责任险"，日志显示"检索逻辑分支"，无"工具调用"相关日志（除retrieval）
  - `programmatic` TR-2.2: LLM调用次数不超过2次
  - `human-judgement` TR-2.3: 代码结构清晰，检索分支逻辑独立

## [x] Task 3: 重构Complex模式工具调用分支
- **Priority**: medium
- **Depends On**: Task 2
- **Description**: 
  - 重构Complex模式的工具调用分支，确保独立执行
  - 流程：ReAct推理 → 调用工具 → 清理消息 → 生成最终回答
  - 确保工具调用分支不涉及检索逻辑
- **Acceptance Criteria Addressed**: AC-3, AC-5
- **Test Requirements**:
  - `programmatic` TR-3.1: 输入"分析一下这个问题"，日志显示"工具调用分支"，无"检索逻辑"相关日志
  - `programmatic` TR-3.2: LLM调用次数不超过3次（ReAct推理）
  - `human-judgement` TR-3.3: 代码结构清晰，工具调用分支逻辑独立

## [x] Task 4: 重构Complex模式检索分支
- **Priority**: medium
- **Depends On**: Task 3
- **Description**: 
  - 重构Complex模式的检索分支，确保独立执行
  - 流程：直接调用retrieval工具 → 清理消息 → 生成最终回答
  - 确保检索分支不涉及工具调用逻辑（除retrieval工具外）
- **Acceptance Criteria Addressed**: AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-4.1: 输入"关于保险你能说什么"，日志显示"检索逻辑分支"，无"工具调用"相关日志（除retrieval）
  - `programmatic` TR-4.2: LLM调用次数不超过2次
  - `human-judgement` TR-4.3: 代码结构清晰，检索分支逻辑独立

## [x] Task 5: 验证整体逻辑
- **Priority**: high
- **Depends On**: Task 4
- **Description**: 
  - 验证所有模式的逻辑分离是否正确
  - 确保无循环调用问题
  - 运行测试用例验证各分支独立执行
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5
- **Test Requirements**:
  - `programmatic` TR-5.1: 所有测试用例通过，无循环调用
  - `programmatic` TR-5.2: 代码语法检查通过
  - `human-judgement` TR-5.3: 整体代码结构清晰，两条分支逻辑完全分离
