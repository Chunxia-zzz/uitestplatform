# UI 自动化平台 · 候选项目验证与选型报告

**调研日期**：2026-10-13　|　**二次验证更新**：2026-10-14（见 **附录 C**）
**调研目标**：为「App 软件 + 配套 Web 中台」项目组合，选定一个「统一管理测试资产、按项目/端路由到 Playwright 或 Appium」的多引擎 UI 自动化平台改造底座。
**证据原则**：本文所有仓库事实均来自 **GitHub REST API / Gitee OpenAPI / npm registry / 各仓库 README 与源码/建表语句原文** 的实测抓取（2026-10-13 初查，2026-10-14 二次验证），已逐条标注来源。无法证实的信息一律标注为「未证实」，不当作事实使用。

> **📌 阅读顺序建议**：先读 §0 一页结论 → 再读 **附录 C（2026-10-14 二次验证与结论更新）**，附录 C 已修正了正文中 5 处不够准确的判断（MokaTest 元素库定位、扩展点 C 现状、路由判据等）。正文保留初查原貌，以附录 C 为准。

---

## 0. 一页结论（TL;DR）

| 问题 | 结论 |
|---|---|
| 有没有"一个现成项目直接拿来用"？ | **没有完美匹配的**。但有 **1 个高度接近的直接底座**（rd-uitest-platform）。 |
| 最推荐的底座 | **rd-uitest-platform（Gitee: shangguanyi666/rd-testing-platform + fe-uitest-platform）** — 全候选里**唯一同时具备 Playwright + Appium + uiautomator2 三引擎**，且"项目/用例/步骤/报告/调度/通知/AI"全套已落地。 |
| 它最大的缺口 | **没有独立的「元素库 + 多端 Locator 映射」模型**。元素定位符以 `element_type` + `element_text` **内联在每一步骤里**，无复用、无多端映射、无自愈。（实测其 `TableStructure.sql`） |
| 补这个缺口找谁 | **MokaTest**（有完整 `Element` 领域模型 + `ElementController` + `ElementLocatorProcessor` + `AiLocatorHealService`）。⚠️ **2026-10-14 修正**：实测其 `element` 表是**单个定位符 + Web-only 枚举**，**不提供多端映射** → 它只能当**「单端元素库」的结构蓝本**，**多端映射必须从零设计**（附录 C.3）。 |
| 「按项目路由引擎」怎么写 | 参考 **Wix Pilot** 的 `FrameworkDriver` + `PromptHandler` 双接口抽象（MIT），把它做成可插拔适配器注册表。⚠️ **注意**：rd 现有 `project.type` 枚举只有 PC/WAP，App 用例靠动作 `type=3/4` **隐式推断** → 方案必须**显式新增 platform/engine 字段**（附录 C.6）。 |
| 谁能学到"多引擎统一封装" | **Toolium**（Apache-2.0，Telefonica 维护，配置驱动切换 Selenium/Playwright/Appium）与 **Mops**（同用例内自由切引擎）。 |
| 谁只能当参考、不能改造 | **流马 Liuma**（AGPL-3.0，二次开发必须开源；且 2024-03 起停更）、**Testver**（npm 分发、**无源码仓库**，闭源产品）。 |
| 移动端执行器备选 | **Appium 为主线**；maestro-runner（Apache-2.0，Go 单二进制）可作 YAML 声明式备选，但 **Windows 需 WSL**，且其默认 DeviceLab driver 二进制不开源。 |
| 最终推荐路线 | **组合改造**：以 rd-uitest-platform 为执行底座 → 补「元素库 + Locator 多端映射 + 适配器注册表」三块 → 前端体验参考 MokaTest → 引擎抽象参考 Pilot/Toolium。 |

> **一句话**：不要自建，也不要试图"整体替换"，而是**在 rd-uitest-platform 上做三处外科手术式扩展**。

---

## 1. 仓库验证结果（全部实测）

| # | 名称 | 真实地址 | 是否存在 | License（实测） | 最后提交 | 活跃度 | 与你描述的偏差 |
|---|---|---|---|---|---|---|---|
| 4.1 | **rd-uitest-platform** | `gitee.com/shangguanyi666/rd-testing-platform`（后端）+ `.../fe-uitest-platform`（前端） | ✅ | ⚠️ **Gitee API 返回 license = None（无 LICENSE 文件）**，仅 README 徽章自称 MIT | 后端 2026-10-08；前端 2026-05-28 | 🟢 **活跃**（2 个月内有提交） | 地址需修正：你给的"Shangguan Yi/rd-uitest-platform"关键词正确，实体仓库名是 `rd-testing-platform` |
| 4.2 | **流马 Liuma** | `github.com/Chras-fu/Liuma-platform`（平台端）+ `.../Liuma-agent`（引擎端） | ✅ | **AGPL-3.0** | 平台端 2024-03-14；引擎端 2024-03-13 | 🔴 **已停更约 2.5 年** | 你给的是 `Liuma-agent`（那是**设备代理端**，不是平台）；平台端才是 `Liuma-platform` |
| 4.3 | **MokaTest** | `github.com/Jinglong233/MokaTest`（Gitee 镜像同步） | ✅ | **BSL 1.1**（Business Source License，GitHub 识别为 NOASSERTION/Other） | 2026-10-11 | 🟢 **非常活跃**（仓库 2026-08-08 创建，2 个月 24 star） | 技术栈正确；但**它不止有元素库，还有完整需求/BUG/测试管理体系**，规模比"Web 平台起点"大得多 |
| 4.4 | **Testver** | npm `@testver/testver`（v1.2.2）；官网 `testver.com` | ✅ 但**闭源** | `SEE LICENSE IN LICENSE`（**npm 包无 repository 字段**） | 包更新 2026-10-12 | 🟢 商业产品，迭代活跃 | ⚠️ **关键修正：它没有开源仓库**，是 12 MB 的打包产物，**无法读源码、无法二次开发**。只能当产品形态参考 |
| 4.5 | **maestro-runner** | `github.com/devicelab-dev/maestro-runner` | ✅ | **Apache-2.0**（但 DeviceLab driver 二进制**不开源**） | 2026-10-10 | 🟢 **很活跃**（501 star，2026-01 创建） | 定位正确；补充：**Windows 需 WSL**，且不是"Maestro 的增强版"而是**Maestro 的开源替代实现** |
| 4.6 | **Wix Pilot** | `github.com/wix-incubator/pilot`（不是 `wix/pilot`） | ✅ | **MIT** | 2026-02-08 | 🟡 中等（47 star，24 open issues） | 地址需修正为 `wix-incubator/pilot` |
| 4.7 | **QA Multipurpose Framework** | — | ❌ **未证实** | — | — | — | 多轮定向检索**未找到**任何以此命名的具体仓库，疑为"多用途框架"的口语化描述而非实体项目。**不作为候选** |
| 4.8 | **Zosma QA** | `github.com/zosmaai/zosma-qa`（包：`zosma-qa` / `@zosmaai/zosma-qa-cli`） | ✅ | **Apache-2.0** | npm 最新 0.0.11（2026-03-28） | 🔴 **极冷**（仓库 10 star，npm 周下载≈0，最近半年无提交） | 定位正确；但 **Appium 目前只是 `@zosmaai/zosma-qa-appium` 空壳包**，成熟度不足 |
| 4.9 | **Toolium** | `github.com/Telefonica/toolium` | ✅ | **Apache-2.0**（PyPI 已验证） | 2025-12-03 | 🟡 中等（企业维护，918 commits） | 定位正确；补充：**Playwright 集成为 Beta**，Appium 是成熟路径 |
| 4.9 | **Mops** | `github.com/CustomEnv/mops`（原名 `EnvInc/dyatel` / `dyatel-wrapper`） | ✅ | **MIT（GitHub 识别）/ README 标称 Apache** ⚠️ 口径不一致 | 2025-07-19 | 🔴 冷（9 star，最后 release 2025-01） | 定位正确；亮点是**同一用例内自由切换 Selenium/Appium/Playwright** |

**⚠️ 两处必须优先处理的许可证风险**（详见 §7）：
1. `rd-uitest-platform` **README 徽章写 MIT，但仓库中没有 LICENSE 文件**（Gitee API `license=None`）→ 改造前必须向作者确认授权。
2. `MokaTest` 是 **BSL 1.1**：内网/内部业务自用免费，但**做成对外托管的云服务需商业授权**。

