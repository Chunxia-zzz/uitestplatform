# UI 自动化平台 · 移动端对接方案（Android / iOS / WebView）

| 项 | 内容 |
|---|---|
| 文档版本 | v1.0（预留方案） |
| 编写日期 | 2026-10-14 |
| **文档性质** | ⚠️ **预留对接方案 —— 当前不实现**。一期（M1–M3）只做 Web，本文档的作用是：① 确保一期实现**不挡住**二期；② 二期启动时**无需重新调研** |
| 上游文档 | 《UI自动化平台技术方案.md》（决策 D3：一期仅 Web；决策 D5：端类型仅 `WEB`/`ANDROID`/`IOS`）·《UI自动化平台技术选型报告.md》附录 B（调试环境）、附录 C（二次验证） |
| 覆盖范围 | Android（Appium / uiautomator2）· iOS（Appium + XCUITest）· 混合应用 WebView 接棒 |
| 不覆盖 | 设备农场/云测平台选型采购、真机机型矩阵、CI 集成、App 安装与签名管理 |

---

## 0. 本文档怎么用

```
一期（M1–M3，已规划）          二期（本文档，不着急实现）
─────────────────────         ──────────────────────────────
Playwright 适配器  ✅           ┌─ M5  Android · Appium + AVD
Appium 适配器      ⛔ 桩        ├─ M6  Android · 双引擎 + 设备并发
UIAutomator2 适配器 ⛔ 桩        └─ M7  iOS 云真机 + WebView 接棒
```

**本文档不要求一期做任何移动端工作**，但**要求一期做对 10 件事**（见 **§6**）—— 这 10 条是"现在顺手做、二期省一个月；现在不做、二期要返工"的分界线。其中 **§6 的第 7 条（`SessionManager` 不得为单例）** 是唯一会造成架构级返工的一条，优先级最高。

---

## 1. 移动端接入总览

### 1.1 端 / 引擎 / 适配器矩阵

| 端 `platform` | 引擎 `engine_key` | 适配器类 | 定位 | 一期 |
|---|---|---|---|---|
| `ANDROID` | `appium` | `AppiumAdapter` | 能力全（含 WebView context、多指手势、悬停） | ⛔ 桩 |
| `ANDROID` | `uiautomator2` | `UiAutomator2Adapter` | 轻、快、需 adb；纯原生场景 | ⛔ 桩 |
| `IOS` | `appium` | `AppiumAdapter` | iOS 唯一解（XCUITest / WDA） | ⛔ 桩 |
| `WEB`（App 内 WebView，二期） | `playwright` | `PlaywrightAdapter`（复用） | 通过 CDP 接管 WebView | ✅ 已实现，二期只加 `attach_to_cdp()` |

> **关键**：移动端接入**不新增端类型**（D5），只是在已有的三个 `platform` 上补齐引擎实现。这正是"新增引擎 = 加一个文件 + 注册"这条设计命题的兑现点。

### 1.2 二期要做的事（概览）

| 层 | 改动 | 是否改一期已有代码 |
|---|---|---|
| 数据 | `execution_target.options` 填入设备 caps | ❌ 不需改结构（JSON） |
| 数据 | `element_locator` 增加 `ANDROID`/`IOS` 行 | ❌ 只是新增数据 |
| 数据 | （建议一期预留）`execution_step_result.active_platform/active_engine` | ❌ 一期已加可空列 |
| 代码 | 新增 `appium_adapter.py` / `uiautomator2_adapter.py` 实现 | ❌ 新增文件 |
| 代码 | `capabilities.py` 增加两个引擎的集合 | 🟡 追加（启动强校验会防漏） |
| 代码 | `adapters/__init__.py` 两行注册 | ❌ 已在桩中注册 |
| 代码 | `SessionManager` 支持多 adapter 实例 | ⚠️ **可能改**，取决于一期设计（§6-7） |
| 代码 | 新增 `attach_webview` / `detach_webview` 两个动作 | 🟡 追加动作 + 上下文栈 |
| 前端 | 无（StepEditor 由 `action_catalog` 驱动） | ❌ 不需改 |
| 环境 | Android SDK / AVD / Appium Server / adb | — 纯环境 |
| 环境 | iOS：云真机账号 或 一台 Mac | — 纯环境 |

---

## 2. Android 对接方案

### 2.1 引擎选择：Appium 还是 uiautomator2

