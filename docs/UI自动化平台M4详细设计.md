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
| **M4.1** | AppiumAdapter 12 个核心动作 + Android 定位映射 + target options 契约 + 用例固化 demo + 真机验收 | ✅ 已完成（2026-11-08，见 §2–§5） |
| **M4.2** | 剩余 16 个动作（手势 / 滑动 / 上下文 / 生命周期）+ `wait_element` 四态 + 元素级截图 + 执行链路加固（上表清单 + `element_list` 形状对齐） | ✅ 已完成（2026-11-08，见 §7） |
| M4.3 | iOS（macOS/云真机）、uiautomator2 引擎、多设备租约与并发 | 后续 |
| 不做（本批） | 前端设备管理页、视频/trace、设备农场、CD | — |

### 1.3 非目标（明确不做）

- 不做设备池/租约：M4.1 一个 target 对应一台设备，执行串行；并发上限仍由队列 Semaphore 控制。
- 不做 App 安装/卸载：`app_package` 必须已安装在设备上；APK 安装仍未排期（M4.2 也未做）。
- 不做 WebView **内部元素**：`get_contexts/switch_to_context` 已在 M4.2 实现（可列上下文、可切、可切回）；切进 `WEBVIEW_*` 后的元素查找/操作仍未验证（GAP-47，需 debug 包 + WebView 调试）。
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

> M4.2 的验收锚点见 §7.7（真机两个用例集 15/15、9/9 + M4.1 星财富回归 5/5）与 §7.8（五个真机坑的修法）。

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
| `gesture_inset_px` | | 屏高 8%（≥120px） | **M4.2 新增（可选）**：整屏手势的安全区内缩；不内缩会把系统通知栏拉下来 |

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

## 7. M4.2 增补设计（剩余动作 + 上下文）

### 7.1 范围与验收锚点

| 项 | 内容 |
|---|---|
| 目标 | 把 appium 从 12/28 补到 **26 个 Android 可用动作 + 2 个平台不适用**；补 WebView 上下文；修 M4.1 两处欠账（`wait_element(state=hidden)`、`screenshot(target=element)`） |
| 不改 | 动作契约（方法名/keyword）、`params_schema`、64 个 REST 端点、数据模型、`CAPABILITY_MATRIX` 的 28 条声明 |
| 验收 | ① `pytest` 全绿（新增约 18 条）；② `audit_status` 报 **28/28 覆写（2 条平台不适用）**；③ 真机平台执行：一条 15 步「手势 + 上下文」用例 **PASSED**；④ M4.1 星财富用例回归仍 PASSED |

### 7.2 动作映射（Appium 端点 / UiAutomator2 命令）

| 动作 | 实现 | 端点 / 命令 | 关键参数 |
|---|---|---|---|
| `long_press` | 手势 | `mobile: longClickGesture` | `elementId`、`duration`（ms，默认 1000） |
| `double_click` | 手势 | `mobile: doubleClickGesture` | `elementId` |
| `coordinate_click` | 手势 | `mobile: clickGesture` | `x`、`y`（屏幕绝对坐标） |
| `drag` | 手势 | `mobile: dragGesture` | `elementId`（源）+ `endX/endY`（目标元素中心）+ `speed`（由 `duration_ms` 反算） |
| `element_scroll` | 元素内滑动 | `mobile: swipeGesture` | `elementId` + `direction` + `percent`（`distance/元素高度`，clamp 0.05–0.95） |
| `page_swipe` | 整屏滑动 | `mobile: swipeGesture` | 屏幕 `left/top/width/height` + `direction` + `percent`（`distance/屏幕高或宽`） |
| `swipe_up` / `swipe_down` | 整屏滑动特例 | 同上 | `direction=up/down` |
| `multi_finger_swipe` | 双指 W3C actions | `POST /actions`（两 pointer，`pointerType=touch`） | `direction`、`distance`，两指水平错开 120px |
| `scroll_to_element` | 轮询 + 滑屏 | 循环 `swipeGesture` 直到命中或超时 | `ctx.timeout_ms` 为上限，每次滑 40% 屏高，间隔 300ms |
| `background_foreground` | 前后台 | `POST /appium/app/background` → `activate_app` | `seconds`（默认 3） |
| `fix_orientation` | 屏幕方向 | `POST /orientation` | `orientation=PORTRAIT/LANDSCAPE` |
| `get_contexts` | 上下文列表 | `GET /contexts` | `output_var` |
| `switch_to_context` | 切上下文 | `POST /context` | `context`；切换前先校验存在于 `/contexts` |
| `wait_element(state=hidden/detached)` | 等待消失 | 轮询 `_find(timeout_ms=0)` | 超时抛 `TimeoutError`（→ `ERROR`，与 Playwright 语义一致） |
| `screenshot(target=element)` | 元素级截图 | `GET /element/{id}/screenshot` | 需绑定元素 |

**平台不适用（2 条，声明保留在矩阵，方法内明确报错）**：