---

## 2. 逐项验证明细

### 2.1 rd-uitest-platform —— 唯一的多引擎统一平台 ✅ 最高优先级

**仓库元数据（Gitee OpenAPI 实测）**

| 项 | 值 |
|---|---|
| 后端 | `gitee.com/shangguanyi666/rd-testing-platform` · Python · 21 star / 12 fork · 创建 2024-10-18 · 最后推送 **2026-10-08** |
| 前端 | `gitee.com/shangguanyi666/fe-uitest-platform` · Vue 3.5 + Vite 6 + Element Plus · **MulanPSL-2.0** · 最后推送 2026-05-28 |
| 在线体验 | `http://14.103.196.193`（README 原文，账号 test / 123456） |
| License | ⚠️ **后端仓库无 LICENSE 文件**（Gitee API license=None），README 徽章自称 MIT；前端是 MulanPSL-2.0 |

**技术栈（README 原文）**：FastAPI 0.115 / Playwright 1.51 / **Appium-Python-Client 4.0.1** / **uiautomator2 3.5** / pytest + xdist + rerunfailures / aiomysql / Redis Pub-Sub / WebSocket / Allure / APScheduler / DeepSeek AI / DingtalkChatbot。

**真实覆盖的端**（README 原文）：
> 「支持 Web UI、WAP 端、API 接口及移动端 App（Android/iOS）的自动化测试」
> 移动端：**基于 Appium，支持 Android 和 iOS 设备，通过 Redis 队列调度执行**

**源码实测结论（这是我替你读源码后最重要的发现）**

1. **数据模型**（解析 `TableStructure.sql`，共 11 张业务表）：
   `account` · `ai_model` · `app_case_steps` · `conversation_date` · `member` · `playwright_method` · **`project`** · `python_script` · **`test_case`** · `test_report` · `testcase_generation_task`

2. **「项目」模型存在且带端类型**：`project` 表有 `type`（1:PC端 2:WAP端）、`platform_name` / `platform_version` / `device_name` / `app_package` / `no_reset` / `app_activity` → **移动端能力已在项目维度建模**。

3. **「元素」模型 ❌ 不存在独立表**：
   `app_case_steps` 把定位信息**内联在步骤行**中 —— `element_type`（元素类型）+ `element_text`（元素的值）。**没有 element 表，没有 locator 映射表，没有多端映射**。
   替代品是 `playwright_method` 表（可复用方法库，`type` = 1:web/wap 2:api 3:ios 4:android 10:通用）→ 这是**步骤复用**，不是**元素复用**。

4. **引擎路由方式：按用例类型分模块，不是可插拔适配器**：
   `routers/` 下并列 `web_case.py` / `api_case.py` / `app_case.py`；`services/` 同理；执行侧由 `queue_runner.py`（Redis 队列消费者）承接 App 用例。
   → 想加第三个引擎（比如内嵌 WebView 走 Playwright、原生走 Appium）需要**改模块、加分支**，不是"注册一个 adapter"。

5. **引擎封装已是类级封装**：`app/appium_method.py` 里 `class AppiumMethod` 用 `platformName` 区分 Android/iOS，构造 caps 时读取项目级 `platform_name/platform_version/device_name/app_package/app_activity/no_reset` → **适配层的雏形已经有了，只差"接口化 + 注册表"**。

6. 另有 `CLAUDE.md`（仓库根目录）→ 说明该项目本身也在用 AI 辅助开发，代码风格/约定文档较全。

**结论**：✅ 作为**执行底座**高度匹配；❌ 作为**测试资产管理**（元素库/多端 Locator）不足；🔧 引擎路由需重构为适配器模式。

---

### 2.2 流马 Liuma —— 架构参考价值高，但**不适合作为改造底座** ⚠️

**README 原文关键点**：
> 「项目分为平台端和引擎端，采用分布式执行设计，可以将测试执行的节点(即引擎)注册在任意环境的任意一台机器上」
> WebUI：「支持关键字驱动，零代码编写用例」「**支持 UI 元素统一管理**，Excel 模板批量导入」「支持自定义关键字」「支持本地引擎执行，实时查看执行过程」
> AppUI：「支持安卓和苹果系统」「支持真机管理、投屏和在线操作」「**支持控件元素在线获取，一键保存元素**」

**技术栈**：前端 Vue + ElementUI；后端 Java + Spring Boot；测试引擎 Python。

**为什么不推荐直接改造**：
- **AGPL-3.0**，README 明确写：「如果您需要二次开发，请务必遵循 AGPL 开源协议，并保留版权信息」→ 一旦改造并对外提供服务，**整个衍生作品都要以 AGPL 开源**。对要做产品化的平台是硬约束。
- **停更**：平台端最后提交 2024-03-14，已 2.5 年无更新。
- **它证明了设计可行性**：元素统一管理 + 控件在线拾取 + 引擎注册，正是你需要的形态 —— 值得**读架构，不读代码**。

---

### 2.3 MokaTest —— 元素库与编排体验的最佳参考，但**引擎单一 + 模块庞大** ⚠️

**实测模块结构**（GitHub API 抓取 `backEnd/`）：
`platform-starter`（启动）· `platform-automation`（UI/API 自动化核心）· `platform-qa`（需求/BUG/用例）· `platform-ai`（AI 能力）· `platform-common`

**`platform-automation` 内的关键类（实测目录）**：
- **领域模型** `domain/ui/`：`Project.java` · **`Element.java`** · `Scene.java` · **`TestStep.java`** · `Plan.java` · `Report.java` → **「项目 → 元素 → 场景/用例 → 步骤」模型完整存在** ✅
- **控制器**：`ElementController` · `ProjectController` · `SceneController` · `StepController` · `PlanController` · `ReportController` · `TaskController` · `TeamController`
- **元素处理**：`element/ElementProcessor.java` · `element/ElementLocatorProcessor.java` · **`element/AiLocatorHealService.java`**（AI 定位自愈）✅
- **调试**：`debug/PlaywrightDebugSession.java` · `PlaywrightPlanSession.java` · `TestExecutionContext.java` + `config/DebugWebSocketHandler.java`
- **执行引擎**：只有 **Playwright**（类名直接带 Playwright），**未见任何 Appium 相关包/类** ❌

**其它实测**：License **BSL 1.1**；技术栈 Vue 3 + Vite + Arco Design / Spring Boot 3 + MyBatis-Plus + Sa-Token / MySQL 8 / MinIO / Docker Compose 一键部署；仓库 2026-08-08 创建、2026-10-11 仍在提交（**非常活跃**）；star 24（新仓库，社区规模还小）。

**结论**：**前端/元素管理/编排/调试体验**是最值得借鉴甚至直接复用的部分；但 ①只支持 Playwright ②Java 技术栈 ③BSL 授权限制 —— 决定了它**只能作为"管理端体验参考"，不能作为移动端底座**。

---

### 2.4 Testver —— ❌ **闭源，不可读源码、不可改造**

**npm registry 实测**：
```
latest: 1.2.2      license: "SEE LICENSE IN LICENSE"
repository: None   homepage: None   bugs: None
dist.unpackedSize: 12,351,795 bytes (≈12 MB)
created: 2026-06-13        modified: 2026-10-12
```
**没有任何 repository 字段** → 这是**闭源打包分发**，不是开源项目。

它的产品定位确实是"包裹现有框架"（README 原文）：
> 「Testver is a self-hosted, AI-native **control plane for your existing test frameworks**」
> 支持：Playwright · Cypress · Selenium · **Appium** · WebdriverIO · Cucumber · REST Assured · PyTest · Puppeteer · Robot Framework
> 「Mobile testing — Native Android & iOS **via Appium** — no separate tool, the same Testver UI」

**结论**：**只能当产品形态参照物**（它证明了"一个 UI 管多引擎"的产品体验该长什么样），**不能作为改造对象**。你简报里"适合研究其执行层如何路由 Web/Mobile"这一条**无法执行**（读不到源码）。

---

### 2.5 maestro-runner —— 移动执行器候选，有 2 个硬约束 ⚠️