| 维度 | **Appium**（`appium`） | **uiautomator2**（`uiautomator2`） |
|---|---|---|
| 实现方式 | Appium Server（HTTP，默认 `:4723`）+ W3C WebDriver | Python 直连设备（adb + atx-agent） |
| 定位语汇 | `id` / `accessibility id` / `xpath` / `-android uiautomator` / `class name` | `resourceId` / `description` / `text` / `xpath` / `className` |
| WebView 上下文 | ✅ `driver.contexts` / `switch_to_context` | ❌ 不支持 |
| 多指手势 | ✅ W3C `actions` | ⚠️ 需绕过 u2 封装 |
| 悬停 / 下拉选择 | ✅ | ❌ |
| 启动开销 | 较高（Server + WDA 类握手） | 低（直连） |
| 稳定性 | 成熟，社区大 | 够用，但封装层薄 |
| 并发 | 多 Server 端口 / 多设备 | 多设备天然支持 |
| 依赖 | JDK + Node + Appium 2.x + driver | Python + adb |

**建议**：
- **M5 先只做 Appium** —— 能力全、与 iOS 共用同一个适配器类，一份代码覆盖两端；
- **M6 再加 uiautomator2** —— 目的是**验证 P2（Locator 的 engine 维度）真的有效**（同一 Android 元素用两套定位语汇都能命中）。这是把"架构正确性"变成"可验收事实"的最好方式。

> ⚠️ 若团队只想维护一套 Android 定位符，**M6 可以不做**，但 `element_locator.engine_key` 这个维度仍必须保留（它同样服务于 WebView 场景与未来的第三引擎）。

### 2.2 环境搭建（Windows 开发机）

| 步骤 | 内容 | 要点 |
|---|---|---|
| 1 | **JDK 17 LTS** | Appium 2.x 与其 Android driver 依赖 |
| 2 | **Android SDK + Platform Tools** | 提供 `adb`、`emulator`；`ANDROID_HOME` 配好 |
| 3 | **AVD 模拟器** | ⚠️ 必须 **x86_64 镜像**（ARM 镜像在 Windows 上慢到不可用）<br>⚠️ 开 **WHPX**（Windows Hypervisor Platform）或 AEHD 加速<br>⚠️ 选 **Google APIs** 镜像，**不要** Google Play 镜像（无法 root，调试受限）<br>建议 API 33/34，内存 ≥ 4 GB / AVD |
| 4 | **Appium Server 2.x** | `npm i -g appium` → `appium driver install uiautomator2` |
| 5 | **uiautomator2（Python）** | `pip install uiautomator2` → `python -m uiautomator2 init`（会向设备推 atx-agent） |
| 6 | 验证 | `adb devices` 能看到 `emulator-5554`；`appium driver list --installed` 有 `uiautomator2` |

> Android 模拟器已足够覆盖"弹窗 / 按钮 / 表单 / 导航"类需求（选型报告附录 B.3）。**真机不是二期的前置条件**，只在遇到厂商 ROM 定制行为、真实性能、推送/内购时才有必要。

### 2.3 `AppiumAdapter` 实现清单

实现 `EngineAdapter`（技术方案 §4.2）的全部必需方法与 Android 可选方法：

| 方法 | 实现要点 |
|---|---|
| `create(options)` | 用 `options` 构造 `AppiumOptions`；**不在此处连 Server**（延迟到 `start()`） |
| `start()` | `webdriver.Remote(options.appiumServer, options=caps)`；幂等（已启动则直接返回） |
| `stop()` | `driver.quit()`；可安全重复调用（捕获 `SessionNotCreated`/`InvalidSessionId`） |
| `session_id` | `driver.session_id` |
| `click` / `input` / `get_text` / `get_attribute` / `wait_element` / `check_exists` | 统一收 `LocatorChain`，走 `_find_chain()`（见 §2.5） |
| `hover` / `select_option` / `double_click` / `long_press` / `drag` / `coordinate_click` | Appium `ActionChains` / `TouchAction` |
| `page_swipe` / `multi_finger_swipe` | W3C `actions`，多指需构造多个 pointer |
| `scroll_to_element` | `mobile: scroll` 或 `UiScrollable` |
| `screenshot` | `driver.get_screenshot_as_file(path)` |
| `start_app` / `stop_app` / `restart_app` / `background_foreground` | `activate_app` / `terminate_app` / `background_app` |
| `go_back` / `go_home` | `driver.back()` / `press_keycode(3)` |
| `get_contexts` / `switch_to_context` | `driver.contexts` / `driver.switch_to.context(name)` ← **WebView 基础，见 §4** |

**与 rd 源码的对照**（只作实现参考，不复制）：rd 的 `AppiumMethod` 已覆盖上述大部分动作；本方案的差异是**统一签名 + 统一异常 + 回退链**，而非方法逐个重写。

### 2.4 `UiAutomator2Adapter` 实现清单

