# UI 自动化平台 · M3 详细设计：执行内核（M3.1）与编排呈现（M3.2）

| 项 | 值 |
|---|---|
| **文档编号** | D2-M3 |
| **版本** | v1.2（含 M3.1 执行内核 + M3.3 用例集） |
| **日期** | 2026-10-19 |
| **上游依赖** | D1 技术方案（D1–D6）· D2-M1 v1.2 · D2-M2 v1.0 |
| **本文性质** | **施工图**。M1 回答"引擎怎么插"，M2 回答"元素怎么管"，本文回答"**执行怎么调度、结果怎么留痕**" |
| **状态** | 待评审（M3.1 先实现） |

---

## 0. 本文定位与决策

### 0.1 文档链位置

```
D0 选型 → D1 总方案 → D1a 移动端 → D2-M1 骨架/适配层 → D2-M2 元素库
                                              ↓
                              D2-M3 本文（执行内核 + 编排呈现）
                                              ↓
                              D2-M4 扩端 · D3 工程约定
```

### 0.2 为什么把 M3 拆成两批（决策 D19）

M3 的原始范围（D1 §12）包含：队列、WebSocket、StepEditor、报告、通知、健康度。一次做完有两个问题：

1. **StepEditor 的交互形态需要单独推敲**（表单 vs JSON vs 低代码拖拽），会拖慢"执行内核"的冻结；
2. 执行内核是**所有后续功能的地基**——报告、通知、健康度都依赖 `execution` 的状态机与产物落库。地基不稳，上层全是返工。

所以拆成：

| 批次 | 范围 | 交付判据 |
|---|---|---|
| **M3.1 执行内核**（本文主体） | 异步队列、并发上限、重试、取消、产物落库、报告生成、WebSocket、事件持久化、启动自愈 | 提交执行**立即返回 202**；并发受控；失败可重试；产物与报告可追溯 |
| **M3.2 编排与呈现**（**已交付 2026-10-19**） | StepEditor（表单式）、报告页、产物访问、用例批量执行、Alembic 迁移、`report` 唯一键、成员启用开关、执行列表按用例集筛选 | 能在界面上编用例、看报告；**不包含**权限/通知/分页等平台管理功能 |
| **M3.3 用例集**（已在 M3.2 之前插入并交付） | `test_suite` + `test_suite_case`；用例集 CRUD、成员管理、单次运行、cron 定时 | 四层模型落地；报告能追溯"哪个用例集跑出来的" |

> **交付方式已确认（2026-10-19）**：M3.2 作为独立批次单独交付，不与 M3.1 合并验收。
> 这符合项目定位：**小型测试团队内部使用的用例管理与执行平台**，不是对外 SaaS。

### 0.2.1 范围收敛（2026-10-19 确认）

用户明确：只做「项目 / 元素 / 用例管理 + 按引擎执行 + 生成报告」，**平台管理类功能尽量削减**。据此调整：

| 功能 | 原计划 | 调整后 | 理由 |
|---|---|---|---|
| 登录鉴权 | M3.2 | ❌ **不做** | 内网小团队，无多租户；`created_by` 保持空 |
| WS 鉴权 | GAP-36 | ❌ **不做** | 随鉴权一起取消 |
| 分页 | M3.2 | ❌ **不做**（保留 `limit` 上限与搜索） | 元素/用例在千级，全量返回足够 |
| 通知（企微/钉钉/Webhook） | M3.2 | ⏸ **暂不做**（可选） | 不在"执行 + 报告"闭环内；需要时再加 |
| 定位符健康度页 | M3.2 | ⏸ **暂不做**（数据已埋点，随时可查） | 属分析增强，不是核心闭环 |
| Docker | M4 前 | ⏸ **暂不做** | 单机内部部署，脚本启动即可 |
| CI（GitHub Actions） | — | ✅ **已接入**（D40，只校验不部署） | backend / frontend / e2e 三 job，2026-11-04 |
| 多实例 / Redis | 视规模 | ❌ **不做** | 见 §0.5 |

> **保留不动的**：报告页、StepEditor、产物访问、用例批量执行 —— 它们直接服务"编用例 → 执行 → 看报告"这条主链。

### 0.2.2 "用例集"的落地方式

需求里提到"将**用例集**通过对应引擎执行"。当前用 `POST /executions {case_ids: [...]}` 表达**选中的一批用例**，语义已覆盖。

**建议不新增 `test_suite` 表**：小团队场景下，"用例集"通常就是"这次要跑的几条用例"，建实体反而要多维护一层分组、成员、排序。M3.2 只在界面上提供"按项目多选用例 → 批量执行"。

> 若后续需要**固化**的回归集（如"冒烟 10 条"每天跑），再单列 `test_suite` + `test_suite_case`。届时是一次独立的小迭代，不影响现有契约。**此项已登记为待确认 Q-11。**

> 拆分不改变 D1 的里程碑编号，只明确"先交什么"。

### 0.3 本文依据的决策

**继承**：D1 自建 · D2 Python+FastAPI · D5 三端 · D6 英文动作名 · D7 横切 · D9 monorepo · D11 `run_python` 默认禁用 · D13/D18 前端零组件库 + SortableJS · D14 无拾取器 · D15 纯树 · D16 不做跨项目共享 · D17 文档顺序。

**本文新增**（对应《待办与缺口跟踪》Q-01 ~ Q-10 的倾向，未否决即执行）：

