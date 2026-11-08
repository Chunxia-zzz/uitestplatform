# UI 自动化平台 M4 详细设计 · Android / Appium（平台侧 + 用例固化）

| 项 | 内容 |
|---|---|
| **版本** | v1.0（2026-11-08） |
| **范围** | M4.1：Android 真机平台侧能力 + 用例固化；不含 iOS / WebView / 手势全集 |
| **依据** | 《移动端对接方案》D1a；M1 适配器冻结约定 FR4/FR15；M3 执行链；真机 spike（PJA110 / Android 16 / `3149dfe3`） |
| **决策** | **D42**：AppiumAdapter 用 **async httpx 直连 Appium REST**（不复用同步的 Appium-Python-Client）；理由：① 适配器本身是 async；② `trust_env=False` 可绕开 `HTTP_PROXY` 代理 localhost 的坑（本次实测）；③ 不新增 selenium 依赖 |

---

## 1. 目标、范围与验收

### 1.1 目标

1. **平台能独立跑 Android 用例**：后端 + Appium Server + 真机即可，不依赖前端页面。
2. **对外可调用**：全部能力通过现有 REST API 暴露（OpenAPI `/docs`），外部脚本/CI 可直接调用。
3. **用例可固化**：项目 → 执行目标 → 元素/定位符 → 用例/步骤 → 用例集 → 执行/报告，全部落库、可重复执行。
4. **与 Web 同一套模型**：不新增表、不新增 API、不改执行链；只加一个 `AppiumAdapter`。

### 1.2 分期

| 阶段 | 内容 | 状态 |
|---|---|---|
| **M4.1（本批）** | AppiumAdapter 12 个核心动作 + Android 定位映射 + target options 契约 + 用例固化 demo + 真机验收 | 本批交付 |
| M4.2 | 剩余动作：`long_press` / `double_click` / `drag` / `coordinate_click` / `element_scroll` / `page_swipe` / `multi_finger_swipe` / `swipe_up/down` / `scroll_to_element` / `element_list` / `background_foreground` / `fix_orientation` / `get_contexts` / `switch_to_context` | 后续 |
| M4.3 | iOS（macOS/云真机）、uiautomator2 引擎、多设备租约与并发 | 后续 |
| 不做（本批） | 前端设备管理页、视频/trace、设备农场、CD | — |

### 1.3 非目标（明确不做）

- 不做设备池/租约：M4.1 一个 target 对应一台设备，执行串行；并发上限仍由队列 Semaphore 控制。
- 不做 App 安装/卸载：`app_package` 必须已安装在设备上；APK 安装留到 M4.2。
- 不做 WebView：`get_contexts/switch_to_context` 归 M4.2。
- 不做 iOS：`platform=IOS` 在 `start()` 时明确报"需 macOS/云真机（M4.3）"。

### 1.4 验收锚点

| # | 场景 | 预期 |
|---|---|---|
| V1 | 创建 `ANDROID + appium` 项目与 target（options 含 udid/app_package） | 201；GET 回读 options 一致 |
| V2 | 真机建 Appium 会话 | 成功，`session_id` 非空，caps 含 `deviceModel/platformVersion` |
| V3 | 用例固化：5 步写入后重新 GET | 步骤数/顺序/绑定元素/参数完全一致 |
| V4 | 平台执行该用例 | 终态 `PASSED`，5/5 步 `PASSED` |
| V5 | 回退链：首选 `resource_id` 故意写错、第二条 `text` 命中 | 步骤 PASSED 且 `fallback_index=1` |
| V6 | 截图产物 | artifact 落库，API 可下载，报告内可见 |
| V7 | 复用：同一 suite 再跑一次 | 不新增元素/用例；第二次仍 PASSED |
| V8 | 报告 | 含 `platform=ANDROID`、`engine=appium`、步骤明细与 fallback |
| V9 | 回归 | `pytest` 全绿；`lint-imports` 2 kept；CI 三 job 绿 |

---

## 2. 平台侧设计

### 2.1 平台现有能力与 M4.1 增量

| 能力 | 现有接口 | M4.1 是否需要改 |
|---|---|---|
| 项目管理（platform/engine 路由） | `POST/GET/PATCH/DELETE /projects` | 否（ANDROID 早已支持） |
| 执行目标（设备/App 配置载体） | `POST/GET/PATCH/DELETE /execution-targets` | 否（options 是 JSON，加参数不改表） |
| 元素树 | `/projects/{id}/elements` | 否 |
| 定位符（platform × engine + priority） | `/elements/{id}/locators` | 否（ANDROID 字典已就绪） |
| 用例 / 步骤 | `/projects/{id}/cases`、`/cases/{id}/steps` | 否 |
| 用例集 / 执行 / 报告 | `/suites`、`/executions`、`/reports` | 否 |
| **引擎执行** | `AppiumAdapter`（桩） | **是：本批实现** |