| 方法 | 实现要点 |
|---|---|
| `start()` | `u2.connect(serial)`（`serial` 来自 `execution_target.options`，如 `127.0.0.1:21503`） |
| `stop()` | `d.service("uiautomator").stop()`；**不卸载 atx-agent** |
| `click` / `input` / `get_text` / `get_attribute` / `wait_element` / `check_exists` | 用 `d(**{locator_type: value})` 构造选择器；同样走 `_find_chain()` |
| `long_press` | `d(...).long_click()` |
| `page_swipe` / `swipe_up` / `swipe_down` | `d.swipe_ext(direction, scale)` |
| `element_list` | `d(**kwargs)` 返回多元素 |
| `scroll_to_element` | `d(scrollable=True).scroll.to(**selector)` |
| `start_app` / `stop_app` | `d.app_start(pkg, activity)` / `d.app_stop(pkg)` |
| `screenshot` | `d.screenshot(path)` |
| `fix_orientation` | `d.set_orientation()` |
| **`hover` / `select_option` / `multi_finger_swipe` / `get_contexts` / `switch_to_context`** | ❌ **不实现，继承基类的 `UnsupportedActionError`** |

> 这一行的"不实现"必须在 `CAPABILITY_MATRIX["uiautomator2"]` 中**同步不声明**，否则启动一致性自检会失败（技术方案 §4.3）。这正是 P3 的用意：**能力缺失是显式契约，不是运行时惊喜**。

### 2.5 ANDROID 定位类型字典与两引擎语汇映射 ★

本方案在 `element_locator.locator_type` 中采用的**引擎无关命名**，及各适配器的翻译：

| 语义 | 本方案 `locator_type` | → Appium 实际传参 | → uiautomator2 实际传参 |
|---|---|---|---|
| 资源 ID | `resource_id` | `-android uiautomator`, `new UiSelector().resourceId("X")` | `resourceId`, `"X"` |
| 无障碍 ID / content-desc | `accessibility_id` | `accessibility id`, `"X"` | `description`, `"X"` |
| 精确文本 | `text` | `-android uiautomator`, `new UiSelector().text("X")` | `text`, `"X"` |
| 包含文本 | `text_contains` | `-android uiautomator`, `new UiSelector().textContains("X")` | `textContains`, `"X"` |
| 类名 | `class_name` | `class name`, `"X"` | `className`, `"X"` |
| XPath | `xpath` | `xpath`, `"X"` | `xpath`, `"X"` |
| 原生选择器串（逃生口） | `uiautomator` | `-android uiautomator`, 原样传入 | ❌ 不支持 |

**回退链示例**（元素「登录按钮」，`platform=ANDROID`）：

| engine_key | locator_type | locator_value | priority |
|---|---|---|---|
| `appium` | `accessibility_id` | `loginButton` | 10 |
| `appium` | `resource_id` | `com.demo.app:id/btn_login` | 50 |
| `appium` | `text` | `登录` | 100 |
| `uiautomator2` | `resource_id` | `com.demo.app:id/btn_login` | 10 |
| `uiautomator2` | `text` | `登录` | 100 |
| `*` | `text` | `登录` | 200 |

→ 切 `engine_key` 时自动选到对应的定位语汇；`*` 通配兜底。**这就是技术方案 §3.2.4 那张表在移动端的完整用法。**

### 2.6 caps 构造（`execution_target.options` → `AppiumOptions`）

```jsonc
// execution_target: "Pixel7-API34-AVD"  (platform=ANDROID, engine_key=appium)
{
  "platformName": "Android",
  "platformVersion": "14",
  "deviceName": "emulator-5554",
  "udid": "emulator-5554",
  "automationName": "UiAutomator2",
  "appiumServer": "http://127.0.0.1:4723",
  "app": "D:/apps/demo-debug.apk",      // 或省略，改用 appPackage/appActivity
  "appPackage": "com.demo.app",
  "appActivity": ".MainActivity",
  "noReset": true,
  "newCommandTimeout": 120,
  "autoGrantPermissions": true,
  "adbExecTimeout": 60000
}
```

> 与一期一致：`options` 是 JSON，**加设备参数不改表结构**。Appium 侧 `autoGrantPermissions` / `newCommandTimeout` 这类"必须写、否则踩坑"的参数，建议在 `AppiumAdapter.create()` 里给默认值，只允许 `options` 覆盖。

### 2.7 设备管理

| 事项 | 做法 |
|---|---|
| 设备标识 | `execution_target.options.udid`；AVD 用 `emulator-5554` 这类序列号 |
| 多设备并发 | **并发上限 = 可用设备数**，不能用 `project.threads` 直接控制（技术方案 §6.3 已注明此约束） |
| 设备占用 | `SessionManager` 维护设备租约（`execution_target_id` → 占用中），无空闲设备时排队而非报错 |
| 断连恢复 | `start()` 前 `adb devices` 自检；失败则重试一次并标记 `execution_target` 为 `unhealthy` |
| 多 AVD | 单机可开 2–4 个 AVD（视内存）；这正是选型报告提到的"引擎注册到任意机器"（流马设计）的用武之地（二期不做，登记为待办） |

### 2.8 动作映射速查（统一 `action_key` → 两引擎）

