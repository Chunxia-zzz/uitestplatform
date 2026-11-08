# 新会话交接指南（HANDOVER）

> **任何新的 AI 会话接手本项目，先把本文件完整读一遍再动手。**
> 本文件是跨会话的"记忆锚点"：当前状态、铁律、环境坑、待决策事项都在这里。
> 维护规则：每批次收尾时更新本文件的「当前状态」与「下一步」。

---

## 1. 项目是什么（30 秒版）

- **多引擎 UI 自动化平台**：小型测试团队内部使用（非 SaaS、单机单实例）。
- **主链**：项目 → 用例集 → 用例 → 元素+动作 → 按端路由引擎执行 → 报告。
- **端**：`WEB`（Playwright，28/28 动作全实现）；`ANDROID` / `IOS`（**桩**，M4 实现——用户已冻结：Web 端验收通过后再启动）。
- 技术栈：FastAPI + SQLAlchemy async + Alembic + APScheduler + Playwright（python）+ Vue 3/Vite/TS（无 UI 组件库）。
- 代码仓库：`F:\jerryyang-uitestplatform`（monorepo：docs/ + backend/ + frontend/ + scripts/）。
- GitHub：https://github.com/Chunxia-zzz/uitestplatform （main 分支，Apache-2.0 LICENSE）。

## 2. 当前状态快照（截至 2026-11-08）

| 维度 | 状态 |
|---|---|
| 里程碑 | **M1 / M2 / M3.1 / M3.2 / M3.3 / M3.4 / M3.5 / M3.6 / M3.7 全部完成**；**M4.1（Android/Appium 平台侧 + 用例固化）已完成**（11 份施工图） |
| 规模 | 64 API 操作 · 51 条动作字典 · 13 张表 · 50 个错误码 · 8 个前端页 |
| 质量基线 | `pytest` **244 passed + 1 skipped**（MySQL 集成按 env 门控）；五份冒烟 **113 项全绿**（m3 17 · m32 24 · m34 30 · m35 15 · m36 27）；`smoke_ui` 11/11；`lint-imports` 2 kept；`alembic check` 无差异 |
| CI | **GitHub Actions 三个 job 全绿**（backend / frontend / e2e），红灯与 `needs` 跳过已实测；`.github/workflows/ci.yml` + 本地同源 `scripts/ci_local.sh`；**无 CD**（D40） |
| Android | **真机 PJA110（Android 16 / `3149dfe3`）已跑通平台用例**：执行 #125/#126 PASSED，5 步含回退链 `fallback_index=1` 与截图产物；`appium` 已实现 12/28 动作（M4.2 补剩余） |
| 验收 | 《docs/验收评估报告.md》结论"可进入验收"；**2026-11-02 已自动复跑全部证据并修 2 处**（/scan 文本列表头与折行、m36 V12 空转）→ 只剩用户手工走查 §5.1 手感项 |
| 验收前审计 | 已做过两轮：2026-10-20 修 1 个竞态；2026-11-02 修扫描表头 + 修正 V12 验收脚本 |

## 3. 铁律（违反 = 返工）

1. **文档先行、代码后写**：每个批次先出增量设计文档（含语义决策 + 文件级任务列表），用户确认后再动代码。
2. **事实以代码为准**：确认任何功能状态，必须以真实代码文件或可执行命令输出为依据，禁止凭文档推断。
3. **冻结契约不可破坏**：动作字典 51 条、CAPABILITY_MATRIX、FR1–FR58；只允许新增；改冻结项必须走变更流程并在文档「变更记录」留痕。
4. **改表必须走 Alembic**（`revision --autogenerate` + `upgrade head`），**禁止删库重建**；`alembic check` 是模型↔迁移一致性唯一判据；`schema.sql` 同步更新（MySQL DDL 事实源）。
5. **统一错误信封**：新错误码 = `core/errors.py` 加类 **且同步文件底部汇总列表**；新 router 必须在 `api/v1/__init__.py` 注册。
6. **FR34**：artifact 只由执行器落库，适配器只产出文件/路径。
7. **每批次收尾**：回填《docs/待办与缺口跟踪.md》（每条 GAP 状态附证据命令）→ 更新 README → `pytest` 全绿 → commit + push。
8. D26 范围外不做：鉴权、分页、通知管理 UI、多实例/Redis、WS 鉴权、Docker/CD（**CI 已由 D40 放行：只校验不部署**）。

## 4. 环境与命令速查（Windows / git-bash）