| # | 决策 | 选定 | 理由 |
|---|---|---|---|
| **D19** | M3 分批 | ✅ **M3.1 执行内核 / M3.2 单独交付** | 见 §0.2；已确认 |
| **D20** | 报告格式 | **HTML（人看）+ JSON（机器读）**，`report.format ∈ {HTML, JSON}` 各一行 | JUnit 等接 CI 再加，避免现在猜格式 |
| **D21** | 并发上限 | 默认 **2**，`UIP_MAX_CONCURRENT_EXECUTIONS` 可配 | 每个执行一个 Chromium；开发机 2 个较安全 |
| **D22** | 取消语义 | **只在"步骤之间"生效**，不强杀浏览器 | 强杀会留下半截会话与脏产物；步骤内强杀需 Playwright 中断改造，收益低 |
| **D23** | 队列实现 | ✅ **进程内 `asyncio.Queue` + 信号量，确定不引入 Redis** | 单机单实例、并发 2、队列上限 200；Redis 的复杂度和收益不匹配（§0.5） |
| **D24** | 事件推送 | **同一进程内事件总线 + WebSocket**，事件同时写 JSONL | 进程外无法收到 WS（需 Redis pub/sub），这一点在 §6.1 冻结 |
| **D25** | 执行结果轮询 | **前端每 5s 轮询一次（≤30s 约束内），不设固定重试次数**，直到终态 | 执行通常 5–20s；5s 足够，且比 1s 少 4 倍请求；轮询次数不设上限，靠服务端超时与启动自愈兜底 |
| **D26** | 平台管理功能 | **不做**鉴权 / 分页 / 通知 / Docker / 多实例 | 内部小团队，范围收敛（§0.2.1） |
| **D27** | 数据层级 | ✅ **项目 → 用例集 → 用例 → 元素+动作**（四层）；**用例集是执行单元**，单次/定时都以它为单位 | 这是行业主流做法；报告与调度都需要"一次执行对应一个集合" |
| **D28** | 定时实现 | **APScheduler `AsyncIOScheduler` + 内存 job store**，5 段 cron，`misfire_grace_time=60s`，启动时从 DB 重建 | 与队列同一单进程语义；不引入 Redis/Celery（D23） |

### 0.4 M3.1 相对 M2 的增量

| 层 | 增量 |
|---|---|
| 配置 | `max_concurrent_executions` / `max_pending` / `report_dir` / `event_log_dir` |
| 数据表 | `execution_step_result.attempt`（加列，FR16 允许） |
| 服务 | `execution_queue`（新）/ `event_bus`（新）/ `report_service`（新）；`execution_service` 重构为 "submit + execute" |
| API | `POST /executions` → **202**；`POST /executions/{id}:cancel`；`GET /executions/{id}/report`；`WS /ws/executions/{id}` |
| 错误码 | `EXECUTION_NOT_FOUND` / `EXECUTION_CANNOT_CANCEL` / `REPORT_NOT_READY` / `QUEUE_FULL` |
| 前端 | 提交后轮询 + 进度条 + 取消按钮 + 报告链接 |
| 测试 | 队列限流、重试、取消、报告、契约测试 |

---

### 0.5 是否需要 Redis？（评估结论：**不需要**）

**结论：不引入 Redis，现有进程内队列满足定位。**

#### 成本

| 维度 | 引入 Redis 要付的代价 |
|---|---|
| 部署 | 多一个常驻服务；开发机/测试机都要装；多环境配置与版本管理 |
| 代码 | 队列从 `asyncio.Queue` 改为 Redis List/Stream；worker 独立进程；任务序列化与幂等；失败重投与可见性超时 |
| WS | 进程内事件总线失效，需要 Redis pub/sub 或退回轮询 |
| 运维 | 内存上限、持久化策略、连接池、Redis 挂了怎么办 |
| 排障 | 多一层"任务到底在 Redis 还是在 worker"的排查路径 |

#### 收益（当前场景用不上）

| Redis 的能力 | 本项目当前是否需要 |
|---|---|
| 多实例共享队列 | ❌ 单机单实例 |
| 重启不丢排队任务 | ❌ 内网平台，重启时重新提交即可（且有启动自愈把残留置 ERROR） |
| 跨机器分布式执行 | ❌ M4 云真机之前不需要；真需要时也是"执行节点注册"，不只是队列 |
| 高吞吐（>100 任务/分钟） | ❌ 小团队，日均个位数到几十次 |

#### 不引入的代价（已接受，且有兜底）

| 代价 | 兜底 |
|---|---|
| 重启丢排队任务 | `reconcile_orphans()` 把 RUNNING/PENDING 置 ERROR，前端能看到"进程重启中断"，重新提交即可 |
| WS 只在同进程有效 | 前端默认**轮询 5s**（D25），WS 只是可选增强 |
| 无法横向扩并发 | 并发上限 2 是刻意限制（每个执行一个 Chromium）；真要提高应先加机器而不是加队列 |

#### 什么时候该重新评估（触发条件，满足任意一条）

1. 需要**多实例部署**（负载均衡 / 高可用）；
2. 重启**不能丢**排队任务（例如定时回归集中触发）；
3. 单机并发需求 > 4 且要跨机器分发执行；
4. M4 接入云真机，需要"执行节点注册 + 任务分发"。

> 这四条都不满足前，引入 Redis 属于**为不存在的需求付运维成本**。

#### 据此的方案调整点

| 调整点 | 原方案 | 调整后 |
|---|---|---|
| 队列 | 预留"多 worker 换 Redis" | **明确单进程**，FR30/FR40 标注为"已决策"，不再是临时妥协 |
| WS | 作为实时主通道 | 降级为**可选增强**，前端以轮询为准（D25） |
| 并发 | 可配置上限 | 保留 `UIP_MAX_CONCURRENT_EXECUTIONS=2`，并注明"提高前先加机器" |
| 待办 | GAP-28（多 worker）挂在 P2 | 改为 **🚫 范围外**，并附上面的触发条件 |

---

## 1. 里程碑目标与验收（M3.1）

### 1.1 一句话目标

**把"点一下跑一个用例、等十几秒"变成"提交即返回、并发受控、失败可重试、结果可追溯"。**

### 1.2 验收标准（V1–V9，全部可执行）