**结论**：M4.1 的平台侧"新增能力"只有一个——把 Appium 桩换成真适配器。所有接口沿用，外部调用方式不变。

### 2.2 `execution_target.options` 契约（Android + appium）

| 键 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `udid` | ✅ | — | `adb devices` 的序列号，如 `3149dfe3` |
| `app_package` | ✅ | — | 被测 App 包名，如 `com.fosunhani.stock.debug` |
| `appium_url` | | `http://127.0.0.1:4723` | Appium Server 地址（兼容别名 `appiumServer`） |
| `app_activity` | | 自动解析 launcher | 启动 Activity，如 `.enter.activity.LauncherActivity` |
| `device_name` | | 同 `udid` | Appium `deviceName` |
| `platform_version` | | 设备自报 | 如 `16` |
| `no_reset` | | `true` | 不清 App 数据 |
| `new_command_timeout` | | `180` | 会话空闲超时（秒） |
| `auto_grant_permissions` | | `true` | 自动授权运行时权限 |
| `adb_exec_timeout` | | `60000` | adb 执行超时（毫秒） |

> 缺 `udid` 或 `app_package` → 执行在 `start()` 阶段报 `ValidationFailed`，错误消息直接指出缺哪个键；不会静默连错设备。

### 2.3 AppiumAdapter 设计

```text
start(config)  → POST /session（caps 见上）→ 保存 session_id
stop()         → DELETE /session/{id}；幂等
click/input/get_text/get_attribute/wait_element/check_exists
               → _find(chain)（回退链）→ 元素命令
start_app/stop_app/restart_app/go_home
               → activate_app / terminate_app / press_keycode
screenshot     → GET /screenshot（base64）→ 落盘 + ctx.artifacts
probe_locator  → 逐条计数（诊断，不进动作字典）
```

**回退链语义**（与 Playwright 完全一致）：每条候选最多等 `min(timeout_ms, 2500)`，最后一条用满；命中发 `locator.hit`（含 `locator_id`/`fallback_index`），未命中发 `locator.miss`。执行器已有的 `used_locator_id`/`fallback_index` 埋点直接复用。

**定位映射（语义层 → Appium 语汇）**：

| 语义 `locator_type` | Appium `using` | Appium `value` |
|---|---|---|
| `resource_id` | `id` | 原值 |
| `accessibility_id` | `accessibility id` | 原值 |
| `text` | `-android uiautomator` | `new UiSelector().text("<escaped>")` |
| `text_contains` | `-android uiautomator` | `new UiSelector().textContains("<escaped>")` |
| `class_name` | `class name` | 原值 |
| `xpath` | `xpath` | 原值 |
| `uiautomator` | `-android uiautomator` | 原样传入（逃生口） |

**异常语义**：找不到元素 → `LocatorNotFoundError`（步骤 `FAILED` 还是 `ERROR` 由执行器既有规则决定）；Appium 4xx/5xx、会话失效 → `RuntimeError`（`ERROR`）。

**Activity 归一化（实现期修正）**：`app_activity` 允许全限定名或相对名；`start_app` 只在相对名（`.Xxx`）时走 `start_activity`，全限定名统一走 `activate_app`。原因：debug 包的 Activity 命名空间可能与包名不同（如 `com.fosunhani.stock.debug` 的 Activity 是 `com.fosunhani.stock.*`），Appium 会再拼一次 `appPackage`，报 "never started"。

### 2.4 M4.1 实现的 12 个动作

`click` · `input` · `get_text` · `get_attribute` · `wait_element` · `check_exists` · `element_list` · `screenshot` · `start_app` · `stop_app` · `restart_app` · `go_home`

其余 17 个声明动作继续走基类 `_not_supported()`：**声明支持但未实现 → `NotImplementedError`**（工作量可追踪，符合 FR15）。

### 2.5 文件清单

| 文件 | 动作 |
|---|---|
| `backend/app/engines/adapters/appium_adapter.py` | 新增：异步 Appium 客户端 + 适配器 |
| `backend/app/domain/capabilities.py` | `ENGINES[appium].implemented=True` + adapter_path 指向新文件 |
| `backend/tests/unit/test_appium_adapter.py` | 新增：caps / 定位映射 / 回退链 / 元素命令 / 截图 / 生命周期 |
| `scripts/demo_android_case.py` | 新增：纯 REST 固化星财富用例并执行 |
| `docs/UI自动化平台M4详细设计.md` | 本文档 |

---