| `action_key` | Appium | uiautomator2 |
|---|---|---|
| `click` | `el.click()` | `d(...).click()` |
| `input` | `el.send_keys(text)` | `d(...).set_text(text)` |
| `get_text` | `el.text` | `d(...).get_text()` |
| `get_attribute` | `el.get_attribute(name)` | `d(...).info[name]` |
| `wait_element` | `WebDriverWait(...).until(EC.presence_of_element_located)` | `d(...).wait(timeout)` |
| `check_exists` | `find_elements(...)` 非空 | `d(...).exists` |
| `long_press` | `ActionChains(driver).click_and_hold().pause().release()` | `d(...).long_click()` |
| `scroll_to_element` | `mobile: scroll` / `UiScrollable` | `d(scrollable=True).scroll.to(**sel)` |
| `page_swipe` | W3C `actions` / `mobile: swipe` | `d.swipe_ext(direction, scale)` |
| `multi_finger_swipe` | W3C 多 pointer | ❌ 不支持 |
| `start_app` | `driver.activate_app(pkg)` | `d.app_start(pkg, activity)` |
| `stop_app` | `driver.terminate_app(pkg)` | `d.app_stop(pkg)` |
| `screenshot` | `driver.get_screenshot_as_file(p)` | `d.screenshot(p)` |
| `get_contexts` | `driver.contexts` | ❌ 不支持 |
| `switch_to_context` | `driver.switch_to.context(name)` | ❌ 不支持 |

### 2.9 M5 / M6 验收标准

**M5（Android · Appium）**
1. 一个 `platform=ANDROID, engine_key=appium` 的项目，在 AVD 上跑通 ≥ 8 步用例（启动 App → 输入 → 点击 → 断言文本 → 截图）；
2. `execution_step_result.active_platform/active_engine` 正确记录为 `ANDROID`/`appium`；
3. 失败截图与 page source 落到 `artifact` 表；
4. 把首选定位符改错，验证回退到第 2 条且 `fallback_index=1`。

**M6（Android · 双引擎）**
1. **同一条用例**在 `engine_key=appium` 与 `uiautomator2` 下**都能跑通**（定位符分别命中各自行）→ 这是 P2 有效性的**决定性证据**；
2. 用 u2 项目选一个 `get_contexts` 动作，验证**前置校验就拦下**（而不是运行时 AttributeError）；
3. 两台 AVD 并发执行，设备租约正确（无抢占、无串扰）。

---

## 3. iOS 对接方案

### 3.1 硬约束（无法绕过）

| 事实 | 影响 |
|---|---|
| **iOS 模拟器是 Xcode 的组成部分** | 模拟器**只能在 macOS 上运行**，Windows 无法跑 iOS 模拟器 |
| **XCUITest driver 需要 WebDriverAgent（WDA）** | WDA 必须用 Xcode **编译并在设备上首次安装** |
| 开发机是 **Windows** | 无法本机完成 WDA 的编译与首装 |

> 结论：**"完全不需要任何 Mac"目前不成立；"不需要 Mac 常驻"成立。**

### 3.2 三条可行路径

| 方案 | 做法 | 成本 | 适用 | 推荐度 |
|---|---|---|---|---|
| **A · 云真机** | BrowserStack App Automate / Kobiton / LambdaTest 等；Windows 直连其 Appium endpoint，本机只跑脚本 | 按量/订阅付费，无硬件 | 想做通 iOS、但不想投硬件 | ⭐ **推荐起步** |
| **B · 一台 Mac 做构建机** | Mac mini + Xcode + Appium；Windows 经局域网/CI 调用 | 一次性硬件投入 | 长期高频 iOS 回归 | ⭐⭐ 长期最优 |
| **C · 非 macOS host 直连真机** | Appium XCUITest driver **11.17+** 起，通过 `appium-ios-remotexpc` + RemoteXPC 隧道连**真机** | 免费，但前置条件多 | 已有真机、且能解决 WDA 预装 | ⭐ 条件满足时可选 |

**方案 C 的四个限制**（依据 Appium 官方文档）：

1. **只支持真机，不支持模拟器**（模拟器仍是 macOS 独占）；
2. 真机必须为 **iOS / tvOS 18 或更高**；
3. **不支持自动选择设备** → 必须显式指定 `appium:udid` + `appium:platformVersion`；
4. **不支持默认的 xcodebuild 启动 WDA** → 必须用 `appium:usePreinstalledWDA`（WDA 已预装）或 `appium:webDriverAgentUrl`（外部托管）。

→ 即使用方案 C，**编译并首次安装 WDA 仍绕不开一次 Xcode**。

### 3.3 `AppiumAdapter` 的 iOS 分支

同一个 `AppiumAdapter` 类，按 `options.platformName` 分叉：