| # | 验收项 | 操作 | 期望 |
|---|---|---|---|
| **V1** | 提交即返回 | `POST /api/v1/executions` | **202**，响应 `{id, status:"PENDING"}`，耗时 < 200ms（不再等执行完） |
| **V2** | 状态推进 | 轮询 `GET /executions/{id}` | `PENDING → RUNNING → PASSED`，终态后不再变化 |
| **V3** | 并发上限 | 连续提交 4 个执行（`max_concurrent=2`） | 同时处于 `RUNNING` 的**最多 2 个**；其余排队为 `PENDING` |
| **V4** | 失败重试 | 造一个 `on_failure=RETRY, retry_times=2` 的必失败步骤 | 该步骤执行 **3 次**（1 次 + 2 次重试）；结果行 `attempt` 依次为 1/2/3（或最终行 `attempt=3`）；执行终态 `FAILED` |
| **V5** | 取消 | 提交后立刻取消 | `PENDING` 或 `RUNNING` → `CANCELLED`；已完成的步骤结果保留；未跑的步骤不产生结果 |
| **V6** | 产物落库 | 执行含 `screenshot` 的用例 | `artifact` 表出现 1 行，`execution_id`/`step_result_id` 正确，文件真实存在 |
| **V7** | 报告 | 执行结束后 `GET /executions/{id}/report` | 返回 HTML（`text/html`）；`report` 表有 HTML + JSON 两行；内容含 passed/failed/errored 与每步 `fallback_index` |
| **V8** | WS 推送 | 连接 `/ws/executions/{id}` 后提交执行 | 依次收到 `execution.started → case.started → step.finished… → execution.finished`；终态后连接可关闭 |
| **V9** | 启动自愈 | 手工把某执行置为 `RUNNING` 后重启服务 | 启动后被改为 `ERROR`，`message` 含"进程重启" |
| **V10** | 用例集 CRUD 与成员（M3.3） | 建用例集 → 加 2 条用例（重复加入应跳过）→ 移除 1 条 → 排序 | 成员顺序与 `sort` 一致；跨项目用例被拒（`invalid`）；同名用例集 409 |
| **V11** | 单次运行与报告追溯 | `POST /suites/{id}:run` → 轮询 → 取报告 | 202；执行 `suite_id`/`suite_name` 有值；**报告抬头显示用例集名**；`last_run_at` 被更新 |
| **V12** | 定时触发（M3.3） | 建用例集，cron 设为 1 分钟后，等到点 | 自动产生一条 `trigger_type=SCHEDULE` 的执行；重启后 job 被重建 |

### 1.3 明确不做（M3.1）

| 不做 | 原因 | 归属 |
|---|---|---|
| StepEditor | 交互形态待定（Q-09） | M3.2 |
| 通知 | 依赖执行完成事件，已具备但渠道优先级待定（Q-10） | M3.2 |
| 定位符健康度页 | 数据源已就绪，聚合口径需与"稳定性"定义一起定 | M3.2 |
| Redis / 多 worker | 决策 D23 | GAP-28 |
| 断言自动重试 | 语义待定（Q-05） | GAP-03 |
| `storage_state` | 决策：不提前 | GAP-06 |

---

## 2. 后端设计

### 2.1 新增/改动文件

```
backend/app/
├─ core/config.py                 ✏️ + max_concurrent_executions / max_pending / report_dir / event_log_dir
├─ models/__init__.py             ✏️ ExecutionStepResult + attempt
├─ engines/base.py                ✏️ ActionContext + artifacts: list[dict]
├─ engines/adapters/playwright_adapter.py  ✏️ screenshot() 写入 ctx.artifacts
├─ services/
│  ├─ execution_queue.py          [新] 队列 + worker + 信号量 + 启动自愈
│  ├─ event_bus.py                [新] 进程内发布/订阅（按 execution_id）
│  ├─ report_service.py           [新] HTML + JSON 报告
│  └─ execution_service.py        ✏️ 拆 submit / execute；重试、取消、产物、事件、报告
├─ api/v1/executions.py           ✏️ 202 / cancel / report
├─ api/ws.py                      [新] /ws/executions/{id}
├─ main.py                        ✏️ 启动/关闭队列、注册 WS、reconcile
└─ sql/schema.sql                 ✏️ attempt 列

backend/tests/unit/
├─ test_execution_queue.py        [新] 限流与顺序
├─ test_report_service.py         [新] 报告内容
└─ test_adapter_contract.py       [新] 参数化跑全部 adapter（GAP-24）
```

### 2.2 执行状态机（冻结）

```
                 submit
                   │
                   ▼
   ┌──────────► PENDING ──cancel──► CANCELLED（终态）
   │               │  worker 取到
   │               ▼
   │            RUNNING ──cancel（步骤间检查点）──► CANCELLED（终态）
   │               │
   │               ├── 全部通过 ──► PASSED（终态）
   │               ├── 有 FAILED ─► FAILED（终态）
   │               └── 有 ERROR ──► ERROR（终态）
   │
   └── 启动时发现残留 RUNNING ──► ERROR（message="进程重启，执行中断"）
```

**不变量**：

| # | 不变量 |
|---|---|
| INV-1 | 终态（PASSED/FAILED/ERROR/CANCELLED）不可再变 |
| INV-2 | `PENDING` 才能被 worker 取走；取走时用条件更新（防重复消费） |
| INV-3 | `finished_at`/`duration_ms` 只在进入终态时写一次 |
| INV-4 | `passed + failed + errored` 等于"跑完的用例数"，`skipped` 单独计 |

> INV-2 的实现：`UPDATE execution SET status='RUNNING' WHERE id=? AND status='PENDING'`，`rowcount==1` 才继续。进程内队列本不会重复投递，但这条让"多 worker 时也不会重复跑"。

### 2.3 队列与并发（D23）

