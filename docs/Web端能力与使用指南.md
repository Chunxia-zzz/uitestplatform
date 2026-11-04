# Web 端能力与使用指南

| 项 | 内容 |
|---|---|
| **适用版本** | M1 骨架 + M2 元素库 + M3 执行内核 / 编排 / 一键接入（2026-10-19） |
| **结论口径** | 本文所有"支持/不支持"均以代码为准，核验命令写在每条后面 |
| **配套文档** | D2-M1（适配层）· D2-M2（元素库）· D2-M3（执行）· D2-M3.4（一键接入） |

---

## 1. 结论：Web 端适配是否完成？

**分三个口径回答，不混为一谈：**

| 口径 | 结论 | 依据 |
|---|---|---|
| **动作层**（引擎能做的事） | ✅ **完成** | `python scripts/audit_status.py` → `[playwright] 声明 28 个动作 · 真实现 28 · 仅继承默认 0`，且签名全部符合"方法名 == action_key、参数名 == schema 属性名"的冻结约定 |
| **执行链路**（跑一条用例需要的配套） | ✅ **完成** | 等待/断言/截图/日志/并发/登录态/弹窗/iframe/多标签/文件上传 逐项有实现（§2.3） |
| **能力面**（专业测试工具的进阶能力） | 🟡 **覆盖主链，有明确边界** | 下载、网络拦截、trace/video、shadow DOM 未实现（§3），均已登记在《待办与缺口跟踪》 |

一句话：**日常 Web 功能测试（页面跳转、表单、点击、列表、断言、截图、并发跑批）已经可以完整跑通；需要"网络 mock / 失败过程回放 / Shadow DOM"的场景暂不支持。**

---

## 2. 覆盖范围

### 2.1 动作：37 个可用（28 引擎动作 + 9 平台内建）

> 星号 `*` 表示平台内建（不经过引擎，任何端都能用）。

| 分类 | 数量 | 动作 |
|---|---|---|
| **ELEMENT** | 14 | `click` `input` `get_text` `get_attribute` `wait_element` `check_exists` `hover` `select_option` `double_click` `scroll_to_element` `drag` `coordinate_click` `upload_file` `element_list` |
| **NAVIGATION** | 7 | `navigate` `go_back` `go_forward` `refresh` `switch_to_iframe` `switch_to_page` `page_scroll` |
| **ASSERT** | 5 | `assert_equals`\* `assert_contains`\* `assert_matches`\* `assert_visible`\* `assert_not_exists`\* |
| **DATA** | 3 | `set_variable`\* `eval_expression`\* `db_query`\* |
| **SYSTEM** | 8 | `screenshot` `get_url` `get_title` `get_cookies` `set_cookies` `delete_cookies` `accept_dialog` `run_python`\* |

其中 `run_python` **默认禁用**（`UIP_ALLOW_RUN_PYTHON=false`），需要显式配置才开。

### 2.2 定位：11 种语义类型

```
testid · css · xpath · id · class · text · role · label · placeholder · title · alt
```

- **语义层与引擎语汇层分离**：库里只存 `testid`，翻译成 `[data-testid="..."]` 由适配器负责。
  换引擎时定位数据不用改。
- **回退链**：同一元素同一端可配多条定位符，按 `priority` 依次尝试；执行结果记录
  `used_locator_id` 与 `fallback_index`（第几条命中）。
- 核验：`GET /api/v1/locator-types` → `platforms.WEB.types`。

### 2.3 执行链路

| 能力 | 实现方式 | 关键细节 |
|---|---|---|
| **等待** | `wait_element`（state + timeout）、断言轮询、回退链分段时间 | 回退链每条候选最多 2.5s，**最后一条**才用满 `timeout_ms`；断言在 `timeout_ms` 窗口内轮询（默认 200ms 一次，不设固定重试次数） |
| **页面就绪** | `navigate` 的 `wait_until` | `commit / domcontentloaded / load / networkidle`；默认 `domcontentloaded`，一键接入场景默认 `load` |
| **断言** | 5 种：相等 / 包含 / 正则 / 可见 / 不存在 | 断言失败记 `FAILED`，引擎异常记 `ERROR`，**两者分开统计** |
| **截图** | 页面级 + 元素级 | `screenshot(target="page"｜"element")`；产物落 `artifact` 表，可按执行下载 |
| **日志** | 结构化 JSON 日志 + 事件 JSONL + WebSocket | 每个执行一个 `events/execution-{id}.jsonl`；请求级 `trace_id` 回写响应头与错误体 |
| **并发** | 进程内 FIFO 队列 + `Semaphore` | 默认并发 2（`UIP_MAX_CONCURRENT_EXECUTIONS`），队列上限 200，满了返回 429 不静默丢弃 |
| **失败重试** | `on_failure=RETRY` + `retry_times` | 每次尝试落一行 `execution_step_result`，`attempt` 递增 |
| **取消** | `POST /executions/{id}:cancel` | 只在**步骤之间**生效（不强杀浏览器，避免半截会话） |
| **登录态复用** | `execution_target.options` 的 `storage_state` / `save_storage_state` | 执行前读、执行结束写回；文件不存在只告警不报错 |
| **弹窗** | `accept_dialog` | dialog handler 在会话启动时**预注册**（否则页面永久阻塞） |
| **iframe** | `switch_to_iframe` 单动作 + 栈语义 | 带 `index` 进入、不带参数弹出；支持嵌套 |
| **多标签** | `switch_to_page(index)` | 切换后清空 frame 栈 |
| **文件上传** | `upload_file(file_path)` | 走 `set_input_files` |
| **Cookie** | `get_cookies` / `set_cookies` / `delete_cookies` | — |
| **报告** | HTML（人看）+ JSON（机器读） | 执行结束自动生成；`report` 表按 `(execution_id, format)` 唯一 |