| 动作 | 原因 | 报错 |
|---|---|---|
| `hover` | 触屏无 pointer hover 语义（Android 手势体系里不存在） | `UnsupportedActionError`，提示改用 `click` / `long_press` |
| `select_option` | Android 原生无 `<select>`/Picker 统一控件（该动作在字典里本就标注 `WEB/IOS`） | `UnsupportedActionError`，提示改用 `click` 展开 + `click` 选项 |

> 为什么保留声明不改矩阵：`CAPABILITY_MATRIX` 是跨平台契约（appium 覆盖 ANDROID + IOS），删除会让 iOS 侧丢能力；且矩阵属冻结契约，不在实现里程碑里改。改由 `audit_status.py` 单列"平台不适用"，避免把"声明了但 Android 用不了"藏起来。

### 7.3 两处行为修正（M4.1 欠账）

| 项 | M4.1 | M4.2 | 理由 |
|---|---|---|---|
| `element_list` 返回形状 | 文本字符串数组 | `[{index, text, visible}]`，上限 200 | 与 Playwright **同形**；不同引擎返回不同形状会让"换引擎用例就崩"，这是跨引擎一致性的硬要求 |
| `wait_element` 的 `state` | 只 `visible`/`attached`，其余报错 | 四个值都支持 | Playwright 一直支持四个值，Web 用例已有用 `hidden` 的写法 |

### 7.4 方向语义（必须先定清，否则用例换个 App 就反了）

| 动作 | `direction` 指什么 | `down` 的实际效果 |
|---|---|---|
| `page_swipe` / `swipe_up` / `swipe_down` / `multi_finger_swipe` | **手指方向** | 手指向上划 |
| `element_scroll` | **内容方向**（与 Web `page_scroll` 一致） | 看到元素内更下方的内容（手指向上划） |

映射在适配器内统一收口（`_gesture_direction()`），用例侧只写业务语义。**方向的实际屏幕效果在真机上核对过**（§7.6），不靠文档推断。

### 7.5 WebView 上下文边界

- 本批实现 `get_contexts` / `switch_to_context`（Android 侧返回 `NATIVE_APP`，若 App 开启 WebView 调试则含 `WEBVIEW_*` / `CHROMIUM`）。
- **切到 WebView 后的元素查找**由 Appium 代理到 chromedriver，前提是被测 App 为 debug 包且开启 WebView 调试；这部分**本批只验证"能列出、能切、能切回"**，WebView 内部元素自动化列为 **GAP-47**（需业务方提供 debug 包与 H5 页面）。
- 上下文不粘滞：每个 `switch_to_context` 都是显式动作，执行器不自动重置（与 Playwright `switch_to_iframe` 栈语义不同，Appium 是全局单上下文）。

### 7.6 测试与真机验收

**单测**（`tests/unit/test_appium_adapter.py` 追加，约 18 条）：每个手势命令的 `mobile: xxx` 名字与参数、`drag` 目标链缺失报错、`element_scroll` percent 计算与 clamp、`multi_finger_swipe` 两个 pointer、`get_contexts` 存变量、`switch_to_context` 校验不存在上下文、`wait_element(hidden)` 命中/超时、`screenshot(element)`、`element_list` 形状、`hover`/`select_option` 报错文案。

**真机验收**（系统设置 App 作沙箱，避免改动星财富自选顺序）：

1. 平台建项目 `Android 手势自检`（`ANDROID` + `appium`，target `app_package=com.android.settings`）；
2. 一条 15 步用例：`restart_app` → `get_contexts` → `switch_to_context(NATIVE_APP)` → `long_press` → `double_click` → `coordinate_click` → `page_swipe(up)` → `swipe_down` → `element_scroll` → `multi_finger_swipe` → `scroll_to_element` → `background_foreground` → `fix_orientation` → `wait_element(hidden)` → `screenshot(element)`；
3. 观察 `PASSED` 与步骤 `used_locator_id` / 产物；
4. 跑 `scripts/demo_android_case.py`（星财富 M4.1 用例）确认无回归。

### 7.7 真机验收结果（2026-11-08，PJA110 / Android 16）

| 用例集 | 执行 | 结果 | 覆盖 |
|---|---|---|---|
| M4.2 手势自检（设置） | #133 / #140 | **15/15 PASSED** | `get_contexts` · `switch_to_context` · `page_swipe` · `swipe_down` · `element_scroll` · `scroll_to_element`（"关于本机" 首屏外）· `element_list` · `multi_finger_swipe` · `wait_element(hidden)` · `background_foreground` · 元素级 + 页面级截图 |
| M4.2 手势自检（计算器） | #134 / #141 | **9/9 PASSED** | `long_press` · `double_click` · `coordinate_click` · `drag` · `fix_orientation` ×2 · 截图 |
| M4.1 星财富回归 | #137/#138 → **#139** | 修复后 **5/5 PASSED**（fallback=1） | `start_app` · 回退链 · 断言 · 截图 |