**README 原文关键点**：
> 「Fast UI test automation for Android, iOS, Web, React Native, Flutter & Expo」
> 「Open-source Maestro alternative — single binary, no JVM」
> 「Runs Maestro YAML flows on real devices... Supports Android (UIAutomator2), iOS (WebDriverAgent), Web (Chrome CDP), and cloud (**Appium**)」
> 驱动表：`DeviceLab`(Android/iOS 默认) · `UIAutomator2` · `WDA` · `Browser (CDP)` · **`Appium`（`--driver appium`，用于云真机 BrowserStack/Sauce Labs/LambdaTest/TestingBot）**
> 报告：**HTML / JUnit XML / Allure-compatible out of the box**
> 「**on Windows, use WSL**」← 硬约束
> 二进制许可：「the prebuilt on-device agents behind `--driver devicelab` ... **are not open source**. You may redistribute them unmodified ... you may not modify them」

**结论**：✅ 驱动抽象（`--driver` 可切换）非常值得学；✅ 可直接接 Appium 云真机。
⚠️ 但：①**用户在 Windows**，需 WSL，本地调试体验打折；②核心 DeviceLab 驱动二进制**不可修改**，深改受限；③它是**CLI 执行器**，不是带数据模型的平台 —— 只能当"移动执行器"挂到底座后面。

---

### 2.6 Wix Pilot —— 「引擎适配层」的最佳抽象参考 ✅

**README 原文实测**：
> 「Originally designed for Detox, it now supports multiple testing platforms including **Puppeteer, Playwright, Appium**, and more」

**包结构（正是"适配器"该有的样子）**：
```
@wix-pilot/core                     # 核心：Pilot 类 + 两个关键接口
@wix-pilot/detox                    # 移动 (Detox)
@wix-pilot/webdriverio-appium       # 移动 (Appium)
@wix-pilot/puppeteer                # Web
@wix-pilot/playwright               # Web
```
**两个关键接口**：
- `frameworkDriver: TestingFrameworkDriver` → **引擎适配接口**（每个引擎一个实现）
- `promptHandler: PromptHandler` → **LLM 接口**（`runPrompt(prompt, image?)` / `isSnapshotImageSupported()`）

**API**：`pilot.perform(...steps)` 用自然语言执行步骤；`pilot.autopilot(goal)` 自主模式返回 `AutoReport`（含 UX/无障碍/i18n 评分）。

**结论**：✅ **MIT 协议、接口干净**，是把"按项目/端路由引擎"实现成**可插拔注册表**的最佳模板。⚠️ 但它是 **JS/TS 生态 + 以自然语言驱动为主**，与 rd-uitest-platform 的 Python + 结构化步骤 不同源，**只借架构、不搬代码**。

---

### 2.7 QA Multipurpose Framework —— ❌ 未证实

多轮定向检索（GitHub + 通用搜索）**未找到**任何以此名称存在的具体仓库。检索返回的都是互不相关的通用框架（`qaAssignmentMavericks`、`playwright-java-accelerator`、`QA_Playwright-Automation-Framework` 等），**没有任何一个**同时集齐"企业级 + Web Playwright + API + Mobile Appium"并能对应到这个名称。
**处理**：**移出候选名单**。若你确有该仓库链接，请提供，我再单独验证。

---

### 2.8 Zosma QA —— 思路可参考，项目本身太冷 🔴

**实测**：`github.com/zosmaai/zosma-qa` · **Apache-2.0** · 包 `zosma-qa` / `@zosmaai/zosma-qa-cli` / `@zosmaai/zosma-qa-playwright` / `@zosmaai/zosma-qa-core` / **`@zosmaai/zosma-qa-appium`**
**活跃度**：npm 最新 0.0.11（2026-03-28），Snyk 报告「No commits over the last 6 months」「Weekly downloads (0)」「GitHub Stars 0」（npm 页面口径），仓库页显示 10 star / 6 fork。
**AI 集成方式（原文）**：`npx zosma-qa agents init` 生成 **Playwright 官方 planner / generator / healer 三个 agent** 的定义文件，交给 OpenCode / Claude Code / VS Code Copilot 使用。
**结论**：AI 集成方式**很轻**（本质是"生成 agent 配置 + 交给编码工具"），可作为「AI 辅助生成/修复用例」的最简实现参考；但**项目本身成熟度不足，不建议依赖**。

---

### 2.9 Toolium / Mops —— 多引擎统一封装的实现参考 ✅

| | **Toolium** | **Mops** |
|---|---|---|
| 仓库 | `github.com/Telefonica/toolium` | `github.com/CustomEnv/mops`（原 `EnvInc/dyatel`） |
| 语言 | Python | Python |
| License | **Apache-2.0**（PyPI 已验证） | **MIT（GitHub 识别）/ README 标称 Apache** ⚠️ 口径不一致 |
| 活跃度 | 2025-12-03 最后提交，PyPI **3.8.1 (2026-04-15)** | 2025-07-19 最后提交，release 3.1.0 (2025-01-29)，9 star |
| 覆盖引擎 | Selenium + **Playwright（Beta）** + **Appium** + requests(API) | Selenium + **Appium** + **sync Playwright** |
| 核心机制 | **配置文件选择驱动** + Page Object + 视觉测试 | **同一用例内自由切换引擎** + `Locator` dataclass + 自动判定定位类型 |

**Toolium 原文**：
> 「a Python wrapper tool of Selenium, Playwright and Appium libraries to test web and mobile applications in a single project. It provides a way of **choosing and configuring the driver through a configuration file**」

**Mops 原文**：
> 「**Engine Switching**: Switch between Selenium, Appium, and Playwright **within the same test case**」
> 「**Automatic Locator Type Definition**: The locator type will be automatically determined based on the provided locator string or Locator object」

**结论**：⚠️ **不要直接依赖**（Toolium 的 Playwright 是 Beta、社区小；Mops 已近停更）。但两者的 **`Locator` dataclass + 自动定位类型判定 + 驱动的配置化选择**，**正好可以填 rd-uitest-platform 缺的「Locator 多端映射」**。

---

## 3. 关键源码发现：数据模型 与 引擎路由

### 3.1 你的期望模型 vs 各候选的实况

| 期望模型 | rd-uitest-platform | MokaTest | 流马 Liuma | Pilot | Toolium/Mops |
|---|---|---|---|---|---|
| **Project**（绑定端类型） | ✅ `project` 表含 `type` + 移动端字段 | ✅ `Project.java` | ✅ | ❌ 无（纯代码库） | ❌ 无（配置驱动） |
| **Element**（逻辑元素） | ❌ 无元素表 | ✅ **`Element.java` + `ElementController`**（实测 `element` 表：树形 `element_type` = ELEMENT/FOLDER） | ✅ **「UI元素统一管理」+ 控件在线拾取** | ❌ 无 | ⚠️ 以 Page Object / `Element` 类表达 |
| **Locator**（多端定位符映射） | ❌ **内联 `element_type`+`element_text` 在步骤行**（无独立映射表） | ⚠️ **单定位符 + Web-only 枚举**（`locator_type` 11 值：id/class/xpath/css/text/placeholder/role/test_id/label/title/alt，**无任何移动端类型**）—— 2026-10-14 修正，见附录 C.3 | ✅ App 端有控件拾取保存 | ⚠️ 由 LLM 运行时推断 | ✅ `Locator` dataclass + 自动类型判定 |
| **TestCase / Scene** | ✅ `test_case` 表 | ✅ `Scene.java` | ✅ | ⚠️ describe/it（代码） | ⚠️ 代码 |
| **Step / Action** | ✅ `app_case_steps` 表（含 python/断言/SQL/上传等 20+ 字段） | ✅ `TestStep.java` | ✅ 关键字驱动 | ✅ 自然语言步骤 | ✅ |
| **Execution / Target** | ⚠️ 由「用例类型模块」隐式决定（**`project.type` 枚举只有 PC/WAP，App 靠动作 type=3/4 隐式推断** ← 详见附录 C.6） | ⚠️ Plan（**`project` 表无平台/端字段** ← 附录 C.3） | ✅ **引擎注册到任意机器** | ✅ `frameworkDriver` | ✅ 配置/运行时选择 |
| **Engine Adapter** | ⚠️ 有类封装（`AppiumMethod` / `UiAutomator2Method` / `WebAutomation`），**无接口无注册表**；但**跨引擎统一动作字典已存在**（`playwright_method.type` = 1 web/wap · 2 api · 3 iOS · 4 Android · 10 通用 ← 附录 C.4） | ❌ 只有 Playwright | ⚠️ 引擎端抽象（AGPL） | ✅ **`TestingFrameworkDriver` 接口 + 每引擎一包** | ✅ `DriverWrapper` |
| **Report** | ✅ `test_report` + Allure + 录屏 | ✅ `Report.java` + MinIO | ✅ 截图存七牛云 | ⚠️ AutoReport | ⚠️ Allure/视觉对比 |