## 3. 接口契约（复用现有 64 个操作，无新增端点）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/projects` | 建项目（`platform=ANDROID, engine_key=appium`） |
| POST | `/api/v1/projects/{pid}/execution-targets` | 建设备目标（options 见 §2.2） |
| PATCH | `/api/v1/projects/{pid}` | 把 `target_id` 绑到项目 |
| POST | `/api/v1/projects/{pid}/elements` | 建元素（树节点） |
| POST | `/api/v1/elements/{eid}/locators` | 加定位符（platform×engine×priority） |
| POST | `/api/v1/projects/{pid}/cases` | 建用例 |
| POST | `/api/v1/cases/{cid}/steps` | 加步骤 |
| POST | `/api/v1/projects/{pid}/suites` | 建用例集 |
| POST | `/api/v1/suites/{sid}/cases` | 加成员（只存 case_id） |
| POST | `/api/v1/executions` | 提交执行（202） |
| GET | `/api/v1/executions/{id}` | 轮询终态/步骤 |
| GET | `/api/v1/executions/{id}/report?format=json\|html` | 报告 |
| GET | `/openapi.json` / `/docs` | 外部调用契约 |

**错误契约**：沿用统一信封 `{"error": {code, message, detail, trace_id}}`；M4.1 不新增错误码。

---

## 4. 用例固化方案（核心）

### 4.1 数据模型（已有，不新增表）

```text
project (platform=ANDROID, engine_key=appium, target_id)
  └─ execution_target (options: udid/app_package/...)
  └─ element (纯树, parent_id/path)
       └─ element_locator (platform × engine_key, priority 回退链)
  └─ case
       └─ test_step (seq, action_key, element_id?, params, timeout_ms, retry...)
  └─ test_suite ──(只存 case_id，不复制步骤)──> case
  └─ execution (快照: suite_id/suite_name + 展开的 case_ids)
       └─ execution_step_result (used_locator_id/fallback_index/artifact)
       └─ report (HTML + JSON)
```

### 4.2 固化流程（7 步，全部 REST）

1. **建项目**：`POST /projects` `{name, code, platform:"ANDROID", engine_key:"appium"}`
2. **建设备目标**：`POST /projects/{pid}/execution-targets`
   `{name, platform:"ANDROID", engine_key:"appium", options:{udid, app_package, app_activity, ...}}`；再 `PATCH /projects/{pid}` 绑 `target_id`
3. **建元素**（树）：`POST /projects/{pid}/elements`
   `{parent_id:0, element_name:"自选 Tab", node_type:"ELEMENT"}`
4. **加定位符**：`POST /elements/{eid}/locators`
   `{platform:"ANDROID", engine_key:"appium", locator_type:"text", locator_value:"自选", priority:10}`
5. **建用例**：`POST /projects/{pid}/cases` `{title:"星财富 · 自选→个股详情"}`
6. **写步骤**：`POST /cases/{cid}/steps`
   `{seq, action_key, element_id?, params, timeout_ms?, retry_times?, on_failure?}`
   —— `seq` 可省略，后端自动追加；`action_key` 必须来自 51 条动作字典
7. **建用例集并运行**：`POST /projects/{pid}/suites` → `POST /suites/{sid}/cases {case_ids:[cid]}` → `POST /suites/{sid}:run`（或 `POST /executions {project_id, case_ids}`）

### 4.3 各层参数说明

| 层 | 关键参数 | 说明 |
|---|---|---|
| project | `platform`、`engine_key` | 两者必须匹配（ANDROID → appium/u2） |
| target | `options.udid`、`options.app_package` | 设备与 App 的唯一入口；换设备只改 target |
| element | `element_name`、`parent_id`、`node_type` | 纯树任意层级；`ELEMENT` 才能绑步骤 |
| locator | `locator_type`、`locator_value`、`priority` | 语义层类型；同元素可挂多引擎/多候选 |
| case | `title` | 用例是步骤容器，不含执行配置 |
| step | `action_key`、`element_id`、`params`、`timeout_ms` | 参数名必须匹配 `params_schema`；`requires_element` 的动作必须绑定元素 |
| suite | `name`、`schedule_cron` | 用例集是执行单元；成员只存 `case_id` |
| execution | `project_id` + `case_ids`/`suite_id` | 202 入队；执行时展开 `enabled=1` 成员 |

### 4.4 保存与复用规则

