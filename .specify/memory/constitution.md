# UI 自动化平台 Constitution

## Core Principles

### I. 文档先行、代码后写（NON-NEGOTIABLE）
每个批次先出增量设计文档（含语义决策 + 文件级任务列表），用户确认后再动代码。SDD 六步（specify → plan → tasks → implement → converge）即为此铁律的执行载体；禁止跳过 spec/plan 直接写代码。

### II. 事实以代码为准
确认任何功能状态，必须以真实代码文件或可执行命令输出为依据，禁止凭文档推断。文档与代码不一致时，以代码为准并回改文档。

### III. 冻结契约不可破坏
动作字典（当前 51 条）、CAPABILITY_MATRIX、FR1–FR58 只允许新增；改冻结项必须走变更流程并在文档「变更记录」留痕。适配器分发约定（方法名 == action_key、kwargs == params_schema）不得偏离。

### IV. 改表必须走 Alembic
`revision --autogenerate` + `upgrade head`，禁止删库重建；`alembic check` 是模型↔迁移一致性唯一判据；`backend/sql/schema.sql`（MySQL DDL）同步更新。

### V. 统一错误信封与分层红线
新错误码 = `core/errors.py` 加类且同步文件底部汇总列表；新 router 必须在 `api/v1/__init__.py` 注册；`lint-imports`（2 kept）不得破坏。FR34：artifact 只由执行器落库，适配器只产出文件/路径。

## 附加约束（范围边界）

D26 明确不做：鉴权、分页、通知管理 UI、多实例/Redis、WS 鉴权、Docker/CD（CI 已由 D40 放行：只校验不部署）。生产库定为 SQLite（2026-11-08 用户决策，GAP-25 改判不适用）。平台是小型测试团队内部工具，非 SaaS、单机单实例。

## 开发工作流与质量门禁

每批次收尾必须：回填《docs/待办与缺口跟踪.md》（每条 GAP 状态附证据命令）→ 更新 README → `pytest` 全绿 → commit + push。CI 门禁：ruff → pytest → import-linter → audit_status --check → compileall → 全新库 alembic。测试用例随实现同步交付，冒烟脚本进 `scripts/`。

## Governance

Constitution 优先于任何其他实践；修订需在本文档留痕并同步 HANDOVER。与《docs/HANDOVER.md》《docs/待办与缺口跟踪.md》冲突时，以本文档为准并回改另两份。

**Version**: 1.0.0 | **Ratified**: 2026-11-08 | **Last Amended**: 2026-11-08