```jsonc
// execution_target: "iPhone15-云真机"  (platform=IOS, engine_key=appium)
{
  "platformName": "iOS",
  "platformVersion": "18.2",
  "deviceName": "iPhone 15",
  "udid": "<真机 udid>",
  "automationName": "XCUITest",
  "appiumServer": "https://hub-cloud.browserstack.com/wd/hub",   // 方案 A
  "bundleId": "com.demo.app",
  "xcodeOrgId": "<Team ID>",
  "xcodeSigningId": "iPhone Developer",
  "usePreinstalledWDA": true,          // 方案 C 必需
  "webDriverAgentUrl": "http://<host>:8100",  // 方案 C 二选一
  "noReset": true,
  "wdaLaunchTimeout": 120000,
  "wdaConnectionTimeout": 120000
}
```

> **默认值策略**：`usePreinstalledWDA` / `webDriverAgentUrl` 只允许在方案 C 下出现；方案 A/B 应保持默认（由 Appium 自行拉起 WDA）。建议在 `AppiumAdapter.create()` 里按 `options.appiumServer` 是否指向云服务来做分支提示。

### 3.4 IOS 定位类型字典

| 语义 | 本方案 `locator_type` | → Appium 实际传参 |
|---|---|---|
| 无障碍 ID | `accessibility_id` | `accessibility id`, `"X"`（**首选，最稳**） |
| 元素名 | `name` | `name`, `"X"` |
| 类链 | `class_chain` | `-ios class chain`, `**/XCUIElementTypeButton[\`label == "登录"\`]` |
| 谓词 | `predicate` | `-ios predicate string`, `label == "登录" AND enabled == true` |
| XPath | `xpath` | `xpath`, `"X"` |

**回退链建议顺序**：`accessibility_id`（10）→ `predicate`（50）→ `class_chain`（80）→ `xpath`（100）。iOS 上 XPath 性能差，**必须放最后**。

### 3.5 决策点（二期启动前必须定）

| # | 决策 | 选项 |
|---|---|---|
| IOS-D1 | iOS 执行环境 | A 云真机 / B Mac 构建机 / C 非 macOS host 直连真机 |
| IOS-D2 | 云服务商 | BrowserStack / Kobiton / LambdaTest / 其他（需评估并发数、价格、是否支持 WDA 预装） |
| IOS-D3 | 是否需要模拟器支持 | 选 A/B → 可以；选 C → **不行**（只有真机） |
| IOS-D4 | 是否已在 App Store 之外分发测试包 | 云真机通常需上传 `.ipa`；需确认签名与 UDID 白名单流程 |

> **建议**：**M7 用方案 A（云真机）起步**，把 iOS 的价值（验证三端定位符映射）先拿到；等 iOS 用例量上来再评估方案 B。

### 3.6 M7 验收标准

1. `platform=IOS, engine_key=appium` 的项目在云真机上跑通 ≥ 5 步用例；
2. 同一「登录按钮」元素的 `IOS` 定位符命中 `accessibility_id` 行，且 Web/Android 行**未被误用**；
3. iOS 执行失败时的截图与 page source 正常归档。

---

## 4. WebView（混合应用 / H5 套壳）对接方案 ★

### 4.1 问题定义

混合应用的典型结构：

```
┌─────────────────────────────────────────────────┐
│ Android / iOS 原生外壳                            │
│  ┌──────────────┐                                │
│  │ 原生导航 / 顶部栏 │  ← 原生控件 → 需要 Appium      │
│  └──────────────┘                                │
│  ┌──────────────────────────────────────────┐   │
│  │ WebView（H5 页面）                        │   │
│  │   <button data-testid="pay">去支付</button> │   │  ← Web DOM → 更适合 Playwright
│  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

**难点**：① 一次用例内要跨两种技术栈；② 同一个 `@id` 在 WebView 里不存在，Web DOM 元素也没有 `resourceId`；③ 定位符与操作 API 完全不同。

> 选型报告附录 C.5 的实测结论：rd-uitest-platform 的 `AppiumMethod` **已有** `get_contexts()` / `switch_to_context()` / `get_html()` 原语，`test_case` 表也已有 `context` 字段 —— 即**"原语已有，编排缺失"**。

### 4.2 方案：Appium 切 context → Playwright 通过 CDP 接棒

```
① AppiumAdapter：driver.contexts
      → ['NATIVE_APP', 'WEBVIEW_com.demo.app']
② AppiumAdapter：driver.switch_to.context('WEBVIEW_com.demo.app')
③ 解析 chrome://inspect 的 devtools endpoint（或通过 Appium 的
   /session/{id}/chromium/... 获取 socket）
④ PlaywrightAdapter：chromium.connect_over_cdp(cdp_endpoint)
      → 拿到 WebView 内的 page，改用 Playwright 操作 H5 内容