```python
class ExecutionQueue:
    """进程内 FIFO 队列 + 固定 worker + 信号量限流。"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[int] = asyncio.Queue(maxsize=settings.max_pending)
        self._workers: list[asyncio.Task] = []
        self._sem = asyncio.Semaphore(settings.max_concurrent_executions)
        self._closing = False

    async def start(self) -> None:
        for i in range(settings.max_concurrent_executions):
            self._workers.append(asyncio.create_task(self._worker(f"w{i}"), name=f"exec-worker-{i}"))

    async def submit(self, execution_id: int) -> None:
        try:
            self._queue.put_nowait(execution_id)
        except asyncio.QueueFull as exc:
            raise QueueFull("执行队列已满，请稍后重试", {"max_pending": settings.max_pending}) from exc

    async def _worker(self, name: str) -> None:
        while not self._closing:
            execution_id = await self._queue.get()
            try:
                async with self._sem:                 # 双保险：worker 数 == 上限时其实恒为 1
                    await execution_service.execute(execution_id)
            except Exception:
                logger.exception("worker %s failed on execution %s", name, execution_id)
            finally:
                self._queue.task_done()

    async def stop(self) -> None:
        self._closing = True
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
```

**为什么 worker 数 = 并发上限、还要再加信号量**：

- worker 数决定"同时最多几个执行在跑"（D21）；
- 信号量是为**将来**准备：若改成"多队列 / 按项目限流"，worker 数可能大于全局上限，信号量是最后一道闸。现在就加，避免届时改结构。

**队列容量**：`UIP_MAX_PENDING=200`，满了返回 `429 QUEUE_FULL`（不静默丢任务）。这是刻意的：**丢任务比报错更糟**——用户以为提交成功，其实永远不跑。

### 2.4 `execution_service` 重构：submit / execute 分离

```python
async def submit(db, *, project_id: int, case_ids: list[int],
                 target_id: int | None) -> Execution:
    """校验 + 建 PENDING 记录 + 入队。**不执行**。"""
    project = await get_project(db, project_id)
    _validate_cases(...)                     # 用例存在且属于该项目
    execution = Execution(status=PENDING, ...)
    db.add(execution); await db.commit(); await db.refresh(execution)
    await execution_queue.submit(execution.id)   # 队列满 → QUEUE_FULL（事务里已提交记录？见下）
    return execution
```

> **顺序陷阱**：先 commit 再入队。若入队失败（队列满），执行记录已存在但永不执行 —— 必须**回滚语义**：捕获 `QueueFull` 后把该记录置为 `CANCELLED` 并写 `message`，再抛出 429。宁可留一条"被取消"的记录，也不留一条永远 PENDING 的幽灵。

```python
async def execute(execution_id: int) -> None:
    """worker 侧：独立 session，跑完写结果/产物/报告/事件。"""
    async with SessionLocal() as db:
        if not await _claim(db, execution_id):        # INV-2 条件更新
            return
        ...
```

**为什么 worker 用独立 session**：请求的 session 在响应返回时就关闭了，而后台任务在其之后才跑；复用会拿到已关闭的 session。

### 2.5 重试（D22 之外的另一条：重试不改状态机）

```python
def max_attempts(step: TestStep) -> int:
    if step.on_failure == "RETRY" and step.retry_times > 0:
        return step.retry_times + 1
    return 1
```

| 策略 | 行为 |
|---|---|
| `ABORT` | 失败即中止本用例剩余步骤（标 SKIPPED） |
| `CONTINUE` | 失败后继续下一步 |
| `RETRY` | 失败后重试，最多 `retry_times` 次；**仍失败则按 ABORT 处理**（因为用户期望它成功） |

**每次尝试都写一行 `execution_step_result`**（`attempt=1/2/3`），而不是只留最后一次。理由：**排查需要看到"第一次为什么失败"** —— 只留最后一条会把最关键的现场丢掉。

> 代价：结果行数变多。可接受（失败重试本就是少数）；统计口径上，`failed` 按"用例"计，不受影响。

### 2.6 取消（D22）

```python
_cancel_flags: set[int] = set()

async def request_cancel(db, execution_id: int) -> Execution:
    execution = await _get(db, execution_id)
    if execution.status in TERMINAL:
        raise ExecutionCannotCancel("已结束的执行不能取消", {...})
    if execution.status == "PENDING":
        execution.status = "CANCELLED"; execution.finished_at = now
        await db.commit()
        return execution
    _cancel_flags.add(execution_id)          # RUNNING：打标记，步骤间检查
    return execution
```

**检查点**：每个步骤开始前 `if execution_id in _cancel_flags: break`，并把剩余步骤标 `SKIPPED`、执行置 `CANCELLED`。

**为什么不做"强杀浏览器"**：Playwright 的 `page` 操作没有安全的抢占式中断；强杀会留下半写状态的产物和未释放的 context。步骤间取消足够覆盖"跑错了想停"的真实场景。

### 2.7 产物落库（GAP-04）

```python
@dataclass
class ActionContext:
    ...
    artifacts: list[dict] = field(default_factory=list)   # [{"kind","path","size"}]

# playwright_adapter.screenshot()
ctx.artifacts.append({"kind": "SCREENSHOT", "path": target,
                      "size_bytes": os.path.getsize(target)})
```

worker 在写入步骤结果拿到 `step_result_id` 后，把 `ctx.artifacts` 逐条写 `artifact` 表（`storage="LOCAL"`）。

> **为什么不由适配器直接写库**：适配器不应该依赖 DB（否则 M4 的 Appium 适配器也要背数据库依赖，且单测无法脱离 DB 跑）。**适配器只产生"产物的路径事实"，落库是执行器的职责。**

### 2.8 报告（D20 / GAP-05）

`report_service.generate(db, execution_id)`：

| 产物 | 内容 | 落点 |
|---|---|---|
| HTML | 执行概览（状态/耗时/通过率）+ 每用例每步骤表格（含 `fallback_index`、`attempt`、错误信息、截图链接） | `{report_dir}/execution-{id}.html` |
| JSON | 与 HTML 同源的机器可读结构 | `{report_dir}/execution-{id}.json` |
| DB | `report` 两行（`format=HTML/JSON`，`path`，`summary`） | `report` 表 |

**幂等**：同一执行重复生成时**覆盖**文件、`report` 表按 `(execution_id, format)` 先删后插（避免重复行）。

**HTML 不引入模板引擎**：用 f-string + 少量内联 CSS。理由：报告结构简单，为它引入 Jinja2（M1 明确"不进 M1 依赖"）不值；等 M3.2 报告页要做复杂布局时再评估。