**这就是本次调研最核心的一张表**：**没有任何候选同时满足「元素库 + 多端 Locator 映射 + 多引擎适配器」。** 三块能力分散在不同项目里 —— 所以答案是"组合"，不是"选一个"。

### 3.2 路由逻辑现状

**rd-uitest-platform 的实际路由（实测）**：
```
test_case.project_type ──► 路由到 routers/{web_case | api_case | app_case}.py
                                    │
                    ┌───────────────┼───────────────┐
             playwright_method   api_method      appium_method / uiautomator2_method
                (Web/WAP)          (API)          (Android / iOS via platformName)
                                    │
                            queue_runner.py (Redis 队列消费者，专供 App 用例)
```
→ **路由是"按用例类型选模块"，硬编码在代码结构里。**

**你期望的路由**：
```
Project → Target/Platform → Engine Adapter → Playwright / Appium / 其他
```
→ 需要一个**适配器注册表 + 接口**。这个改造量在 rd-uitest-platform 上是**可控的**，因为它已经把引擎封装在 `app/*_method.py` 里，只差抽接口。

---

## 4. 候选对比表（按你指定的维度）

### 4.1 完整平台类候选

| 维度 | rd-uitest-platform | MokaTest | 流马 Liuma | Testver |
|---|---|---|---|---|
| 项目-元素-用例 | ⚠️ 项目✅ / 元素❌ / 用例✅ | ✅ **完整** | ✅ **完整** | ✅（产品内，不可见） |
| 多引擎 | ✅ **Playwright + Appium + uiautomator2** | ❌ 仅 Playwright | ✅ API/WebUI/AppUI | ✅ Web+Appium |
| 按项目路由引擎 | ⚠️ 按用例类型分模块 | ❌ | ✅ 引擎注册 | ✅（不可见） |
| Web 引擎 | Playwright | Playwright | Selenium 系 | Playwright 等 |
| 移动引擎 | **Appium + uiautomator2** | ❌ | Appium（Android/iOS） | Appium |
| 元素多端定位符映射 | ❌ | ❌ **单定位符 / Web-only 枚举**（附录 C.3） | ✅ | ⚠️ 自愈为主 |
| 用例编排 | 表格化步骤（20+ 字段/步） | **可视化画布 + 步骤双视图 + 录制插件** | 关键字驱动零代码 | 录制 + AI 注解 |
| 调试能力 | 实时结果推送（WebSocket） | **暂停/断点/执行到此处 + 热加载** | 本地引擎实时查看 | 实时流式输出 |
| 报告 | **Allure + 录屏 + 历史趋势** | Allure + MinIO 截图 | 七牛云截图 | 截图/视频/trace |
| 部署难度 | 中（MySQL+Redis+Nginx，Systemd 脚本齐备） | 低（**Docker Compose 一键**） | 中（需配七牛云/邮箱） | **低（npm 两行命令）** |
| License | ⚠️ **无 LICENSE 文件**（徽章自称 MIT） | ⚠️ **BSL 1.1** | ⚠️ **AGPL-3.0** | ❌ **闭源** |
| 社区活跃度 | 🟢 21 star，2026-10 仍提交 | 🟢 24 star，2026-10 活跃 | 🔴 停更 2.5 年 | 🟢 商业产品 |
| 二次开发成本 | **中低**（Python 全栈，结构清晰，含 CLAUDE.md） | 高（Java 5 模块，且需换栈） | **极高**（AGPL + 停更） | **不可行** |
| **推荐改造优先级** | **★★★ 首选底座** | ★★ 管理端/元素库参考 | ★ 仅架构参考 | ☆ 仅产品形态参考 |

### 4.2 引擎 / 适配层类候选

| 维度 | Wix Pilot | Toolium | Mops | maestro-runner | Zosma QA |
|---|---|---|---|---|---|
| 类型 | 适配层 + AI 驱动 | 统一驱动封装 | 统一驱动封装 | 移动执行器(CLI) | 零配置 QA 框架 |
| License | **MIT** | **Apache-2.0** | MIT/Apache（口径不一） | **Apache-2.0**（drv 二进制不开源） | Apache-2.0 |
| 活跃度 | 🟡 2026-02 | 🟡 2025-12 / PyPI 2026-04 | 🔴 2025-07 | 🟢 2026-10 | 🔴 2026-03 |
| Playwright | ✅ | ✅ Beta | ✅ sync | ✅（Web via CDP） | ✅ |
| Appium | ✅（WebdriverIO） | ✅ | ✅ | ✅（云真机） | ⚠️ 空壳包 |
| 统一抽象 | ✅ **FrameworkDriver 接口** | ✅ 配置选驱动 | ✅ **同用例切引擎** | ✅ `--driver` | ✅ 插件式 |
| 对你有用的点 | **适配器接口设计** | **配置驱动 + 兼容矩阵** | **Locator dataclass** | **驱动切换 + 报告** | AI agent 生成方式 |
| 直接用? | 借架构 | 谨慎（Beta） | 不建议（停更） | 可作移动备选（需 WSL） | 不建议 |

---

## 5. 推荐方案

### ✅ 方案：**组合改造 —— 以 rd-uitest-platform 为执行底座，做三处扩展**

**为什么不是"直接用一个"，也不是"自建"**：
- **不能自建**：rd-uitest-platform 已有 Playwright + Appium + uiautomator2 三引擎、项目/用例/步骤/报告/调度/通知/AI 全套，在 Python 生态下自建等价物至少是数月工作量。
- **不能"整体替换"**：没有任何单项目同时具备"多引擎 + 元素库 + 多端 Locator"。
- **改造 rd-uitest-platform 的改造量最小**：缺口清晰、边界明确、且它的代码结构（routers/services/app 三层）本身就为扩展留了位置。

**三处扩展（外科手术式）**：

| # | 扩展点 | 现状 | 改造内容 | 参考来源 |
|---|---|---|---|---|
| **A** | **元素库 + Locator 多端映射** | 元素内联在 `app_case_steps.element_type/element_text` | 新增 `element` 表 + `element_locator` 表（`element_id` + `platform` + `locator_type` + `locator_value`）；步骤行改为引用 `element_id`；支持一个逻辑元素挂 Web/Android/iOS 三套定位符 | 领域模型抄 **MokaTest** `Element.java` / `ElementController`；`Locator` 结构抄 **Mops** 的 dataclass（含自动定位类型判定）；自愈思路抄 MokaTest `AiLocatorHealService` |
| **B** | **引擎适配器注册表** | `routers/` 按用例类型硬分模块 | 定义 `EngineAdapter` 抽象接口（`start / stop / click / input / wait / assert / screenshot`），把 `PlaywrightMethod` / `AppiumMethod` / `Uiautomator2Method` 实现为 adapter 并注册；`Project.project_type` → adapter 查表 | 接口设计抄 **Wix Pilot** 的 `TestingFrameworkDriver`（MIT，接口干净）；配置驱动抄 **Toolium** |
| **C** | **混合应用（H5 套壳）上下文切换** | ⚠️ **原语已有，编排缺失**（2026-10-14 修正，见附录 C.5）：`AppiumMethod` 已实现 `get_contexts()` / `switch_to_context()` / `get_html()`，`test_case.context` 字段也已存在 | ① 补 Android 侧暴露（现有 context 动作只在 iOS 动作集 type=3）② 新建「切到 WebView 后由 Playwright/CDP 接管后续操作」的编排；原生控件仍走 Appium | Appium 官方 context 机制 + **Mops** 的"同一用例内切引擎"实践 |

**其余候选的定位（不改造，只取用）**：