| 用途 | 命令 |
|---|---|
| venv Python | `F:/jerryyang-uitestplatform/.venv/Scripts/python.exe` |
| 全量测试 | `cd /f/jerryyang-uitestplatform/backend && ../.venv/Scripts/python.exe -m pytest -q` |
| 分层红线 | `../.venv/Scripts/lint-imports.exe`（预期 2 kept） |
| 迁移一致性 | `../.venv/Scripts/alembic.exe check`（开发库已 stamp，改模型先 `revision --autogenerate`） |
| 后端启动 | `cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`（后台运行） |
| fixture 静态站 | `.venv/Scripts/python.exe scripts/serve_fixtures.py`（8899，含 login/locators/multi-hit/todo） |
| 前端 dev | `cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`（**必须带 `--strictPort`**：5173 处于 TIME_WAIT 时 vite 会静默换到 5174，导致走查/冒烟打空） |
| 杀端口 | PowerShell：`Get-NetTCPConnection -LocalPort 8000 -State Listen` → `Stop-Process -Id $_ -Force` |
| 冒烟验收 | `scripts/smoke_m3.py`(17) · `smoke_m32.py`(24) · `smoke_m34.py`(30) · `smoke_m35.py`(15) · `smoke_m36.py --phase <full\|off\|bad\|offdiag\|nostub>`(27)——m36 各阶段需按脚本头部注释切 env 重启后端 |
| 本地 CI 同源检查 | `bash scripts/ci_local.sh`（pytest + lint-imports + 全新库 alembic check + 前端 build；加 `--with-e2e` 需 8000/8899 已起） |
| 演示用例 | `scripts/demo_web_case.py`（11 步 Todo 全链路） |
| 能力自检 | `scripts/audit_status.py`（声明 vs 实现 + FR4 签名核对） |
| Android 用例固化 | `NO_PROXY=127.0.0.1,localhost python scripts/demo_android_case.py`（前置：Appium 4723 + 真机 + 后端 8000） |

### ⚠️ Git 推送（本机特殊网络，最容易踩的坑）

**沙箱代理（127.0.0.1:50644）与机器直连都无法访问 github.com**；唯一可用通道是本机代理客户端 **127.0.0.1:7890**（系统代理开关显示 off 但端口在监听）。推送命令（需真实网络环境执行）：

```bash
cd /f/jerryyang-uitestplatform
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
  git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push
```

凭据走 Git Credential Manager（已授权过）。若 7890 未监听，说明代理客户端没开——请用户先打开它。

## 5. 文档地图（按问题找文档）

| 要解决什么 | 读哪份 |
|---|---|
| 项目为什么这样选型 | `UI自动化平台技术选型报告.md`（D0，含参照项目实测纠错） |
| 整体架构 / 数据模型 / 路由设计 | `UI自动化平台技术方案.md`（D1；**注意**：其中 Redis 表述已过时，实际按 D23/D26 用进程内队列，待更新） |
| App 端怎么接（M4 蓝本） | `UI自动化平台移动端对接方案.md`（D1a，含 WebView 上下文栈） |
| 某个里程碑的实现细节与冻结契约 | `UI自动化平台M{1,2,3,3.4,3.5,3.6}详细设计.md`（各文档 §6 为冻结声明，文末有变更记录） |
| 现在能做什么 / 怎么写用例 | `Web端能力与使用指南.md` |
| 未完成事项与待确认事项的唯一清单 | `待办与缺口跟踪.md`（42+ 条 GAP / 13 条 Q，每条带核验命令——**改状态必须附证据**） |
| 能不能验收 / 怎么验收 | `验收评估报告.md`（2026-10-20，含逐项核对表与操作指引） |
| 一次 URL 抓取评估的来龙去脉 | `URL抓取导入能力评估.md`（催生了 M3.5） |

## 6. 关键决策索引（详文在各设计文档）

| 决策 | 内容 | 出处 |
|---|---|---|
| D1–D6 | 从零自建（只借鉴架构）/ FastAPI / 一期仅 Web / 完整方案 / monorepo / 动作英文 snake_case | 技术方案 §0 |
| D5 | 端只有 `WEB/ANDROID/IOS`，不设 WAP（移动浏览器 = target 仿真） | 技术方案 |
| D11/D12 | `run_python` 保留但默认禁用；`switch_to_iframe` 单动作栈语义 | M1 |
| D14→D28 | 不做交互式拾取器；放开"按 URL 批量扫描 + 人工确认落库" | M3.5 |
| D19/D25/D26 | M3 拆批；轮询 5s 不限次数；平台管理功能削减清单 | M3 |
| D27/D28(M3.3) | 四层模型（用例集）；APScheduler 内存 job store | M3 |
| D23/Q-08 | 进程内队列，不引入 Redis（触发重评条件见 M3 §0.5） | M3 |
| D29–D39 | target 软删语义 / 通知门控 / trace 默认 on-failure / 诊断两段式等 | M3.6 §1.3 |
| **D40** | **接入 GitHub Actions CI（只校验不部署）：backend / frontend / e2e 三 job；D26 的「不做 CI」就此收窄为「不做 CD」** | 2026-11-04 用户要求；`.github/workflows/ci.yml` |
| **D41** | **通知渠道单选 `UIP_NOTIFY_CHANNEL=wecom\|feishu`（默认 wecom）；飞书走 interactive 卡片，标题带自定义关键词；不做多渠道并行/管理 UI** | 2026-11-04；M3.7 详细设计；GAP-43 |
| **D42** | **AppiumAdapter 用 async httpx 直连 Appium REST（`trust_env=False`），不引入同步 Appium-Python-Client；M4.1 只做 Android + 12 个核心动作** | 2026-11-08；M4 详细设计；真机联调实测 |