### 2.9 事件总线与 WS（D24）

```python
class EventBus:
    """进程内 pub/sub：一个 execution 可被多个 WS 连接订阅。"""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, execution_id: int) -> asyncio.Queue: ...
    def unsubscribe(self, execution_id: int, queue: asyncio.Queue) -> None: ...
    def publish(self, execution_id: int, event: str, payload: dict) -> None:
        for queue in self._subscribers.get(execution_id, ()):
            queue.put_nowait({"event": event, "payload": payload, "ts": ...})
```

**背压策略**：每个订阅者队列 `maxsize=200`；满了**丢弃最旧**并计数（`dropped`）。理由：WS 慢客户端不应拖慢执行；丢弃比阻塞好，且丢的事件可从 `GET /executions/{id}` 补齐最终状态。

**事件名（冻结，沿用 M1 §3.4）**：`execution.started` / `case.started` / `step.finished` / `case.finished` / `execution.finished`，M3.1 新增 `step.retried`、`execution.cancelled`。

**JSONL 事件日志**：`{event_log_dir}/execution-{id}.jsonl`，每行 `{"ts","event","payload"}`。作用：WS 断开后仍可回放；也是 GAP-29 的落地。

### 2.10 启动自愈（GAP-31）

```python
async def reconcile_orphans(db) -> int:
    """启动时把残留 RUNNING 的执行置为 ERROR。"""
    result = await db.execute(update(Execution)
        .where(Execution.status.in_(["RUNNING", "PENDING"]))
        .values(status="ERROR", finished_at=now,
                message="进程重启，执行中断"))   # message 列见附录 A
```

> `execution` 表当前**没有** `message` 列 —— 需要加（附录 A）。这是自愈功能的前置。

---

### 2.11 用例集与定时（M3.3）

**四层模型**：`项目 → 用例集 → 用例 → 元素+动作`。用例集是**执行单元**。

| 表 | 关键列 | 说明 |
|---|---|---|
| `test_suite` | `project_id` / `name` / `schedule_cron` / `schedule_enabled` / `last_run_at` / `deleted_seq` | 软删 + `deleted_seq` 保证"删除后能重建同名"（与 element 同一套方案） |
| `test_suite_case` | `suite_id` / `case_id` / `sort` | `UNIQUE(suite_id, case_id)` 防重复加入；`sort` 决定执行顺序 |
| `execution` | `+suite_id` / `+suite_name` | `suite_name` 是**快照**：用例集改名/删除不影响历史报告 |

**三条语义（冻结）**：

1. **不复制步骤**：用例集只存 `case_id`，用例改了，集合跟着变。复制会造成"同一用例两套步骤"。
2. **执行时快照**：`run()` 把 `enabled=1` 的成员展开成 `case_ids` 写进 `execution`。之后改集合不影响这次执行的历史。
3. **只跑启用的成员**：成员有 `enabled` 字段，M3.3 界面暂只做增删，开关接口已就绪。

**调度实现**（D28）：

```python
scheduler = AsyncIOScheduler(timezone=settings.timezone)     # Asia/Shanghai

async def start():
    scheduler.start()
    await reload_all()          # 从 DB 读 schedule_enabled=1 的用例集，重建 job

def sync_suite(suite):          # 新建/修改/删除后调用，幂等
    remove_job(f"suite:{suite.id}")
    if not suite.is_deleted and suite.schedule_enabled and suite.schedule_cron:
        add_job(_trigger, CronTrigger.from_crontab(suite.schedule_cron),
                id=f"suite:{suite.id}", coalesce=True, max_instances=1,
                misfire_grace_time=60)
```

| 参数 | 取值 | 原因 |
|---|---|---|
| cron | **5 段**（分 时 日 月 周） | 团队最熟悉的写法；秒级精度对 UI 回归没意义 |
| 时区 | `UIP_TIMEZONE`，默认 `Asia/Shanghai` | 避免"9 点跑"变成 UTC 9 点 |
| `coalesce` | True | 停机堆积的多次触发只补一次 |
| `max_instances` | 1 | 同一用例集不并发跑 |
| `misfire_grace_time` | 60s | 错过超过 1 分钟就不补，避免启动瞬间雪崩 |

**已知限制**（登记在跟踪清单）：内存 job store → 重启需重建（已实现）；停机超过 60s 的触发不补；"手动 + 定时恰好同时"会产生两个执行，不去重（代价低于引入分布式锁）。

---

## 3. 接口契约

### 3.1 变更与新增

| 方法 | 路径 | 变更 |
|---|---|---|
| POST | `/api/v1/executions` | **200 → 202**；响应 `{id, status:"PENDING", queued_at}` |
| POST | `/api/v1/executions/{id}:cancel` | 新增；`200 {id, status}` |
| GET | `/api/v1/executions/{id}` | 响应增加 `attempt`（步骤结果）、`message`、`queue_position`（PENDING 时） |
| GET | `/api/v1/executions/{id}/report` | 新增；`format=html|json`（默认 html）；未生成 → `409 REPORT_NOT_READY` |
| WS | `/ws/executions/{id}` | 新增；服务端推送事件，客户端只读 |

**M3.3 用例集端点（10 个）**

| 方法 | 路径 | 用途 |
|---|---|---|
| GET/POST | `/api/v1/projects/{pid}/suites` | 列表（带 `case_count`）/ 新建 |
| GET/PATCH/DELETE | `/api/v1/suites/{id}` | 详情（含成员）/ 改（含 cron）/ 软删 |
| GET/POST | `/api/v1/suites/{id}/cases` | 成员列表 / 批量加入（重复跳过、跨项目拒绝） |
| DELETE | `/api/v1/suites/{id}/cases/{case_id}` | 移除成员 |
| PUT | `/api/v1/suites/{id}/cases/order` | 成员排序（全量 id 列表） |
| POST | `/api/v1/suites/{id}:run` | **单次运行 → 202** |
| POST | `/api/v1/executions` | body 增加 `suite_id`（与 `case_ids` 二选一） |

### 3.2 错误码增量