1. **元素/定位符复用**：同一项目内元素按 `element_name`（同级）唯一；定位符按 `(platform, engine_key, type, value)` 去重。用例步骤只引用 `element_id`，改定位符不需要改用例。
2. **用例复用**：用例不复制步骤；一个用例可加入多个用例集。用例集成员只存 `case_id`，执行时才展开。
3. **执行快照**：`execution` 保存 `suite_id/suite_name` 与当时的 `case_ids` 快照；之后改用例集成员不影响历史执行。
4. **重新固化**：demo 脚本按 `project.code` / `target.name` / `element_name` / `case.title` 查找，存在则复用，不重复创建；步骤只在用例为空时写入（避免翻倍）。
5. **跨引擎复用**：同一元素可同时挂 `appium` 与 `uiautomator2` 的定位符；切项目 `engine_key` 自动选对应语汇，`*` 通配兜底。

### 4.5 星财富固化示例（本批真机验收用例）

| seq | action_key | 元素 | params | 预期 |
|---|---|---|---|---|
| 1 | `restart_app` | — | `{}`（用 target 的 app_package） | App 回到主界面 |
| 2 | `click` | 自选 Tab（`text=自选`） | `{}` | 切到自选页 |
| 3 | `click` | 标普500ETF-SPDR 行（`text=标普500ETF-SPDR`） | `{}` | 进入个股详情 |
| 4 | `assert_visible` | 详情标题（`text_contains=标普500ETF-SPDR`） | `{}` | 断言通过 |
| 5 | `screenshot` | — | `{"target":"page"}` | 产物落库 |

**回退链验收**：把第 2 步元素的 `resource_id` 候选（故意错）设为 priority 10，`text=自选` 设为 20；执行后 `fallback_index=1`。

### 4.6 外部调用方式

- **同步脚本**：`scripts/demo_android_case.py`（本批新增，纯 httpx，不依赖前端）。
- **curl**：见 README「M4 Android 用例固化」小节。
- **CI/其他系统**：直接调 REST；OpenAPI 见 `/docs`。所有接口无鉴权（D26 内网定位），调用方需自备网络隔离。

---

## 5. 测试与验收

### 5.1 单元测试（`tests/unit/test_appium_adapter.py`，约 10 条）

| # | 用例 |
|---|---|
| 1 | caps 构造：options → W3C caps；默认值正确 |
| 2 | 缺 `udid` / `app_package` → `ValidationFailed` |
| 3 | 7 种定位类型映射正确（含转义） |
| 4 | 回退链：首条空、第二条命中 → `fallback_index=1` + `locator.hit` |
| 5 | 全部未命中 → `LocatorNotFoundError` |
| 6 | `check_exists` 返回 False 不抛 |
| 7 | `click` 调用正确元素端点 |
| 8 | `start_app` 用 target 的 app_package |
| 9 | `screenshot` 落盘 + `ctx.artifacts` 登记 |
| 10 | `stop()` 删除会话且幂等 |

### 5.2 真机验收（本批必跑）

1. 起 Appium Server + 后端；
2. `python scripts/demo_android_case.py` → 5/5 步 PASSED；
3. 看报告：`fallback_index`、截图、`platform/engine`；
4. 再跑一次 → 仍 PASSED，元素/用例不重复。

### 5.3 回归

- `pytest -q`（新增约 10 条）；
- `lint-imports` 2 kept；
- Web 冒烟不受影响（`smoke_m3` 17/17 可选复跑）；
- CI backend job 绿。

---

## 6. 对后续的冻结声明

1. **动作契约不变**：方法名 == `action_key`、关键字参数 == `params_schema`；M4.2 只新增方法，不改签名。
2. **target options 键冻结**：`udid` / `app_package` / `appium_url` / `app_activity` / `device_name` / `platform_version` / `no_reset` / `new_command_timeout` / `auto_grant_permissions` / `adb_exec_timeout`；新增只能加键，不能改名。
3. **定位映射冻结**：§2.3 表；新增 Android 语义类型必须同时更新 `locator_types.py` 与本表。
4. **M4.1 边界**：仅 Android；iOS 明确报错；手势/WebView/element_list 归 M4.2。
5. **异常语义**：找不到元素 `LocatorNotFoundError`；协议/会话错误 `RuntimeError`；不得把两者混为一种。
6. **不做**：设备池、并发租约、App 安装、视频/trace（M4.2+）。

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-11-08 | v1.0：M4.1 平台侧 + AppiumAdapter 12 动作 + 用例固化方案；D42 async httpx | 真机 spike（PJA110/Android 16）；D1a；用户要求"先平台侧、再固化" |
| 2 | 2026-11-08 | v1.1 实现落地：已知 12/28 动作；Activity 全限定名走 `activate_app`；`audit_status.py` 改为按注册表动态加载适配器；真机用例 #125/#126 连续 PASSED、fallback=1 | `pytest` 244 passed + 1 skipped；`audit_status` appium 12/28；平台执行记录 |