产物核对：元素级截图 3.5 KB（仅 WLAN 文字），页面级 210 KB —— 证明 `screenshot(target=element)`
真的按元素裁剪，不是整屏。

### 7.8 真机踩坑与加固（这一节是本次最主要的产出）

| # | 现象 | 根因 | 加固 |
|---|---|---|---|
| 1 | 滑动后的步骤全部定位不到元素 | `swipeGesture` 从屏幕最顶部开始，把**系统通知栏**拉了下来（`mCurrentFocus=NotificationShade`） | 整屏手势统一内缩：`_gesture_bounds()` 取屏高 8%（下限 120px），可用 `options.gesture_inset_px` 覆盖 |
| 2 | `fix_orientation` 报 `Screen rotation cannot be changed ... Is it locked?` | ① 系统「自动旋转」关闭；② ColorOS 设置在清单里锁了竖屏 | 错误翻译成人话（提示开自动旋转 / App 锁方向）；验收用例把旋转放在计算器（支持旋转）而非设置 |
| 3 | App 重启后第一步点击**卡 1 分钟以上**，执行永远 RUNNING | `terminate_app`+`activate_app` 后 uiautomator2 的 instrumentation 尚未恢复，单条 `/elements` 会挂到命令超时 | ① `start_app` / `restart_app` 结束后 `_wait_for_package()` 轮询前台包名（≤10s）；② `_find` 每条候选的**单次请求**单独限时 3–8s |
| 4 | 驱动瞬时返回 `500 Could not proxy command`，重试把一步拖到 182s | 重试无上限 + 单条命令无硬上限 | ① 传输层错误连续 3 次即放弃该定位符（`MAX_TRANSIENT_RETRIES`）；② `_request` 加命令级硬上限（read timeout + 10%，最少 +1s）；③ 执行器给**每一步**加硬上限 `max(30s, timeout_ms×2+30s)`，超时记 `ERROR` 并写明"驱动可能卡死" |
| 5 | 星财富冷启动弹全屏开屏广告，控件树只剩广告，"自选" 定位不到 | App 产品行为（关闭按钮无可访问性描述） | 非平台缺陷：演示用例第 1 步改为 `start_app`（热启动）；文档标注跑前先关广告 |

> 有了 #3/#4 两道限时后，同类故障的表现为「20 秒内明确报错」，而不是「执行卡住不动」——
> 这是这次修得最值的一处：**可用的错误信息 > 看起来在跑的假象**。

### 7.9 冻结声明（M4.2）


1. 动作契约、`params_schema`、矩阵 28 条、target options 键**均不变**；
2. 手势统一走 `mobile:` 命令，**不再引入 Appium-Python-Client**（D42 不变）；
3. `element_list` 返回形状以本批为准（`[{index,text,visible}]`），后续引擎必须跟齐；
4. `hover` / `select_option` 在 Android 上**明确不支持**，不得写成"静默成功"；
5. **任一步都必须在有限时间内结束**：适配器层（命令硬上限 + 瞬时错误限次 + 单次请求限时）与执行器层（单步硬上限）**两道保险都不许移除** —— 去掉任何一道，都会回到"执行永远 RUNNING"；
6. `start_app` / `restart_app` 结束后必须等前台包名匹配（`_wait_for_package`），否则第一个动作会撞上 instrumentation 抖动；
7. 不做：多设备并行、App 安装/卸载、视频/trace、WebView 内部元素（GAP-47）、开屏广告自动关闭（产品行为，GAP-48）。

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-11-08 | v1.0：M4.1 平台侧 + AppiumAdapter 12 动作 + 用例固化方案；D42 async httpx | 真机 spike（PJA110/Android 16）；D1a；用户要求"先平台侧、再固化" |
| 2 | 2026-11-08 | v1.1 实现落地：已知 12/28 动作；Activity 全限定名走 `activate_app`；`audit_status.py` 改为按注册表动态加载适配器；真机用例 #125/#126 连续 PASSED、fallback=1 | `pytest` 244 passed + 1 skipped；`audit_status` appium 12/28；平台执行记录 |
| 3 | 2026-11-08 | v1.2：**M4.2 增补设计**（§7）：16 动作映射、2 条平台不适用、`element_list` 形状对齐、`wait_element` 四态、WebView 上下文边界、方向语义收口 | M4.1 遗留清单；`appium-uiautomator2-driver@4.2.9` 实际命令表（`execute-method-map.js`） |
| 4 | 2026-11-08 | v1.3 **M4.2 交付**：16 动作 + 2 平台不适用 + `wait_element` 四态 + 元素级截图 + `element_list` 形状对齐；**新增 §7.7 真机结果 / §7.8 五个真机坑与加固**（手势内缩、旋转错误映射、前台等待、瞬时错误限次、命令/单步硬上限）；演示用例改热启动避开开屏广告 | `pytest` 273 passed + 1 skipped；`audit_status` appium 28/28（2 平台不适用）；真机 #133/#140 15/15、#134/#141 9/9、M4.1 回归 #139 5/5 |