| 项目 | 在本方案中的角色 |
|---|---|
| **MokaTest** | ① 元素库领域模型蓝本 ② 前端编排/调试体验蓝本 ③ 若将来要做"好看的管理端"，可直接参考其 Vue 3 + Arco Design 实现 |
| **Wix Pilot** | 引擎适配接口（`FrameworkDriver`）设计蓝本；可选：给平台加"自然语言驱动"能力 |
| **Toolium / Mops** | 配置驱动切换 + `Locator` 类型自动判定的实现参考 |
| **maestro-runner** | 移动端**备选执行器**：若要做大量 YAML 声明式移动回归，把它挂在适配层后面（注意 Windows 需 WSL） |
| **流马 Liuma** | **只读架构**：分布式"引擎注册到任意机器"的设计，是将来多设备并发的蓝图 |
| **Testver** | **只作产品形态参照**：体验目标的标尺（一个 UI 管多引擎该长什么样） |
| **Zosma QA** | AI agent 生成的轻量实现参考（可选，非必需） |

### 5.1 目标架构

```
┌────────────────────────────────────────────────────────────┐
│  统一管理层（FastAPI + Vue3）                                │
│  Project ─ Element ─ Locator(多端映射) ─ TestCase ─ Step      │
│  ├ 执行调度（APScheduler + Redis 队列）                       │
│  ├ 实时结果（WebSocket Pub/Sub）                              │
│  └ 报告（Allure + 截图/录屏/trace）                            │
├────────────────────────────────────────────────────────────┤
│  引擎适配层  EngineAdapterRegistry                            │
│  Project.project_type ──► 查表 ──► EngineAdapter              │
│  ┌──────────────┬──────────────┬──────────────────────┐     │
│  │ Playwright   │ Appium       │ (预留: maestro-runner │     │
│  │ Adapter      │ Adapter      │   / 其他)             │     │
│  │ Web / WAP    │ Android/iOS  │                       │     │
│  │              │ + WebView    │                       │     │
│  └──────────────┴──────────────┴──────────────────────┘     │
└────────────────────────────────────────────────────────────┘
```

---

## 6. 下一步源码阅读清单

按**优先级顺序**读，每项标注**要回答的具体问题**：

### P0 —— rd-uitest-platform（后端 `shangguanyi666/rd-testing-platform`）
| 文件 | 要回答的问题 |
|---|---|
| `TableStructure.sql` | ✅ 已读。确认无 element 表；确认 `project`/`test_case` 字段 |
| `app/playwright_method.py` | 有哪些原子动作？能否抽成统一 Action 集合？ |
| `app/appium_method.py` | ✅ 已读开头。`start_app()` 的 caps 构造、断言/等待/截图方法清单 |
| `app/uiautomator2_method.py` | uiautomator2 与 Appium 的职责边界在哪？（为何 Android 用 u2，iOS 用 Appium？） |
| `services/run_case_service.py` | ✅ 已读。`execute_case()` 如何按 case 分发到不同引擎？（第 50 行起） |
| `queue_runner.py` | Redis 队列协议；App 用例为何要独立队列 |
| `routers/app_case.py` + `services/app_case_service.py` | App 用例的 CRUD 与 `element_type/element_text` 的实际取值枚举 |
| `conftest.py` | ✅ 已读。pytest 侧如何注入 `--case_ids` / `--report_id` |
| `CLAUDE.md` | 项目自述的架构约定与代码风格 |
| `fe-uitest-platform` 前端 | 步骤编辑器如何呈现 `element_type/element_text`（改造成元素引用时的 UI 成本） |

### P1 —— MokaTest（`backEnd/platform-automation`）
| 文件 | 要回答的问题 |
|---|---|
| `domain/ui/Element.java` | 元素字段设计（是否已含多定位符？） |
| `element/ElementLocatorProcessor.java` | 定位符如何解析/回退。**2026-10-14 备注**：已从 `mokatest_full_schema.sql` 确证 `element` 表为**单定位符 + Web-only 枚举**（附录 C.3），本文件只需确认**运行时的解析/回退顺序**，不必再期待多端映射 |
| `element/AiLocatorHealService.java` | 自愈的输入输出契约（能否移植到 Python） |
| `controller/ElementController.java` | 元素 CRUD 的 API 契约 |
| `service/*Scene*` + `debug/PlaywrightDebugSession.java` | 编排执行 + 调试器实现 |
| `backEnd/sql/mokatest_full_schema.sql` | ✅ **已读**（2026-10-14，57 张表，见附录 C.3）。下一步：`test_step.step_detail` 的 JSON 结构、`plan`/`report` 的表设计 |

### P2 —— 适配层参考
| 文件 | 要回答的问题 |
|---|---|
| `wix-incubator/pilot` → `packages/core` 的 `TestingFrameworkDriver` 接口 | 适配器最小接口集 |
| `@wix-pilot/playwright` 与 `@wix-pilot/webdriverio-appium` | 两个实现的差异有多大（决定适配层厚度） |
| `CustomEnv/mops` → `Locator` dataclass 与 `DriverWrapper` | 定位类型自动判定的规则 |
| `Telefonica/toolium` 的驱动选择配置机制 | 配置驱动的 schema 设计 |
| `Chras-fu/Liuma-platform` 的引擎注册接口（只读） | 分布式引擎注册协议 |

---

## 7. 风险与待验证问题

### 🔴 高风险（动手前必须解决）

| # | 风险 | 说明 | 建议动作 |
|---|---|---|---|
| R1 | **rd-uitest-platform 授权不明** | Gitee API `license=None`，仓库**无 LICENSE 文件**，仅 README 徽章自称 MIT。**没有 LICENSE 文件 = 默认保留所有权利**，法律上不可直接商用改造 | **第一件事**：在 Gitee 提 Issue / 联系作者确认授权，或要求补 LICENSE 文件。前端 fe-uitest-platform 是 MulanPSL-2.0（明确可商用），后端必须确认 |
| R2 | **MokaTest 是 BSL 1.1** | 「将本软件作为托管/云服务提供给第三方」需商业授权。若你的平台将来对外提供服务，不能直接沿用其代码 | 只借鉴**设计思路与数据结构**，不复制代码；或走商业授权 |
| R3 | **流马 AGPL-3.0 传染性** | 二次开发必须整体 AGPL 开源 | **不复制任何 AGPL 代码**，只读架构文档 |
| R4 | **Testver 闭源** | 无法读源码、无法改造，且为商业产品 | 明确排除出改造候选 |

### 🟡 中风险 / 待验证

| # | 问题 | 需要验证什么 |
|---|---|---|
| R5 | **rd-uitest-platform 的 Appium 是真机还是模拟器？** | README 说「支持 Android 和 iOS 设备」，但 `appium_method.py` 里 `_check_adb_device()` 用 `adb devices` 判断 → **iOS 侧是否真跑通过？需要实测**。**2026-10-14 更新**：仍**未证实**——源码层 `UiAutomator2Method.connect()` 默认连 `127.0.0.1:21503`（模拟器端口），iOS 侧只有 `AppiumMethod` 一条路径且**仓库内无 iOS 设备/驱动配置约定**；在线演示站已下线（R9）无法间接验证。**判定：属"运行环境验证"，不阻塞架构设计**（附录 C.1 / C.8） |
| R6 | **Android 为何用 uiautomator2 而非 Appium？** | 若两套并存，元素定位符要维护两套（u2 的 resourceId vs Appium 的 accessibility id），**会加大 Locator 映射的复杂度**。**2026-10-14 已收敛**：✅ 确认 **Android 有两条并列路径（Appium / u2），iOS 只有 Appium**；两类的动作名与签名**不统一**（如 `input(element_type, element, text)` vs `input(element_type, value, text)`）。→ **技术方案的 Locator 表必须带 `engine`/`driver` 维度，不能只带 `platform`**（附录 C.2） |
| R7 | **iOS 自动化需要 macOS + Xcode** | 你的开发机是 **Windows**（`OS Version: win32`）→ **iOS 真机自动化无法在本机跑**，必须接 macOS 构建机或云真机（BrowserStack/Sauce Labs/LambdaTest）。这是**架构级约束，需提前决策**（已在**附录 B** 给出三方案对比与逐步推进顺序） |
| R8 | **前端 fe-uitest-platform 与后端版本是否配套** | 后端最后提交 2026-10-08，前端 2026-05-28 → **前端落后后端约 4.5 个月**，可能出现接口不匹配。需 clone 后实际联调。**2026-10-14 更新**：按"只借鉴架构不搬代码"，**不构成阻塞**；但**若决定 fork 后端骨架，必须先 clone 验证前后端契约**（附录 C.8） |
| R9 | **在线体验站可用性** | README 写 `http://14.103.196.193`（旧文档写 `shangguangroup.top`），需实际访问确认。**2026-10-14 已收敛**：❌ **已不可用**——`http://14.103.196.193` 返回 **HTTP 502**（10s 超时），`https://` 无法建连。→ **不能作为验收参照**；改以源码为准（附录 C.1） |
| R10 | **MokaTest 完整表结构未取到** | 本轮 GitHub API 未认证限流（60 次/时），`backEnd/sql/mokatest_full_schema.sql` 待补读。**2026-10-14 已收敛**：✅ **已取到**——`backEnd/sql/mokatest_full_schema.sql`，**109,682 字节 / 57 张表**，默认分支 `master`。关键结论见 **附录 C.3**（MokaTest 元素库是**单端单定位**，**不是**多端映射蓝本） |
| R11 | **Mops 许可证口径冲突** | GitHub 识别 MIT，README 写 Apache-2.0 → 若要用必须核对 `LICENSE` 文件原文 |
| R12 | **「QA Multipurpose Framework」不存在** | 未找到对应仓库，**已移出候选**。若你有确切链接请提供 |