---

## 3. 已知限制（刻意的或尚未实现的）

| # | 限制 | 说明 / 替代方案 | 状态 |
|---|---|---|---|
| 1 | **无下载处理** | 没有 `expect_download`，导出类功能测不了 | ⏸ 顺延（GAP-10） |
| 2 | **无网络拦截 / mock / 等特定响应** | 不能 `page.route`，也不能"等到某个 XHR 返回"；异步页面建议用 `wait_element` + `networkidle` 兜 | ⏸ 顺延（GAP-09） |
| 3 | **无 trace / video / HAR** | 失败现场只有截图 + 步骤消息，不能回放 | ⏸ 顺延（GAP-08） |
| 4 | **无 Shadow DOM 穿透** | 封闭 shadow root 内的元素定位不到 | 未排期 |
| 5 | **iframe 只能按 index 进** | 不能按元素/URL 定位 iframe；动态顺序的页面需要先 `switch_to_page` 或改结构 | ⏸ 顺延（GAP-12） |
| 6 | **无元素拾取器** | 定位符必须手工录入或由输入提供（D14 决策）；有"一键验证"但没有"页面点选" | 设计决策，非缺陷 |
| 7 | **移动浏览器不是独立端** | `WEB` + `execution_target.options.device`（如 iPhone 15 仿真）；不设 `WAP` 端（D5） | 设计决策 |
| 8 | **Appium / uiautomator2 只有桩** | 建 Android/iOS 项目能建，但执行会抛 `NotImplementedError` | M4 |
| 9 | **单进程执行** | 进程重启会丢排队任务（启动自愈把残留置 `ERROR`）；WS 只在同进程有效 | D23 决策 |
| 10 | **SQLite 不做 ENUM 强约束** | 生产建议 MySQL 8 + `sql/schema.sql` | 环境约束 |

> 完整清单与核验命令见 [`待办与缺口跟踪.md`](./待办与缺口跟踪.md)。

---

## 4. 如何写一个 Web 用例

三条路，按"从快到可控"排序。**三者最终落的是同一套数据**（项目 / 元素 / 用例 / 用例集）。

### 4.1 方式 A：元素扫描（先扫后确认，定位符零手工）

打开 `/scan`：选项目 → 填 URL → 「开始扫描」→ 候选表（强/中/弱分级，默认勾强/中）
→ 可改名/删定位符 → 「导入选中」→ 元素库落库。

**扫描不落库**；只有导入才写。适合"给一个新页面快速建元素库"。

### 4.2 方式 A2：快速接入（最快，30 秒）

打开 `http://localhost:5173/scaffold`：

1. 网页地址填目标页 URL（如 `http://127.0.0.1:8899/todo.html`）
2. 填项目 code（幂等键）、项目名、用例标题、用例集名
3. 「添加动作」，每个动作选动作类型；需要元素的动作会展开"元素名 + 定位符"（可加多条形成回退链）
4. 点「生成并运行」→ 结果面板给出完整 id 链，可直接跳执行结果/报告

也可以直接调 API（同一份数据）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/scaffold \
  -H "Content-Type: application/json" \
  -d @payload.json