| HTTP | code | 触发 |
|---|---|---|
| 404 | `EXECUTION_NOT_FOUND` | 执行不存在 |
| 409 | `EXECUTION_CANNOT_CANCEL` | 终态执行再取消 |
| 409 | `REPORT_NOT_READY` | 执行未结束或报告未生成 |
| 429 | `QUEUE_FULL` | 待执行数 ≥ `max_pending` |

### 3.3 关键响应

```jsonc
// POST /executions → 202
{ "id": 12, "status": "PENDING", "queued_at": "2026-10-19T16:02:11+08:00" }

// GET /executions/12（RUNNING 中途）
{
  "id": 12, "status": "RUNNING", "total": 1, "passed": 0, "failed": 0,
  "errored": 1, "skipped": 0,
  "cases": [{ "case_id": 1, "title": "登录成功", "steps": [
     { "seq": 4, "action_key": "click", "status": "ERROR", "attempt": 2,
       "duration_ms": 5120, "used_locator_id": 4, "fallback_index": 1,
       "message": "TimeoutError: ..." } ] }]
}

// GET /executions/12/report?format=json → 200
{ "execution": {...}, "cases": [...], "summary": {"pass_rate": 0.0} }
```

---

## 4. 前端设计（M3.1 只改执行页）

| 改动 | 说明 |
|---|---|
| 提交后轮询 | `POST` 拿到 202 → **每 5s** `GET`（D25，≤30s 约束内），直到终态；**不设固定重试次数** |
| 进度条 | `done/total`（已出结果步骤数 / 总步骤数），不做假动画 |
| 取消按钮 | `RUNNING`/`PENDING` 显示；点击调 cancel，按钮进入"取消中…" |
| 报告入口 | 终态后显示「查看报告」，`window.open('/api/v1/executions/{id}/report')` |
| WS（可选） | 保留端点，但**不作为主通道**；前端以轮询为准（D25），WS 留给 M3.2 的实时看板 |
| 批量执行（M3.2） | 多选用例 → 复用 `case_ids` 提交，不新增 `test_suite` 表（§0.2.2） |

> **为什么轮询 5s 而不是 1s**：执行通常 5–20s，5s 的进度感知已经够；1s 在 10 个页面同时看时会放大 5 倍请求量。轮询**不设次数上限**——执行本身有超时、启动有自愈，卡住的执行会被 `reconcile_orphans` 收尾，前端不需要"重试 N 次后放弃"的逻辑。

---

## 5. 测试与验收

| 层 | 覆盖 |
|---|---|
| 单测 | `max_attempts` 三策略；`EventBus` 多订阅与丢弃策略；`report_service` 内容；队列 FIFO/限流（注入 fake runner） |
| 契约测试 | 参数化跑 3 个 adapter：无遗留抽象方法、`capabilities` 每条都有同名方法、未实现/不支持可区分 |
| 集成（真浏览器） | V1–V8 全部按 §1.2 手工或脚本复跑 |
| 回归 | 既有 45 个单测必须全绿（执行链路改动最大，重点看 `test_element_service` / `test_locator_service`） |

**脚本**：`scripts/smoke_m3.py` —— 提交 → 轮询 → 校验终态 → 取报告 → 连 WS 收事件，一条命令出结论。

---

## 6. 对后续的冻结声明

### 6.1 冻结项（M3.1 验收通过后生效）

| # | 冻结内容 | 改它的代价 |
|---|---|---|
| **FR28** | `POST /executions` **202 语义**（提交即返回）；同步模式不再提供 | 前端与所有调用方全改 |
| **FR29** | 执行状态机与终态不可变（INV-1/2） | 历史数据语义失效 |
| **FR30** | 队列为**进程内**、FIFO、并发上限 `UIP_MAX_CONCURRENT_EXECUTIONS`（**D23 已决策，非临时妥协**） | 换 Redis 需重写 worker |
| **FR31** | 启动时 `RUNNING/PENDING → ERROR`（自愈） | 崩溃后数据永久卡住 |
| **FR32** | 重试：`attempt` 逐次落行；`RETRY` 用尽后按 `ABORT` | 结果统计与排查口径变 |
| **FR33** | 取消只在步骤间生效；已跑步骤结果保留 | 语义变"立即中断"需改适配器 |
| **FR34** | `artifact` 必须由执行器落库（适配器只给路径） | 产物无法按步骤追溯 |
| **FR35** | 报告 `format ∈ {HTML, JSON}`，路径落 `report` 表，重复生成幂等 | 前端报告页与导出全改 |
| **FR36** | WS 事件名与载荷（M1 冻结的 5 个 + `step.retried`/`execution.cancelled`） | 推送协议返工 |
| **FR37** | 事件 JSONL 路径 `{event_log_dir}/execution-{id}.jsonl` | 回放工具失效 |
| **FR38** | 4 个新错误码 | 前端分支 |
| **FR39** | 队列满返回 `429 QUEUE_FULL`（**不静默丢任务**） | 用户以为提交成功 |
| **FR40** | **单进程语义**：WS 与队列只在同进程内有效（**D23 已决策**，触发条件见 §0.5） | 多实例部署前必须换 Redis |
| **FR41** | 执行结果轮询：**5s 间隔、不设次数上限**（D25）；轮询只是观察手段，不影响执行 | 前端与验收脚本的等待策略 |
| **FR42** | **不做**鉴权 / 分页 / 通知 / Docker / 多实例（D26）；新增这些需先改范围 | 范围一旦放开，工作量翻倍 |
| **FR43** | ★ 四层模型：`项目 → 用例集 → 用例 → 元素+动作`；**用例集是执行单元**；`execution` 必须存 `suite_id` + `suite_name` 快照 | 报告无法追溯来源；历史报告会被改名影响 |
| **FR44** | 用例集**只存 `case_id`，不复制步骤**；执行时把 `enabled=1` 成员展开成 `case_ids` 快照 | 出现"同一用例两套步骤"的漂移 |
| **FR45** | 定时：APScheduler 内存 job store、5 段 cron、`misfire_grace_time=60s`、启动从 DB 重建 | 换调度器/多实例需重做 |
| **FR46** | ★ `check_exists` **沿回退链逐条判断**（任一命中即存在）；断言不能绕过回退链 | "首选定位符写错、第 2 条可用"的元素会被断言误判为不可见（M3.2 已修） |
| **FR47** | 断言在 `ctx.timeout_ms` 窗口内**轮询**，间隔 `UIP_ASSERT_POLL_INTERVAL_MS`（默认 200ms），**不设固定重试次数**（Q-05） | 改回"固定 N 次"会放大总耗时；改间隔影响误报率 |
| **FR48** | 产物下载**双重校验**：`artifact.execution_id == URL execution_id` + `realpath(path)` 必须在 `artifacts_dir` 内；API 不返回服务器路径 | 越权读文件 |
| **FR49** | 报告链接一律用 `/api/v1/executions/{id}/artifacts/{artifact_id}`；报告 HTML 默认 `Content-Disposition: inline`（`?download=1` 才附件） | 报告页 iframe 与截图预览全挂 |
| **FR50** | `report` 唯一键 `uk_report_execution_format`，生成走 **upsert**（savepoint 兜并发） | 出现重复报告行 |
| **FR51** | 步骤写入口统一校验：动作存在、`params` 匹配 schema、`element_id` 属于同项目、`seq` 不冲突；**新增与修改同一份规则** | 执行时才炸，排查成本几十秒级 |
| **FR52** | `screenshot.target ∈ {page, element}`；`element` 必须绑定元素，`page` 不允许绑定元素 | 元素级截图与页面级语义混淆 |
| **FR53** | **Alembic 是迁移唯一入口**；`sql/schema.sql` 仍是 MySQL DDL 事实源，两者由 `alembic check` 保证一致 | 改表又回到"删库重建" |