### ✅ 已排除的错误前提（本报告修正）

1. ❌「rd-uitest-platform 支持项目-元素-用例」→ **部分错**：有项目、有用例，**没有元素**。
2. ❌「流马来源是 `Chras-fu/Liuma-agent`」→ **错**：`Liuma-agent` 是引擎端，平台端是 `Liuma-platform`。
3. ❌「Testver 适合研究其执行层路由」→ **不可行**：闭源，读不到源码。
4. ❌「Wix Pilot 在 `wix/pilot`」→ **错**：是 `wix-incubator/pilot`（`wix/pilot` 返回 404）。
5. ❌「maestro-runner 是 Maestro 的增强版」→ **不准**：它是 **Maestro 的开源替代实现**（README 原文 "Open-source Maestro alternative"）。
6. ❌「QA Multipurpose Framework 是候选」→ **无此仓库**。

---

## 8. 附录：信息出处

| 结论类型 | 来源 |
|---|---|
| 仓库 star/fork/license/时间戳 | GitHub REST API `GET /repos/{owner}/{repo}`、`/commits`（2026-10-13 实测） |
| Gitee 仓库元数据 | Gitee OpenAPI v5 `GET /repos/{owner}/{repo}`（2026-10-13 实测） |
| rd-uitest-platform 数据模型 | `gitee.com/shangguanyi666/rd-testing-platform` raw `TableStructure.sql`（35,576 字节，11 张表） |
| rd-uitest-platform 引擎封装 | raw `app/appium_method.py`（11,997 字节）、`conftest.py`（1,446 字节）、`services/run_case_service.py`（9,461 字节） |
| MokaTest 模块结构 | GitHub Contents API 递归抓取 `backEnd/platform-automation/src/main/java/...` |
| Testver 闭源判定 | npm registry `registry.npmjs.org/@testver/testver`（`repository: None`，unpackedSize 12.3 MB） |
| 流马架构与 AGPL 声明 | `github.com/Chras-fu/Liuma-platform` README 原文 |
| maestro-runner 驱动矩阵 | `raw.githubusercontent.com/devicelab-dev/maestro-runner/main/README.md` |
| Wix Pilot 驱动/接口 | `github.com/wix-incubator/pilot` README 原文 |
| Toolium | `pypi.org/project/toolium`、`github.com/Telefonica/toolium` |
| Mops | `github.com/CustomEnv/mops` README、`mops.readthedocs.io` |
| Zosma QA | npm `zosma-qa` / `@zosmaai/zosma-qa-cli`、Snyk、`github.com/zosmaai` |

> **说明**：本文中标注「未证实」「待验证」的条目，均未作为结论依据。所有"支持/不支持"的判断都基于实测的仓库元数据、README 原文或源码文件内容。

---

## 附录 B：本地调试环境方案（Windows 开发机）

> 回答一个实操问题：**"我只做平台，调试用 Chrome 浏览器够不够？还是必须用真机？"**
> 补充说明（2026-10-14）：按需借鉴架构、不搬代码，故 §7 中的 R1（rd-uitest-platform 授权不明）与 R2（MokaTest BSL 1.1）**不再构成阻塞**；R3（流马 AGPL）按"只读架构文档、不碰代码"执行。

### B.1 先分清两种「调试」——平台 ≠ 被测对象

| 你在调试什么 | 用 Chrome 够不够 | 说明 |
|---|---|---|
| **平台自身**（管理端页面、元素库、用例编排、报告展示） | ✅ **完全够** | 平台本身就是 Web 中台，Chrome 即最终运行环境 |
| **被测 Web 中台** | ✅ **完全够** | Playwright 驱动 Chromium，桌面 Chrome 就是生产环境 |
| **App 的原生部分**（弹窗、按钮、原生导航、权限弹窗） | ❌ **完全不行** | Chrome 是浏览器，无法识别/操作原生控件 |
| **App 内的 H5 / WebView 部分** | 🟡 仅开发期部分可行 | Chrome DevTools 可远程调 WebView 内页面，但"进入 WebView"这一步仍需 Appium |

**核心结论：App 用例 Chrome 一个都跑不了；但不等于必须买真机。**

### B.2 推荐的最小可用环境组合

| 端 | 引擎 | 本地环境 | 需要真机？ |
|---|---|---|---|
| Web / WAP | Playwright | 桌面 Chrome / Chromium | ❌ 不需要 |
| Android | Appium + uiautomator2 | Android Studio AVD 模拟器 | ❌ 不需要（开发/回归阶段足够） |
| iOS | Appium + XCUITest (WDA) | macOS + Xcode Simulator，或云真机 | 🟡 需要一台 Mac 或云账号，**不需要自购 iPhone** |
| 混合应用 WebView | Appium context 切换 | 模拟器 / 真机 + `chrome://inspect` | ❌ 不需要 |

### B.3 Android：模拟器就够，配置有讲究

1. **必须用 x86_64 镜像**，不要用 ARM 镜像（Windows 上慢到无法使用）。
2. **开启 WHPX 加速**（Windows Hypervisor Platform）或 AEHD，否则模拟器启动极慢。
3. 建议 AVD 规格：**API 33/34 + Google APIs 镜像**（不要选 Google Play 镜像，无法 root，调试受限）。
4. Appium 侧装驱动：`appium driver install uiautomator2`。
5. 若平台后续要做**并发执行**，一台机器可同时开 2–4 个 AVD（视内存），这正是「引擎注册到任意机器」的用武之地。

### B.4 iOS：Windows 上的三条路（含一个 2026 年的新变化）

**先明确硬事实**：iOS 模拟器是 Xcode 的组成部分 → **模拟器只能在 macOS 上运行**，Windows 无论怎么折腾都跑不了 iOS 模拟器。

| 方案 | 做法 | 成本 | 适用 |
|---|---|---|---|
| **A. 云真机**（推荐起步） | BrowserStack App Automate / Kobiton / LambdaTest 等，Appium 直连其 endpoint，本机只跑脚本 | 按量或订阅付费，无需硬件 | 想在 Windows 上立刻跑通 iOS |
| **B. 一台 Mac 做构建机** | Mac mini 装 Xcode + Appium，Windows 经局域网/CI 调用 | 一次性硬件投入 | 长期高频跑 iOS 回归 |
| **C. 非 macOS Host 直连真机**（新增能力） | Appium XCUITest driver **11.17+** 起有限支持 Windows/Linux host，通过 `appium-ios-remotexpc` + RemoteXPC 隧道连**真机** | 免费，但有前置条件 | 已有真机、且能解决 WDA 预装 |