```

请求体结构见 D2-M3.4 §3.2；可运行示例见 `scripts/demo_web_case.py`。

### 4.3 方式 B：元素库 + 用例编排（逐步可控）

1. **元素库**（`/elements`）：建元素 → 加定位符（可多条）→ 点「验证当前端」确认命中
2. **用例编排**（`/cases`）：新建用例 → 添加步骤 → 绑定元素 / 填参数 → 调 seq
3. **用例集**（`/suites`）：新建用例集 → 加入用例 → 点「运行」

适合需要长期维护、反复修改的用例。

### 4.4 方式 C：纯 API（可进 Git，适合 CI）

```bash
# 1) 建项目
POST /api/v1/projects            {"name":"...","code":"...","platform":"WEB","engine_key":"playwright"}
# 2) 建元素
POST /api/v1/projects/{id}/elements   {"parent_id":0,"element_name":"添加按钮","node_type":"ELEMENT"}
# 3) 加定位符
POST /api/v1/elements/{id}/locators   {"platform":"WEB","engine_key":"playwright","locator_type":"testid","locator_value":"add"}
# 4) 建用例 + 步骤
POST /api/v1/projects/{id}/cases      {"title":"待办增删"}
POST /api/v1/cases/{id}/steps         {"action_key":"click","element_id":12,"params":{}}
# 5) 建用例集 + 加成员 + 运行
POST /api/v1/projects/{id}/suites     {"name":"冒烟"}
POST /api/v1/suites/{id}/cases        {"case_ids":[3]}
POST /api/v1/suites/{id}:run
```

### 4.5 完整示例：待办清单（11 步）

页面：`backend/fixtures/web/todo.html`（输入框 `testid=new-todo`、按钮 `testid=add`、计数 `testid=count`、列表项 `css=li[data-testid="todo-item"]`）。

| # | 动作 | 元素 | 参数 | 断言什么 |
|---|---|---|---|---|
| 1 | `navigate` | — | `url=/todo.html`、`wait_until=load` | 页面打开 |
| 2 | `input` | 新待办输入框 | `text=买牛奶` | — |
| 3 | `click` | 添加按钮 | — | — |
| 4 | `assert_visible` | 第一条待办 | — | 列表里出现了项 |
| 5 | `input` | 新待办输入框 | `text=写周报`、`clear=true` | — |
| 6 | `click` | 添加按钮 | — | — |
| 7 | `get_text` | 待办计数 | `output_var=count_text` | — |
| 8 | `assert_equals` | — | `actual=${count_text}`、`expected=2` | 计数变成 2 |
| 9 | `click` | 第一条的删除按钮 | — | — |
| 10 | `get_text` | 待办计数 | `output_var=count_after` | — |
| 11 | `assert_equals` | — | `actual=${count_after}`、`expected=1` | 删除后计数回到 1 |

要点：

- **变量语法** `${name}` 或 `{{ name }}`，作用域是**用例内**；变量缺失时保留原样（不会静默变空串）。
- **多命中**：`assert_visible` 只判断"存在"（任一候选定位符 `count > 0`）；`click` / `input` 取该定位符的**第一个**匹配元素并等待其可见。要点列表第 N 项时，用更精确的 CSS（如 `li:nth-of-type(2) button`）或 xpath；`element_list` 只能读快照，不负责"按索引点击"。
- **回退链**：同一元素可配 `testid` + `css` 两条，第一条错会自动试第二条，结果里 `fallback_index=1`。

---

## 5. 在本地唤起并执行

### 5.1 前置条件

| 项 | 要求 | 检查命令 |
|---|---|---|
| Python 环境 | 项目内 venv 已建、依赖已装 | `.venv/Scripts/python.exe -c "import fastapi, playwright"` |
| 浏览器 | Playwright Chromium 已装 | `.venv/Scripts/python.exe -m playwright install chromium` |
| 后端 | 8000 端口 | `curl http://127.0.0.1:8000/healthz` → `{"status":"ok"}` |
| 被测页面 | 有可访问的 URL；本地可用 fixture | `curl http://127.0.0.1:8899/todo.html` → 200 |
| 数据库 | 默认 SQLite，无需安装 | `backend/data/uitest.db` |

一键起环境：

```powershell
cd F:\jerryyang-uitestplatform
.\scripts\setup.ps1        # 首次：建 venv、装依赖、装 Chromium、装 npm 包
.\scripts\dev.ps1          # 起后端(8000) + 前端(5173)
# 另开一个终端，起 fixture 静态站（演示页面）
cd backend; ..\.venv\Scripts\python.exe ..\scripts\serve_fixtures.py
```

### 5.2 三种执行方式

**① 界面**：`/scaffold` 点「生成并运行」，或 `/suites` 点「运行」，或 `/executions` 选批次。

**② 一条命令（推荐先跑这个验证环境）**：

```bash
cd F:/jerryyang-uitestplatform
.venv/Scripts/python.exe scripts/demo_web_case.py
```

它会建好 Todo 项目/元素/用例/用例集并执行，打印每一步的状态与耗时。