### 6.2 M3.2 实现记录（已交付）

**交付清单与落点**（每条都能用命令复核，不是"已完成"三个字）：

| # | 事项 | 对应缺口 | 实现落点 | 自测证据 |
|---|---|---|---|---|
| 1 | 步骤 CRUD + 全量排序 | GAP-19 | `services/case_service.py`、`api/v1/cases.py`（`PATCH/DELETE /cases/{id}`、`GET/POST/PATCH/DELETE /cases/{id}/steps`、`PUT .../order`） | `tests/unit/test_case_service.py` 20 条；`smoke_m32.py` A 段 8/8 |
| 2 | 前端用例编排页（按 schema 生成表单） | GAP-19 / Q-09 | `views/CasesView.vue`、`api/index.ts`、`router` | `smoke_ui.py` `/cases` OK |
| 3 | 报告页（HTML iframe + JSON 视图 + 下载） | GAP-27 | `views/ReportView.vue`、路由 `/executions/:id/report` | `smoke_ui.py` 报告页 OK |
| 4 | 产物列表与下载 | GAP-34 | `services/artifact_service.py`、`GET /executions/{id}/artifacts[/{aid}]` | `tests/unit/test_artifact_service.py` 7 条；`smoke_m32.py` B 段（200 + image/png） |
| 5 | 元素级截图 | GAP-07 | `action_keys.py` 加 `target`；`playwright_adapter.screenshot`；执行器按 `target=element` 解析 chain | `smoke_m32.py` B 段 PASSED |
| 6 | 断言轮询 + 回退链存在性 | GAP-03 | `engines/actions.py::_poll_until`；`playwright_adapter.check_exists` | `test_assert_poll.py` 7 条 + `test_playwright_lookup.py` 5 条；`smoke_m32.py` F 段 |
| 7 | 登录态复用 | GAP-06 | `playwright_adapter.start/stop` 的 `storage_state` / `save_storage_state` | `smoke_m32.py` G 段（文件写出） |
| 8 | Alembic 迁移 | GAP-33 | `backend/alembic.ini`、`alembic/env.py`、`versions/20261019_2f2753e09b0f_initial_schema.py` | `alembic upgrade head` + `alembic check` → "No new upgrade operations detected" |
| 9 | `report` 唯一键 + upsert | GAP-35 | `models.Report.__table_args__`、`schema.sql`、`report_service._upsert` | `test_report_service.py` 2 条；`smoke_m32.py` C 段两分支 |
| 10 | 用例集成员启用开关 | GAP-38 | `suite_service.set_member_enabled`、`PATCH /suites/{id}/cases/{case_id}`、`SuitesView` 勾选框 | `smoke_m32.py` D 段（禁用后不在执行中） |
| 11 | 执行列表按用例集筛选 | GAP-39 | `GET /executions?suite_id=`、`ExecutionsView` 下拉 | `smoke_m32.py` E 段 |
| 12 | 定位符行内编辑 | GAP-26 | `LocatorPanel.vue` 双击/✎ 编辑，保存后状态回 `UNVERIFIED` | 前端构建通过；后端已有 `PATCH /element-locators/{id}` |
| 13 | 前端产物入口 | GAP-34 | `ExecutionsView` 步骤表新增「产物」列 | 截图查看 |

**实现中发现并修掉的真缺陷（不在原计划内）**：

| # | 缺陷 | 影响 | 修法 |
|---|---|---|---|
| **F-M3.2-1** | `PlaywrightAdapter.check_exists` 只查回退链**首条** | 演示数据里「登录按钮」首选定位符是故意写错的 → **所有 `assert_visible` 一律误判失败**；`assert_not_exists` 则相反地永远通过 | 改为沿链逐条 `count()`，任一命中即存在（FR46） |
| **F-M3.2-2** | `element` 表的 `uk_element_name` / 4 个索引**只存在于 `schema.sql`，ORM 里没有** | `create_all` 建的开发库没有唯一约束；"同名元素"只靠应用层检查，并发会漏 | Alembic autogenerate 暴露后补进 `models.Element.__table_args__`（FR53 的直接收益） |
| **F-M3.2-3** | 桩适配器 `screenshot` 缺 `target` 参数 | 调用时 **TypeError 发生在函数体之前**，`_todo` 的 `NotImplementedError` 根本不会抛，违反"待实现 vs 不该实现"的区分 | 桩签名补齐（FR4 约定的具体要求） |
| **F-M3.2-4** | `test_step.output_var` 是**死字段**（只序列化，执行时不生效） | 用户在 StepEditor 里配了输出变量却毫无作用 —— "看起来配了、实际没配" | 执行时若 `params` 无 `output_var` 则注入 `step.output_var` |
| **F-M3.2-5** | `step_result_to_dict` 不含 `id` | 产物按 `step_result_id` 挂靠，前端对不上号 | 返回 `id`（新增字段，向后兼容） |