⚠️ **方案 C 的四个限制**（依据 Appium 官方文档 <https://appium.github.io/appium-xcuitest-driver/11.17/guides/non-macos-hosts>）：
- **只支持真机，不支持模拟器**（模拟器仍是 macOS 独占）；
- 真机必须为 **iOS/tvOS 18 或更高**；
- **不支持自动选择设备**，必须显式指定 `appium:udid` + `appium:platformVersion`；
- **不支持默认的 xcodebuild 启动 WDA**，必须使用 `appium:usePreinstalledWDA`（WDA 已预装）或 `appium:webDriverAgentUrl`（外部托管 WDA）。

→ 换句话说：**编译并首次安装 WDA 仍然绕不开一次 Xcode**。所以"完全不需要任何 Mac"目前还不成立，但"不需要 Mac 常驻"是成立的。

### B.5 什么时候才真的必须上真机

| 场景 | 模拟器能否覆盖 |
|---|---|
| 弹窗、按钮、表单、导航、Toast、权限弹窗 | ✅ 可覆盖 |
| 指纹 / 人脸 / NFC / 蓝牙 / 相机 / 传感器 | ❌ 模拟器没有 |
| 真实性能、内存、耗电 | ❌ 模拟器数据无参考价值 |
| 厂商 ROM 定制行为（华为 / 小米 / OPPO 等） | ❌ 需要真机 |
| 推送通知、应用商店内购流程 | ❌ 需要真机 |
| 上架前最终验收 | ❌ 需要真机 |

**按你的目标（只关注 App 内部功能如弹窗、按钮，不做卸载/控制 App 等系统级操作）→ 开发和回归阶段一台真机都不需要，Android 模拟器全覆盖。**

### B.6 建议的推进顺序

1. **先跑通 Web**：Playwright + 桌面 Chrome，**零设备成本**，先把「元素库 + Locator 多端映射 + 适配器注册表」三处扩展在 Web 端验证完。
2. **再接 Android**：加 Appium 适配器 + AVD 模拟器，验证"按项目路由引擎"真的能切换。
3. **iOS 最后接**：此时适配器注册表已稳定，iOS 只是注册第三个 adapter；执行环境用云真机起步，避免过早投入硬件。

> 这个顺序正好与「引擎适配器注册表」的设计吻合：**先把两个引擎跑通、把注册表做对，第三个引擎就只是配置问题。**

---

## 附录 C：二次验证与结论更新（2026-10-14）

> **目的**：在动笔写《技术方案》前，把 §7 里仍标注「待验证」的条目收敛掉，并修正第一轮中**不够准确**的判断。
> **方法**：只读 raw / Contents API 实测**源码与建表语句**，不依赖二手描述；关闭了正文中所有"推测性"表述。
> **净结果**：推荐路线**不变**；但有 **5 处结论被修正或加强**，其中 3 处会直接改变《技术方案》的写法。

### C.1 待验证项收敛情况

| # | 原问题 | 二次验证结果 | 依据 |
|---|---|---|---|
| **R10** | MokaTest 完整表结构未取到 | ✅ **已取到**：`backEnd/sql/mokatest_full_schema.sql`，**109,682 字节 / 57 张表**，默认分支 `master` | GitHub Contents API（默认分支实测） |
| **R9** | 在线体验站是否可用 | ❌ **已下线**：`http://14.103.196.193` → **HTTP 502**（10s 超时）；`https://` 无法建连 | curl 实测 |
| **R6** | Android 为何用 uiautomator2 而非 Appium？ | ✅ **已收敛**：Android 有**两条并列路径**，iOS 只有 Appium；两类动作名/签名不统一 → **Locator 表必须带 engine 维度** | 源码 L20/L12 起 |
| **R5** | rd 的 Appium 是真机还是模拟器？iOS 真跑通过吗？ | ⚠️ **仍未证实**（演示站已下线，无法间接验证）→ 判定为「运行环境验证类」，**不阻塞架构设计** | 源码 + C.1 R9 |
| **R8** | 前后端版本是否配套 | ⚠️ 未实测（需 clone）；但按"只借鉴架构"**不构成阻塞** | — |

### C.2 rd-uitest-platform：两个移动引擎的职责边界（R6 收敛）⭐

实测 `app/appium_method.py`（11,997 B）与 `app/uiautomator2_method.py`（7,275 B）：

| | **`AppiumMethod`** | **`UiAutomator2Method`** |
|---|---|---|
| 类定义 | `app/appium_method.py` L20 | `app/uiautomator2_method.py` L12 |
| 启动方式 | `webdriver.Remote("http://127.0.0.1:4723/wd/hub", options)` + caps | 直连设备（adb），**无 caps** |
| 启动签名 | `start_app(platform_name, platform_version, device_name, app_package, app_activity, no_reset=True)` | `start_app(package_name, activity=None)` |
| **覆盖端** | **Android + iOS**（`platformName` 区分） | **仅 Android** |
| 连接 | Appium Server `:4723` | `connect()` → 如 `127.0.0.1:21503`（模拟器端口） |
| 独有能力 | `get_contexts()` / `switch_to_context()` / `get_html()`（**WebView 上下文**）· 录屏 · `hover` · `select` · `is_selected` | `element_list()` · `fix_orientation()` · `go_home()` / `go_back()` · 录屏 |
| 共性动作 | click · input · get_text · get_attribute · check_element_presence · is_displayed · swipe · long_press · scroll_to_element · screenshot | 同左，**但名称/签名有差异** |

**结论**：
1. 两个类**都已是"引擎封装"**，但**接口不统一**（典型：`input(element_type, element, text)` vs `input(element_type, value, text)`）→ **抽 `EngineAdapter` 接口是必要且可行**的，签名取两者**交集 + 归一化**即可。
2. ⚠️ **Android 双路径直接放大了 Locator 复杂度**：同一 Android 元素可能同时需要 **u2 定位语汇**（`text` / `resourceId` / `xpath` / `description`）与 **Appium 定位语汇**（`id` / `accessibility id` / `-android uiautomator`）→ **Locator 表的维度是「platform × engine/driver」，不能只按 platform**。这是本轮最重要的建模修正之一。

### C.3 ⚠️ 重要修正：MokaTest 的元素库**不是**多端映射蓝本

拿到 `mokatest_full_schema.sql`（57 张表）后，`element` 表实测原文：

```sql
create table element (
  id, parent_id, element_name,
  element_type  enum('ELEMENT','FOLDER'),   -- 树形：元素 / 目录
  locator_type  enum('id','class','xpath','css','text','placeholder',
                     'role','test_id','label','title','alt'),   -- ← 11 种，全部 Web 定位
  locator_value text,                        -- ← 单个定位符
  sort, description, project_id, is_shared, is_deleted, ...
)
```

**关键事实**：
- `locator_type` + `locator_value` **各只有一个** → **一个元素只挂一个定位符**，是**单端单定位**模型。
- 11 个 `locator_type` 枚举值**全部是 Web 定位类型**（含 `test_id` = `data-testid`）→ **不含任何移动端类型**（无 `resource-id` / `accessibility id` / `uiautomator` / `-ios predicate`）。
- 另有 `element_type enum('ELEMENT','FOLDER')` + `parent_id` + `sort` → **树形元素库**；`is_shared` 区分共享/私有。

**对正文的修正**：

| 正文原说法 | 修正后 |
|---|---|
| §3.1「MokaTest 有 `ElementLocatorProcessor`，但**仅 Web 定位**」 | **更准确**：MokaTest 的**元素表本身**就是单定位符 + Web-only 枚举。它给的是「**单端元素库**」蓝本（命名规范、树形组织、共享/私有、软删除、定位类型枚举设计），**不是多端映射蓝本**。 |
| §4.1「元素多端定位符映射：MokaTest ⚠️ 仅 Web」 | **下调为 ❌**：MokaTest 在**多端向量上完全缺失** → **多端 Locator 映射必须从零设计**，不能照搬。 |
| §2.3「MokaTest 数据模型 项目→元素→用例→步骤 完整存在」 | 仍成立，但补**反向事实**：MokaTest 的 `project` 表**无任何平台/端类型字段**（只有 team_id / status / coverage / api_total / ui_total…），`scene` 表也只有 `scene_category enum('UI','API','MIXED')`、**无 Web/Android/iOS 维度**。→ **在"按端路由"这一维度上，rd-uitest-platform 反而更强**。 |