⑤ WebView 内操作完成 → detach：Playwright 断开，Appium switch_to_context('NATIVE_APP')
```

**为什么不让 Appium 自己操作 WebView 了？**
Appium 在 WebView 内退化为"WebDriver over mobile"，可用但脆弱：元素查找慢、`execute_script` 受限、等待语义弱。Playwright 在 DOM 上是原生能力（locator 自动等待、trace、网络拦截）。**两个引擎各用各的长处，只交接一次。**

### 4.3 数据模型如何表达：**上下文栈**（不改 `project`）

**关键设计**：**不改 `project.engine_key`**。项目的主引擎仍是 Appium；WebView 是执行过程中的一个**作用域**。用**上下文栈**表达：

```
一次 execution 的上下文栈：
  初始            [ {platform: ANDROID, engine: appium} ]
  attach_webview  [ {platform: ANDROID, engine: appium},
                    {platform: WEB,     engine: playwright} ]   ← 步骤绑定栈顶
  detach_webview  [ {platform: ANDROID, engine: appium} ]
```

**这带来一个极其自然的收益**：栈顶决定 `platform`，而 `platform` 正是 `element_locator` 的一个维度 —— 所以

> **WebView 内的元素用 `platform=WEB` 的定位符，原生外壳元素用 `platform=ANDROID` 的定位符，二者挂在同一个「逻辑元素」上互不干扰。**

即：技术方案 §3.2.4 的 `element_locator` 二维模型，**在 WebView 场景下自动成立，无需任何额外建模**。这是 P2 设计（坚持 `platform` 独立维度）的第二个回报。

**新增两个动作**（二期追加到 `action_catalog`）：

| `action_key` | name | category | platforms | engines | params |
|---|---|---|---|---|---|
| `attach_webview` | 接管 WebView | CONTEXT | `["ANDROID","IOS"]` | `["appium"]` | `{"context_name": "auto"}`（`auto` = 取第一个 `WEBVIEW_*`） |
| `detach_webview` | 退出 WebView | CONTEXT | `["ANDROID","IOS"]` | `["appium"]` | `{}` |

> **注意**：`attach_webview` 的 `engines` 写 `["appium"]`，但它**实际会拉起 Playwright 适配器实例**。这是"动作声明在 Appium 上、副作用涉及第二个引擎"的唯一特例，需在 `CAPABILITY_MATRIX` 与执行器里显式处理（建议在 `actions.py` 里用 `ContextStackAction` 单独实现，不走普通引擎分发）。

### 4.4 与 P1（显式路由）的关系

| 问题 | 回答 |
|---|---|
| 这算不算违反"路由必须显式"？ | **不算**。P1 反对的是"用动作反推端类型"这种**隐式、无声明**的路由；`attach_webview` 是**显式写进用例的步骤**，栈的变化完全由步骤驱动、可追溯 |
| 项目级路由还用吗？ | **用**。`project.platform/engine_key` 决定**初始栈顶**与**主引擎**，即"这个项目默认怎么跑" |
| 会不会导致用例只能在混合场景用？ | 不会。纯 Web / 纯原生项目永不出现 `attach_webview`，栈深度恒为 1，行为与一期完全一致 |
| 步骤结果怎么记？ | `execution_step_result.active_platform` / `active_engine` 记录栈顶（这正是 §6-5 要求一期预留两列的原因） |

### 4.5 编排示例

```jsonc
[
  { "seq": 1, "action_key": "start_app",       "params": {} },
  { "seq": 2, "action_key": "click",           "element_id": 301 },          // 原生：进入"我的"页
  { "seq": 3, "action_key": "click",           "element_id": 302 },          // 原生：点"去支付"
  { "seq": 4, "action_key": "attach_webview",  "params": { "context_name": "auto" } },
  { "seq": 5, "action_key": "wait_element",    "element_id": 401 },          // ← platform=WEB 的定位符
  { "seq": 6, "action_key": "input",           "element_id": 402, "params": { "text": "100.00" } },
  { "seq": 7, "action_key": "click",           "element_id": 403, "params": {} },
  { "seq": 8, "action_key": "get_text",        "element_id": 404, "output_var": "order_no",
    "assert_expr": { "op": "matches", "value": "^\\d{16}$" } },
  { "seq": 9, "action_key": "detach_webview",  "params": {} },
  { "seq": 10, "action_key": "click",          "element_id": 303 },          // 回到原生：确认页
  { "seq": 11, "action_key": "screenshot",     "params": {} }
]
```

对应 `element_locator` 的行：

| element_id | 逻辑名 | platform | locator_type | locator_value |
|---|---|---|---|---|
| 301 | 我的 | `ANDROID` | `text` | `我的` |
| 302 | 去支付 | `ANDROID` | `resource_id` | `com.demo.app:id/btn_pay` |
| 401 | 订单金额输入框 | `WEB` | `testid` | `amount-input` |
| 402 | 订单金额输入框 | `WEB` | `css` | `.pay-form input[name=amount]` |
| 403 | 提交订单 | `WEB` | `testid` | `submit-order` |
| 404 | 订单号 | `WEB` | `css` | `.order-result .no` |

→ 步骤 5–8 自动用 `platform=WEB` 的定位符并交给 Playwright；步骤 2/3/10 用 `platform=ANDROID` 的定位符交给 Appium。**同一份用例，两个引擎，零分支代码。**

### 4.6 风险与待验证

| # | 风险 | 说明 | 对策/待验证 |
|---|---|---|---|
| WV1 | **CDP endpoint 获取方式不稳定** | `chrome://inspect` 端口需转发（`adb forward tcp:9222 localabstract:webview_devtools_remote_<pid>`）；不同 WebView 实现（系统 WebView / X5 / 自研内核）差异大 | **M7 第一件事就是实测**：在 AVD 上验证 Android System WebView 的 endpoint 获取；若不可靠，退化为"Appium 在 WebView 内操作"（功能可用、体验较差） |
| WV2 | X5 / 第三方内核不支持 CDP | 国内 App 常用腾讯 X5 内核，devtools 协议支持不完整 | 待验证；必要时为这类 App **只在 WebView 内用 Appium**，原生仍用 Appium（栈深度退化为 1） |
| WV3 | iOS WebView 的 CDP 支持 | iOS WKWebView 需 `isInspectable = true`（iOS 16.4+）且依赖 `ios_webkit_debug_proxy` | 待验证；iOS 侧优先级低于 Android |
| WV4 | Playwright 与 Appium 争抢同一 WebView | 两方同时操作会互相干扰 | 用上下文栈**串行化**：栈顶唯一，非栈顶引擎处于"挂起"态（不持有操作权） |
| WV5 | 用户登录态/Storage 不共享 | Playwright 通过 CDP 接管的是**已存在的** WebView，天然继承登录态（这也是必须"接管"而非"另开浏览器"的原因） | 已由设计规避，需在验收中确认 |
| WV6 | `attach_webview` 拉起的 Playwright 实例生命周期 | 必须在 `detach` 或 execution 结束时确保关闭 | `SessionManager` 兜底（§6-7/§6-6） |