**明确不在 M3.2**：鉴权、分页、通知、健康度页、Docker（D26）；CI 已于 2026-11-04 由 D40 单独接入（只校验不部署）。

### 6.3 变更流程

与 M1 §6.4 一致：改冻结项 → 本文末「变更记录」留痕 → 回写 D1/M1/M2 对应章节 → 影响历史数据则给迁移。

---

## 附录 A：DDL 增量

```sql
-- 1) 重试次数落行（FR32）
ALTER TABLE `execution_step_result`
  ADD COLUMN `attempt` INT NOT NULL DEFAULT 1
    COMMENT '第几次尝试，从 1 开始' AFTER `status`;

-- 2) 执行级消息（启动自愈 / 取消原因，FR31）
ALTER TABLE `execution`
  ADD COLUMN `message` VARCHAR(512) NULL
    COMMENT '终态原因：进程重启中断 / 用户取消 / 队列满' AFTER `duration_ms`;

-- 3) M3.3 用例集：执行来源快照（FR43）
ALTER TABLE `execution`
  ADD COLUMN `suite_id` BIGINT NULL AFTER `target_id`,
  ADD COLUMN `suite_name` VARCHAR(128) NULL AFTER `suite_id`;

-- 4) M3.3 用例集表（完整定义见 sql/schema.sql）
CREATE TABLE IF NOT EXISTS `test_suite` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `project_id` BIGINT NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `description` VARCHAR(512) NULL,
  `schedule_cron` VARCHAR(64) NULL,
  `schedule_enabled` TINYINT(1) NOT NULL DEFAULT 0,
  `last_run_at` DATETIME NULL,
  `is_deleted` TINYINT(1) NOT NULL DEFAULT 0,
  `deleted_seq` BIGINT NOT NULL DEFAULT 0,
  `deleted_at` DATETIME NULL,
  `created_by` BIGINT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_suite_name` (`project_id`, `name`, `deleted_seq`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `test_suite_case` (
  `id` BIGINT NOT NULL AUTO_INCREMENT,
  `suite_id` BIGINT NOT NULL,
  `case_id` BIGINT NOT NULL,
  `sort` INT NOT NULL DEFAULT 0,
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_suite_case` (`suite_id`, `case_id`),
  KEY `idx_suite_case_case` (`case_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

> 当前项目 `schema.sql` 与 ORM 同步维护；这两列已同时写入 `sql/schema.sql` 的 `CREATE TABLE`，新库无需 ALTER。

## 附录 B：事件清单

| event | payload |
|---|---|
| `execution.started` | `{execution_id, total, platform, engine_key}` |
| `case.started` | `{case_id, title}` |
| `step.finished` | `{case_id, seq, action_key, status, duration_ms, attempt, fallback_index}` |
| `step.retried` | `{case_id, seq, attempt, error}` |
| `case.finished` | `{case_id, status}` |
| `execution.finished` | `{execution_id, status, passed, failed, errored, skipped, duration_ms}` |
| `execution.cancelled` | `{execution_id, at_seq}` |

## 附录 C：文件清单（M3.1）

| 类别 | 文件 | 数量 |
|---|---|---|
| 新服务 | `execution_queue.py` / `event_bus.py` / `report_service.py` | 3 |
| 改动 | `execution_service.py` / `config.py` / `models/__init__.py` / `engines/base.py` / `playwright_adapter.py` / `main.py` / `api/v1/executions.py` / `sql/schema.sql` | 8 |
| 新 API | `api/ws.py` | 1 |
| 测试 | `test_execution_queue.py` / `test_report_service.py` / `test_adapter_contract.py` | 3 |
| 脚本/前端 | `scripts/smoke_m3.py` / `ExecutionsView.vue` | 2 |

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-10-19 | v1.0 初稿：M3 拆 M3.1/M3.2（D19）；冻结 FR28–FR40 | 《待办与缺口跟踪》GAP-01/02/04/05/14/18/29/30/31 + Q-01~Q-10 倾向 |
| 2 | 2026-10-19 | **v1.1 范围收敛**：M3.2 单独交付；不做鉴权/分页/通知/多实例；轮询改 5s 且不限次数（D25/D26/FR41/FR42）；新增 §0.5 Redis 评估 | 用户三条约束（2026-10-19） |
| 3 | 2026-10-19 | **v1.2 新增 M3.3 用例集**：四层模型（D27）、定时调度（D28）、§2.11、10 个端点、FR43–FR45、附录 A 增量 | 用户确认"用例集建实体"；实现与测试已通过 |
| 4 | 2026-10-19 | **v1.3 M3.2 交付**：新增 FR46–FR53（回退链存在性 / 断言轮询 / 产物双重校验 / 报告链接与 inline / report upsert / 步骤写入期校验 / screenshot.target / Alembic 唯一入口）；§6.2 改为实现记录并登记 5 个实现期缺陷；`test_step.output_var` 不再为死字段 | `smoke_m32.py` 24/24；`pytest` 114 passed；`alembic check` 无差异；`smoke_ui.py` 6/6 |
| 5 | 2026-11-04 | **CI 接入（D40）**：§0.2.1 范围表 Docker/CI 拆行，CI 标 ✅（只校验不部署）；§6.2 末尾同步 | 用户要求加 CI 不加 CD；`.github/workflows/ci.yml` 三 job 首跑全绿 |