**③ 直接调执行接口**（已有用例集时）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/suites/1:run   # 返回 202 + execution id
curl http://127.0.0.1:8000/api/v1/executions/1           # 轮询到终态
```

执行是**异步**的：`POST` 立即返回 `202`，实际执行在后台队列里。

### 5.3 预期结果

一条成功执行应当满足：

| 观察点 | 期望值 |
|---|---|
| `execution.status` | `PASSED` |
| `passed / failed / errored / skipped` | `1 / 0 / 0 / 0`（单用例单步骤时按实际） |
| 每个步骤 `status` | `PASSED` |
| `duration_ms` | > 0（导航步通常几十到几百毫秒） |
| `used_locator_id` | 命中定位符时有值 |
| `fallback_index` | 首选命中为 `0`；回退命中为 `1,2...` |
| 报告 | `GET /executions/{id}/report` 返回 200，抬头显示用例集名 |

失败时的语义区分（很重要，别混）：

- **`FAILED`**：断言不成立（页面行为不符合预期）—— 这是"测出了问题"。
- **`ERROR`**：引擎层面异常（定位不到、超时、元素不可交互）—— 这是"测试本身有问题或环境有问题"。

### 5.4 执行通知（飞书 / 企微）

执行到终态后可以推一条消息到群里。渠道由环境变量单选，**默认企微**；用飞书就切 `channel`，不需要改代码：

| 环境变量 | 说明 |
|---|---|
| `UIP_NOTIFY_CHANNEL` | `wecom`（默认）/ `feishu` |
| `UIP_NOTIFY_WECOM_WEBHOOK` | 企微群机器人 webhook；留空 = 该渠道禁用 |
| `UIP_NOTIFY_FEISHU_WEBHOOK` | 飞书自定义机器人 webhook；留空 = 该渠道禁用 |
| `UIP_NOTIFY_FEISHU_KEYWORD` | 飞书机器人「自定义关键词」，默认 `UI自动化平台`，会写进卡片标题 |
| `UIP_NOTIFY_ON` | `none` / `failure`（默认，FAILED+ERROR 才推）/ `all` |
| `UIP_PUBLIC_BASE_URL` | 平台前端地址；非空时卡片带「查看报告」按钮 |

先自测一条（同步返回，失败会直接告诉你原因）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/notifications:test \
  -H 'Content-Type: application/json' -d '{}'
# 200: {"sent":true,"channel":"feishu","webhook":"https://open.feishu.cn/open-apis/bot/v2/hook/9f2c***"}
```

注意两点：

- 飞书机器人若开了「自定义关键词」，消息标题必须包含关键词，否则飞书返回 `19024 Key Words Not Found`，平台侧表现为 `502 NOTIFY_SEND_FAILED`；
- 推送是 **fire-and-forget**：超时/网络错误只记日志 `event=notify.failed`，**不会改变执行终态**（D39）。webhook 属凭据，只写 `backend/.env`（已 gitignore），响应与日志均掩码。

---

## 6. 排错对照表

| 现象 / 错误码 | 大概率原因 | 怎么查 |
|---|---|---|
| `LOCATOR_NOT_FOUND` | 元素在该端没有可用定位符 | 元素库看 `coverage.WEB` 是否为 0 |
| 步骤 `ERROR: 元素 N 的全部 M 条定位符均未命中` | 定位符写错 / 页面没加载完 | 用元素库「验证当前端」逐条看命中数 |
| `VALIDATION_ERROR`（写步骤时） | 动作参数不符合 schema / 需要元素却没绑 | 看错误体 `error.detail` |
| `SCAFFOLD_ELEMENT_REQUIRED` | 动作需要元素但没给 `element_key` | 该动作 `requires_element=true` |
| `SCAFFOLD_UNKNOWN_ELEMENT_KEY` | 动作引用了未声明的元素 key | 检查请求里 `elements[].key` |
| `ARTIFACT_PATH_FORBIDDEN` | 产物路径不在 `artifacts_dir` 内 | 检查 `UIP_ARTIFACTS_DIR` 是否改过 |
| 执行一直 `PENDING` | 队列满 / worker 未启动 | `healthz` 看 `queue_pending`；重启后端 |
| 执行变 `ERROR` 且 message 含"进程重启" | 后端在执行中被重启 | 启动自愈的预期行为，重跑即可 |
| 页面弹窗导致卡死 | 未用 `accept_dialog` 预注册策略 | 加一步 `accept_dialog`，或让被测页面别在首屏弹 |

---

## 7. 怎么确认这份结论没过期

```bash
cd backend
../.venv/Scripts/python.exe -m pytest -q                 # 134 passed
../.venv/Scripts/python.exe -m app.cli doctor            # 字典/矩阵/注册表一致性
cd ..
.venv/Scripts/python.exe scripts/audit_status.py         # 声明 vs 实现
.venv/Scripts/python.exe scripts/demo_web_case.py        # 真实浏览器跑一条 11 步用例
```

四项都通过，说明本文的"已完成"仍然成立。任何一项变化，都应该先改本文再改结论。