### 4.7 M7 验收标准

1. 上例 11 步用例在 AVD 上端到端跑通，步骤 5–8 的 `active_platform=WEB`、`active_engine=playwright`，步骤 2/3/10 为 `ANDROID`/`appium`；
2. `detach_webview` 后原生操作正常（验证 context 切回）；
3. 若 WV1 实测失败：记录结论，并给出"降级方案"（WebView 内用 Appium）的工时评估。

---

## 5. 二期里程碑

| 里程碑 | 内容 | 前置 | 主要风险 |
|---|---|---|---|
| **M5 · Android · Appium** | `AppiumAdapter` 实现 + AVD 环境 + 设备租约 | M1–M3 完成 | 环境搭建（WHPX / x86_64 镜像） |
| **M6 · Android · 双引擎** | `UiAutomator2Adapter` + 并发按设备数限流 | M5 | 定位语汇差异带来的映射 bug |
| **M7 · iOS + WebView** | 云真机接入 + `attach_webview`/`detach_webview` + 上下文栈 | M5（Appium 适配器复用） | WV1（CDP endpoint）为最大不确定项 |
| **M8（可选）· 分布式引擎注册** | 引擎注册到任意机器（借鉴流马设计，只读架构） | M6 | 一期不涉及 |

**建议顺序**：M5 → M6（可选）→ M7。**M7 的 WebView 部分建议与 iOS 部分解耦**，先做 Android WebView（风险 WV1 可快速验证），iOS WebView 后置。

---

## 6. 对一期（M1–M3）的依赖清单 ★★

**这是本文档最重要的一节**。以下 10 条如果一期做对了，二期只需"新增文件 + 新增数据"；做错了就要改一期代码。

