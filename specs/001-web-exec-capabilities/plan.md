# Implementation Plan: Web 执行能力补齐（M3.8）

**Branch**: `001-web-exec-capabilities` | **Date**: 2026-11-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-web-exec-capabilities/spec.md`

## Summary

补齐四项 Web 执行能力（GAP-09/10/12/13）：网络 mock 与响应检索（3 个新动作）、下载产物化（1 个新动作 + 新产物类型）、iframe 按元素进入（冻结动作语义扩展）、执行级变量（内建动作参数扩展）。实现全部收敛在既有架构的扩展点上：动作字典 + 能力矩阵 + Playwright 适配器 + 平台内建动作 + 执行器两处校验，**零新表、零新 REST 端点**（artifact.kind 为 VARCHAR(32)，新增枚举值无迁移）。

## Technical Context

**Language/Version**: Python 3.11+（后端）/ TypeScript + Vue 3 + Vite（前端）

**Primary Dependencies**: FastAPI、SQLAlchemy (async)、Playwright (python)、pytest、ruff、import-linter

**Storage**: SQLite（生产库选型 2026-11-08 用户决策定案）；本批次无表结构变更

**Testing**: pytest（275 passed + 1 skipped 基线）+ 五份 Web 冒烟（scripts/smoke_m3*.py，113 项）+ 新增 smoke_m38.py

**Target Platform**: Windows 开发机 / 单机单实例服务（FastAPI uvicorn）

**Project Type**: monorepo web-service（backend/ + frontend/ + scripts/ + docs/）

**Performance Goals**: 不变（单执行串行复用会话；mock/响应收集器为会话内内存操作，无额外网络往返）

**Constraints**: 冻结契约（动作字典/矩阵/FR1–58）只增不改；统一错误信封；FR34 artifact 只由执行器落库；D43 单步硬上限语义不受影响

**Scale/Scope**: 动作字典 51 → 55；4 个新适配器方法 + 2 个内建/执行器扩展点；前端预期零到极小改动（编排表单由 params_schema 驱动）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原则 | 评估 | 依据 |
|---|---|---|
| I. 文档先行 | ✅ PASS | 本 plan 即 spec → plan → tasks 流程产物，implement 在用户确认 tasks 后启动 |
| II. 事实以代码为准 | ✅ PASS | 关键扩展点均已核实代码：`case_service._special_element_need`（绑元素特判钩子）、`db.py:77`（启动自动 seed 字典）、`schema.sql:270`（kind 为 VARCHAR(32)） |
| III. 冻结契约 | ⚠️ 合规变更 | 动作字典**只新增** 4 条；`set_variable` 加**可选** scope 参数、`switch_to_iframe` 加**可选**元素形态均为向后兼容扩展，走变更流程在设计文档变更记录留痕（FR-014） |
| IV. Alembic | ✅ PASS | 零表结构变更（artifact.kind 非枚举列，DDL 为 VARCHAR(32)） |
| V. 错误信封/分层/FR34 | ✅ PASS | 解除不存在的 mock 用既有 ValidationFailed（无需新错误码）；下载产物走 `ctx.artifacts` → 执行器 `_record` 落库（FR34 语义不变）；适配器不 import DB 层 |

**Re-check after Phase 1**: 通过（research R1–R9 均未引入越界依赖；无新增违规）。

## Project Structure

### Documentation (this feature)

```text
specs/001-web-exec-capabilities/
├── plan.md              # 本文件
├── research.md          # Phase 0：9 项技术决策（R1–R9）
├── data-model.md        # Phase 1：数据影响面（零新表 + kind 新值 + 内存态变量）
├── quickstart.md        # Phase 1：端到端验证指引
├── contracts/
│   └── action-schema.md # Phase 1：4 个新动作 + 2 个扩展动作的 params_schema 契约
└── tasks.md             # Phase 2（/speckit-tasks 产出）
```

### Source Code (repository root)

```text
backend/app/
├── domain/
│   ├── action_keys.py        # +4 ActionDef（NETWORK×3 / ELEMENT×1）；set_variable、switch_to_iframe 参数扩展
│   └── capabilities.py       # _WEB 集合 +4
├── engines/
│   ├── actions.py            # _builtin_set_variable 读 scope；dispatch 渲染用双层变量视图
│   ├── base.py               # ActionContext +shared_variables/case_started_ts（additive）；EngineAdapter +reset_case_scope() 默认 no-op
│   └── adapters/
│       └── playwright_adapter.py  # mock_route/unmock_route/wait_for_response/download_file；switch_to_iframe 元素形态；reset_case_scope 覆写；响应收集器
├── services/
│   ├── case_service.py       # _special_element_need 增加 switch_to_iframe（绑元素）/download_file
│   └── execution_service.py  # execution_vars 建立与传递；每用例开始调用 reset_case_scope；needs_element 与写入口共用同一规则
frontend/src/                 # 预期零改动；仅当编排页对动作绑元素有硬编码限制时微调
scripts/
├── serve_fixtures.py         # fixture 站 +下载链接页 + mock 演示页 + 双 iframe 页
└── smoke_m38.py              # 本批次冒烟（对齐 spec 全部验收场景）
backend/tests/                # 单测：新动作 schema/行为 + 变量作用域 + iframe 互斥校验
```

**Structure Decision**: 全部改动落在既有 monorepo 分层内；无新增顶层目录、无新 router 注册。

## Complexity Tracking

> 无 Constitution 违规，无需记录。