## 7. 实现踩坑 Top 10（真金白银的教训，勿重蹈）

1. **SQLite 上 BIGINT 主键不自增** → 必须 `BigInteger().with_variant(Integer, "sqlite")`。
2. **步骤间变量必须每个用例一份 `ActionContext.variables`**，否则 `${var}` 变字面量、断言静默失败。
3. **回退链每条候选只等 `min(总超时, 2.5s)`、末条用满**——否则首选写错要白等 15s。
4. **`check_exists` 必须沿回退链逐条判断**（M3.2 修复）：只查首条会让"首选错、回退可用"的元素被断言误判。
5. **诊断产物登记必须在终态 commit 之前**（M3.6 验收审计修复的竞态）：video/HAR 由 context close 落盘且文件名随机 → 两段式 finalize→close_all→目录扫描。
6. **fire-and-forget 通知**：外层 async 内 `create_task + wait_for + 全异常吞掉`；调用处 await 外层只等门控同步逻辑——直接"不 await"协程不会执行。
7. **服务内函数名会遮蔽 sqlalchemy**（如 `update` → 改 `sa_update`）；MySQL 整文件 skip 用 `pytestmark = pytest.mark.skipif(..., allow_module_level=True)`。
8. **不要 `session.expire_all()`**（批量 UPDATE 后会 MissingGreenlet）；改就地同步 ORM 对象。
9. **纯字符串判断的函数不要写成 async**（如 `move_guard`），否则漏 await 循环检测静默失效。
10. **前端字段名必须核对后端响应**（`/actions` 返回 `action_key` 不是 `key`，写错不报错只是静默显示错）。

完整 22 条见 WorkBuddy 工作区记忆；以上是跨会话最贵的 10 条。

## 8. 待用户决策（新会话不要擅自定）

| # | 事项 | 背景 |
|---|---|---|
| 1 | **生产库选型**：SQLite（现状）vs MySQL 8（D1 原定） | 选 MySQL → 部署时切 `UIP_DATABASE_URL` + 跑 GAP-25；选 SQLite → 改判 GAP-25 不适用 + 更新 D1 |
| 2 | **「执行目标管理」前端页**要不要排期 | 现状：target/trace/video/har 只能 env 或 API 配置，无页面 |
| 3 | **M4.2 手势/WebView 排期** | M4.1 只做 12/28 动作；手势、context 切换、元素级截图归 M4.2 |

## 9. 下一步开发优先级（依赖序）

```
1. M4.2：Appium 剩余 16 动作（手势/滑动/列表/context）+ 元素级截图
2. M4.3：iOS（macOS/云真机）、uiautomator2 引擎、多设备租约
3. GAP-09/10/12/13（网络拦截 / 下载 / iframe 按元素 / 执行级变量）
4. D3 工程约定（目录/命名/错误码/Git 流程/测试规范）
5. GAP-25 MySQL 集成测试（代码已就绪，skip 门控）                      ← 随决策 #1
```

## 10. 已知限制（对用户如实交代过的）

- trace/video/HAR 无页面配置；通知支持企微 / 飞书单选（D41），仍无管理 UI；
- **Android 仅 M4.1**：Appium 12/28 动作（无手势 / WebView / 元素级截图）、单设备串行、iOS 未实现（M4.2/M4.3）；
- 无下载处理、网络拦截、trace 之外没有 Shadow DOM 穿透、iframe 只能按 index；
- 单机单进程语义：重启丢排队任务（启动自愈置 ERROR）、WS 仅同进程（前端有 5s 轮询兜底）；
- `schema.sql` 是 MySQL DDL，SQLite 下 ENUM 无 DB 级强校验。

---

*本文件由 2026-11-01 会话创建。维护者：每批次收尾的 AI 会话。*