| # | 一期必须做对的事 | 做错的话，二期会怎样 | 优先级 |
|---|---|---|---|
| 1 | **`EngineAdapter` 的元素动作收 `LocatorChain`**（不是单个 `Locator`） | 二期移动端回退链无法接入；要么改接口（全适配器改），要么移动端放弃回退能力 | 🔴 高 |
| 2 | **`platform` 是独立字段且只有 3 个取值**（D5） | 若把 WAP 也当端，移动端会继续膨胀枚举；若把 platform 塞进 engine_key，则无法按端统计 | 🔴 高 |
| 3 | **`element_locator.engine_key` 维度必须存在**（含 `'*'` 通配） | 二期 Android 双引擎、WebView 跨端都无处落定位符 → 需改表 + 改解析器 | 🔴 高 |
| 4 | **`CAPABILITY_MATRIX` + 启动强校验**（`action_catalog.engines` ↔ 矩阵一致） | 二期加的动作若声明了但没实现，会静默失效或运行时崩溃 | 🟡 中 |
| 5 | **`execution_step_result` 预留 `active_platform` / `active_engine`**（可空） | 二期需做表迁移 + 回填；WebView 场景无法追溯每步用了哪个引擎 | 🟡 中 |
| 6 | **`EngineAdapter.start()` / `stop()` 幂等**，`stop()` 可安全重复调用 | 多引擎 session 下清理逻辑会重复触发，出现难以复现的资源泄漏 | 🟡 中 |
| **7** | **`SessionManager` 支持一次 execution 内 1..N 个 adapter 实例**（⚠️ **不得为单例**） | **WebView 接棒无法实现**，且这是**架构级返工**：所有依赖"唯一 session"的代码都要改 | 🔴 **最高** |
| 8 | **`import-linter` 红线**（L3 不得 import 引擎库） | 二期引入 `appium` 依赖后，会直接污染业务层 | 🟡 中 |
| 9 | **`execution_target.options` 用 JSON**（不是固定列） | 设备 caps 有 20+ 参数且各引擎不同，固定列必然不够 → 改表 | 🔴 高 |
| 10 | **前端 StepEditor 由 `action_catalog` 驱动**（不硬编码动作） | 二期加 `attach_webview` 等动作要改前端代码 | 🟡 中 |

### 6.1 一期验收时的"二期友好性"检查（建议加入 M3 验收）

- [ ] 写一个 `FakeAdapter` 并通过契约测试 → 证明接口可被第二个实现满足（**间接验证 #1/#6**）
- [ ] `SessionManager` 单元测试里**同时创建 2 个 adapter 实例**并各自 start/stop（**直接验证 #7**）
- [ ] 库表 REVIEW：`execution_step_result` 是否已有 `active_platform`/`active_engine` 两列（**验证 #5**）
- [ ] `import-linter` 在 CI 中执行且通过（**验证 #8**）
- [ ] 在 `execution_target` 里手填一条 `platform=ANDROID` 的记录并保存成功（**验证 #9/#2**）
- [ ] 在 `element_locator` 里为某元素手填一条 `platform=ANDROID, engine_key=uiautomator2` 的记录并保存成功（**验证 #3**）

> 这 6 项不需要任何真机/模拟器，**纯本地即可完成**，成本极低，但能把二期的最大风险提前消掉。

---

## 7. 风险与待验证汇总

| # | 风险 | 等级 | 对策 |
|---|---|---|---|
| MR1 | Android 模拟器在 Windows 上性能不足 | 🟡 | x86_64 镜像 + WHPX 加速；必要时改用云真机 |
| MR2 | Android 双引擎导致定位符维护量翻倍 | 🟡 | `element_locator.engine_key` 维度已支持；建议 M6 可选，纯原生项目二选一 |
| MR3 | iOS 环境依赖 macOS / 云账号（无 Mac） | 🟡 | 方案 A 云真机起步；**不阻塞 M5/M6** |
| MR4 | WDA 首次编译必须 Xcode | 🟡 | 方案 A/B 由服务商或 Mac 构建机承担；方案 C 需 `usePreinstalledWDA` |
| MR5 | **WebView CDP endpoint 获取不稳定** | 🔴 | M7 第一件事实测；失败则降级为"Appium 操作 WebView" |
| MR6 | X5 / 自研内核不支持 CDP | 🟡 | 待验证；这类 App 直接走降级方案 |
| MR7 | 设备并发受物理设备数限制 | 🟡 | 一期已注明；二期按设备数限流 + 设备租约 |
| MR8 | 厂商 ROM 定制行为 | 🟢 | 只在上架前验收才需真机（选型报告附录 B.5） |

---

## 8. 附：二期启动前的决策待定项

| # | 待定 | 建议默认 |
|---|---|---|
| 1 | Android 是否真的要做双引擎（M6） | **先做，用于验证 P2**；之后可只保留 Appium |
| 2 | Android 默认引擎 | `appium`（能力全，且与 iOS 共用适配器） |
| 3 | iOS 执行环境（IOS-D1） | **A 云真机**起步 |
| 4 | iOS 云服务商（IOS-D2） | 待比价（并发数 / 价格 / WDA 预装支持） |
| 5 | WebView 是否纳入二期 | 若产品确有 H5 套壳页 → 纳入；否则可延后到 M8 |
| 6 | 是否需要"引擎注册到任意机器"（分布式） | 二期不做；M8 评估 |
| 7 | 移动端通知/报告增量 | 沿用项目级 `notify_type`（钉钉 / 企业微信），二期不改 |

---

*— 文档结束 —*
*本文档为预留方案。二期启动时，请先复核：Appium / uiautomator2 / XCUITest driver 的版本与 API 是否有变化，以及 §7 中 🔴 级风险的实测结论。*