**顺带发现（对技术方案正向）**：
- MokaTest `test_step` 用 **`step_detail json`** 存步骤详情（富结构、易扩展），与 rd 的 `app_case_steps`（20+ 固定列）风格迥异 → 技术方案可考虑 **"固定列 + JSON 扩展" 混合模型**。
- `scene.scene_category enum('UI','API','MIXED')` 说明它已考虑**跨类型同场景**，但**跨端**没做。

### C.4 ✅ 重要更新：rd 的「统一动作字典」已经存在（改造量下调）

`playwright_method` 表**并非 Playwright 专用**，而是**跨引擎统一动作字典**（表名有误导性）。实测分布（去重后）：

| `type` | 含义 | 方法数 |
|---|---|---|
| 1 | web / wap | **31** |
| 2 | api | **1** |
| 3 | **iOS** | **30** |
| 4 | **Android** | **18** |
| 10 | **通用**（断言 / 数据库 / 上传 / exec / eval） | **20** |

**三个直接可用的结论**：
1. ✅ **统一 Action 语汇已经存在** → 《技术方案》里的 `EngineAdapter` 接口**可以直接对齐这套动作枚举**，不必从零定义动作集 → **B 扩展的改造量比第一轮估计更低**。
2. ⚠️ **iOS(30) 与 Android(18) 是两套不同动作集**：`获取上下文` / `切换到上下文` / `多指滑动` / `悬停` / `下拉选项框` **只在 iOS 集出现**；`向上滑动` / `向下滑动` / `返回元素列表` 为 **Android 独有**。→ **适配器接口必须处理"能力不对称"（capability matrix）**，不能假设两端一一对应。
3. ⚠️ **schema 缺陷**：`playwright_method` 建表语句里 **`type` 列被重复定义了两次**（同表两条 `type`，注释还不一致）→ 快速迭代痕迹，**改造前需先做一次 schema 清理**。

### C.5 ⚠️ 修正：扩展点 C（WebView）现状是「原语已有，编排缺失」

正文 §5 把扩展点 C 的现状写作「**无**」。**实测源码后修正**——`app/appium_method.py` **已内置 WebView 上下文原语**：

```python
def get_contexts(self):        # L174 → self.driver.contexts
def switch_to_context(self, context_name):   # L177 → self.driver.switch_to.context(...)
def get_html(self):            # L180
```

且 `test_case` 表**已有 `context json` 字段**；`playwright_method` 里也有 **`获取上下文` / `切换到上下文`** 两个动作（type=3）。

→ **修正后的现状 = "原语已有，编排缺失"**。真正的缺口是：
1. 上下文切换动作**只在 iOS 动作集（type=3）暴露，Android 集（type=4）没有** → 需补 Android 侧；
2. 切到 WebView 后，**没有"把后续操作路由给 Playwright/CDP"的机制**（现在仍用 Appium 操作 WebView）→ **这部分才是要新建的**。

**改造量因此下调**：从"新建上下文切换能力" → **"复用已有原语 + 补 Android 暴露 + 增加 Playwright 接管 WebView 的编排"**。

### C.6 ⚠️ 新增发现：rd 的「路由判据」是模糊且自相矛盾的（技术方案必须显式化）

实测建表语句与注释：

```sql
`project`.`type`                 COMMENT '1：PC端，2：WAP端'   -- 只有 2 个枚举值
`test_case`.`project_type`       COMMENT '1：PC端，2：WAP端'   -- 同样只有 2 个
`app_case_steps`.`project_type`  int default 1                -- 无注释
```

**矛盾**：项目/用例的 `type` 枚举里**根本没有 App 的取值**，但 `app_case` 模块、`app_case_steps` 表、Appium / u2 封装**都真实存在**。
→ 说明 **App 用例的判据并不在 `project.type`**，实际落在**动作字典的 `type` = 3/4**（iOS/Android）上 —— 即 **"用例里用到了 iOS/Android 动作 ⇒ 这是 App 用例"**，是**隐式推断**而非显式字段。

**这正是《技术方案》必须引入显式 `platform` / `engine` 字段的直接依据** —— 否则做"按项目路由引擎"时必然踩到同样的一致性坑。

### C.7 其它佐证（现状细节，对技术方案有用）

来自 `project` 表（rd）：

| 字段 | 含义 | 对方案的意义 |
|---|---|---|
| `notice_type` | **1:钉钉 2:企业微信 3:不通知** | ✅ **通知能力已具备**（项目级 + `notice_token`/`notice_secret`），与用户既有 httprunnerplatform 经验可复用 |
| `threads` / `timing` | 并发线程数 / 定时 | ✅ 调度已具备（APScheduler） |
| `host/port/user/password/database` | 数据库连接 | ✅ 供 **SQL 步骤**用，说明"UI + 数据校验"混合用例已在模型内 |
| `context` (test_case) | WebView 上下文配置 | ✅ 印证 C.5 |

**代码质量佐证**：Android 动作里出现 `判断元素知否存在`（"知否"应为"是否"）→ 与 C.4 的重复 `type` 列一致，均为快速迭代痕迹。

### C.8 仍未解决（需 clone 后实测，但不阻塞文档）

| # | 事项 | 为何文档阶段可先不解决 |
|---|---|---|
| R5 | iOS / Android 是否在真实设备跑通 | 属"运行环境验证"，不影响架构设计；方案按"适配器已就绪、需实测"处理 |
| R8 | 前端（2026-05-28）落后后端（2026-10-08）约 4.5 个月 | 只借鉴架构不搬代码 → 不阻塞；**若决定 fork 后端骨架，须先 clone 验证前后端契约** |
| R11 | Mops 许可证口径冲突（GitHub MIT vs README Apache） | 只用其 `Locator` **设计思路**，不用代码 → 不阻塞 |
| — | 在线体验站已 502 | 无法演示验证，改以源码为准 |

### C.9 结论更新汇总（相对第一轮的**净变化**）

| 项 | 第一轮结论 | 更新后 | 影响 |
|---|---|---|---|
| 推荐底座 | rd-uitest-platform | **不变，且证据更强** | — |
| 三处扩展 | A 元素库 / B 适配器 / C WebView | **不变，但 C 的改造量下调**（原语已有） | 工作量↓↓ |
| 元素库蓝本 | MokaTest（⚠️ 仅 Web） | **MokaTest 只能当"单端元素库"的结构蓝本，多端映射需从零设计** | **建模必须自研** |
| 适配器接口 | 需从零定义动作集合 | **下降**：已有跨引擎动作字典（type 1/2/3/4/10），接口可直接对齐；**但需处理能力不对称** | 工作量↓ |
| Locator 映射维度 | platform | **必须 platform × engine/driver**（Android 双路径） | **建模修正** |
| 路由模型 | 参考 rd 的 `project.type` | **必须显式新增 platform/engine 字段**（rd 现有判据隐式且自相矛盾） | **建模修正** |
| 授权风险 | R1/R2 高风险 | **不阻塞**（已确认"只借鉴架构"） | 阻塞解除 |

> **一句话**：二次验证没有推翻推荐路线，反而**印证了它**；同时把《技术方案》必须先解决的三个建模问题**提前暴露**出来 —— ① Locator 的 engine 维度、② 显式 platform/engine 字段、③ 适配器的能力不对称。这三点正是下一阶段文档的核心。

### C.10 本附录的证据来源

| 结论 | 来源（均为 2026-10-14 实测） |
|---|---|
| MokaTest 57 张表 / `element` 表结构 | GitHub Contents API `backEnd/sql/mokatest_full_schema.sql`（base64，109,682 B） |
| rd 两个移动引擎类 | Gitee raw `app/appium_method.py`（11,997 B）、`app/uiautomator2_method.py`（7,275 B） |
| rd 动作字典分布 | Gitee raw `TableStructure.sql`（35,576 B）中 `playwright_method` 的 INSERT 数据 |
| rd 路由字段矛盾 | 同上，`project` / `test_case` / `app_case_steps` 建表语句 |
| rd WebView 原语 | `app/appium_method.py` L174–L180 |
| 在线体验站 | curl `http://14.103.196.193` → HTTP 502 |
| 本地留档 | `research/mokatest_schema.sql`、`research/rd_tablestructure.sql`（供后续核查） |
