# UI 自动化平台 · M3.5 详细设计：页面元素自动扫描与确认落库

| 项 | 内容 |
|---|---|
| **文档编号** | D2-M3.5 |
| **版本** | v1.1 |
| **日期** | 2026-10-19 |
| **上游依赖** | D2-M2（元素库 / 定位符 / 定位类型字典）· D2-M3.4（一键接入）· 《URL抓取导入能力评估》 |
| **本文性质** | 施工图。回答"输入 URL 自动扫描页面元素，人工确认后批量落库" |
| **状态** | ✅ **已实现**（`scan_dom()` + 2 个端点 + `/scan` 页面），见 §7 实现记录 |

---

## 0. 目标与决策

### 0.1 一句话目标

> 用户输入一个 URL，平台自动扫描该页面可交互的元素，生成候选清单（含建议定位符与稳定性分级）；
> 用户在候选清单里**勾选确认**哪些有效，确认的元素自动落库到元素库。

### 0.2 关键决策 D28（放开 D14 边界）

| 决策 | 内容 |
|---|---|
| **D28** | 放开 D14 的边界：D14 原本"不做元素拾取器"，现**保留"不做交互式点选"**，但**允许"按 URL 批量扫描元素"**。定位符由扫描自动生成，但**必须人工确认后才落库**——"自动扫描、人工确认、确认即落库" |

> D14 原文是"不做拾取器（页面点选生成定位符）"。D28 把它收窄为"不做**点选**"，新增"**批量扫描**"这一路。两者不冲突：点选是"一次一个元素"，扫描是"一次一页元素"。

### 0.3 为什么必须"人工确认"，不能全自动

1. `element` 是**长期资产**（用例步骤靠 `element_id` 引用），自动入库 50 个 `div` 会让元素树不可用；
2. 定位符稳定性是**概率问题**（`class` 改版就断），机器只能给出分级，不能替人判断"这个值值得长期维护"；
3. 命名权在用户手里——自动命名会产出 `div-1…div-50` 这类垃圾名。

### 0.4 明确不做

| 不做 | 理由 |
|---|---|
| 交互式点选拾取器 | D14 的残留边界，不在本期 |
| 全自动直接落库 | 违背"人工确认"前提 |
| 扫描结果的版本快照 / 两次扫描对比 | 阶段二，本期不实现 |
| App 端扫描 | 仍只有桩适配器（M4） |

---

## 1. 处理流程

```
POST /projects/{id}/element-scan   { url, max_elements, include }
  │
  ├─ 解析目标（复用 target / base_url / url 覆盖）
  ├─ 起会话（SessionManager + Playwright）
  ├─ navigate → 等 networkidle
  ├─ scan_dom()（适配器诊断方法，不进 action_catalog）
  │      → 返回 [ {tag, name, text, attrs, locators, strength} ]
  ├─ 过滤（按 include / 去重 / 截断 max_elements）
  └─ 返回 candidates（**不落库**）+ stats + warnings
        │
        ▼
POST /projects/{id}/element-scan/import   { candidates: [ {name, locators:[...]} ] }
  │
  ├─ 逐个创建元素（parent_id=0，node_type=ELEMENT）
  ├─ 批量创建定位符（复用 create_bulk）
  └─ 返回 created / failed
```

**为什么拆成两个端点**：扫描是"只读探测"，导入是"写库"。中间隔一个人工确认，
天然是两个请求；合并成一个会把"看都不看就落库"变成默认行为。

### 1.1 扫描（只读）

| 环节 | 说明 |
|---|---|
| 目标解析 | 优先用请求里的 `url`；否则用项目默认 `execution_target.base_url`；都没有 → 422 |
| 会话 | `SessionManager` + Playwright；headless 沿用 `settings.headless` |
| 等待 | `wait_until="networkidle"`（SPA 需要），超时 `settings.verify_total_timeout_s` 兜底 |
| 扫描 | 适配器新诊断方法 `scan_dom()`（见 §2.2） |
| 过滤 | `include` 白名单（tag 集合，默认交互元素）；容器 `div/span/section` 默认**不进候选** |
| 去重 | 同一"可定位值"（如 testid）出现两次，只留第一个 |

### 1.2 导入（写库，人工确认后）

| 环节 | 说明 |
|---|---|
| 输入 | 用户在候选里勾选的子集，可改名、可删定位符 |
| 元素 | 逐个 `element_service.create`（`parent_id=0`，顶层） |
| 定位符 | 复用 `locator_service.create_bulk`（单元素 ≤50 条，逐条报告失败） |
| 结果 | `{ created: [...], failed: [...] }`；部分失败不中断（与 create_bulk 语义一致） |

---

## 2. 后端设计

### 2.1 模块划分

| 文件 | 职责 |
|---|---|
| `app/engines/base.py` | 新增诊断方法 `scan_dom()`（基类默认抛 `NotImplementedError`，桩适配器不实现） |
| `app/engines/adapters/playwright_adapter.py` | 实现 `scan_dom()` |
| `app/domain/scan.py`（新） | 候选分类、定位符生成优先级、稳定性分级（**纯函数，零依赖，可单测**） |
| `app/services/scan_service.py`（新） | 目标解析、会话编排、扫描、导入 |
| `app/schemas/scan.py`（新） | 请求/响应模型 |
| `app/api/v1/scan.py`（新） | `POST /element-scan` + `POST /element-scan/import` |
| `app/core/errors.py` | 新增 2 个错误码 |

### 2.2 `scan_dom()`：为什么放适配器

与 `probe_locator()` 同理（M2 F-M2-3）：**扫描是"平台自身能力"，不是"用例能编排的步骤"**，
所以：
- 不进 `action_catalog`（动作字典保持 51 条不变）；
- 放适配器层，因为抓取依赖引擎的 `page` 对象，且未来 App 端扫描（UiAutomator 控件树）也能在各自适配器实现。

```python
# 基类（默认不支持，桩适配器不实现）
async def scan_dom(self, ctx: ActionContext, *,
                   max_elements: int = 200) -> list[dict]:
    raise NotImplementedError(f"{self.key} 不支持页面扫描")
```

### 2.3 定位符生成优先级（`domain/scan.py`）

按下列顺序取第一条命中的方式作为"主定位符"，其余作为备选：

```
data-testid → id → name → role+aria-label → aria-label → placeholder
→ alt → title → href → src → text（叶子，长度 2~30）→ css（tag 限定 nth-of-type）
```

稳定性分级：

| 等级 | 条件 | 语义 |
|---|---|---|
| `strong` | testid / id / name | 页面改版基本不受影响 |
| `medium` | role / aria-label / placeholder / alt / title / href / src | 较稳 |
| `weak` | text / class | 改文案或改样式就可能断 |

### 2.4 候选过滤规则（默认）

**只保留"可能被操作/断言"的元素**，默认跳过：

- `script/style/meta/link/head/title/noscript/br`（结构噪音）
- `div/span/section/article/main/header/footer/nav/ul/li` 等**纯容器**（无交互、无唯一属性时）
- 不可见元素（`offsetWidth/offsetHeight/getClientRects` 全空）

例外：容器若带 `data-testid` 或 `id`，**保留**（它可能是"某区块"的锚点，用户自己判断）。

`include` 白名单（请求参数，可覆盖默认）：`text / image / link / form / button / other`。

### 2.5 命名策略

候选的 `name` 默认取**文本或可读属性**，人工确认时可改：

- 表单控件：`aria-label` > `placeholder` > `name` 属性 > tag 名；
- 链接/按钮：文本 > `title` > `aria-label` > tag 名；
- 图片：`alt` > `title` > "图片"。

---

## 3. 接口契约

### 3.1 扫描

```
POST /api/v1/projects/{project_id}/element-scan
```

请求：

```jsonc
{
  "url": "http://127.0.0.1:8899/todo.html",   // 可选；缺省用项目默认目标 base_url
  "max_elements": 200,                         // 可选，默认 200
  "include": ["text", "image", "link", "form", "button", "other"]  // 可选
}
```

响应（200，**不落库**）：

```jsonc
{
  "url": "http://127.0.0.1:8899/todo.html",
  "candidates": [
    {
      "key": "c1",                              // 本次扫描内唯一，供导入引用
      "tag": "input",
      "name": "新待办",
      "text": "",
      "strength": "strong",
      "locators": [
        { "locator_type": "testid", "locator_value": "new-todo", "primary": true },
        { "locator_type": "placeholder", "locator_value": "要做什么？" }
      ]
    }
  ],
  "stats": { "total": 8, "strong": 7, "medium": 0, "weak": 1, "skipped": 12 },
  "warnings": ["跳过 3 个纯容器 div（无可定位属性）"]
}
```

### 3.2 导入

```
POST /api/v1/projects/{project_id}/element-scan/import
```

请求（只包含**用户勾选**的候选，可改名/删定位符）：

```jsonc
{
  "candidates": [
    {
      "name": "添加按钮",
      "locators": [
        { "locator_type": "testid", "locator_value": "add" }
      ]
    }
  ]
}
```

响应（200）：

```jsonc
{
  "created": [
    { "name": "添加按钮", "element_id": 30, "locator_ids": [77] }
  ],
  "failed": [
    { "name": "xxx", "code": "ELEMENT_NAME_DUPLICATED", "message": "..." }
  ]
}
```

### 3.3 错误码（新增 2 个）

| 码 | HTTP | 含义 |
|---|---|---|
| `SCAN_TARGET_REQUIRED` | 422 | 既没给 url，项目也没有默认执行目标 |
| `SCAN_EMPTY_CANDIDATES` | 422 | 扫描结果为空（页面无法访问 / 无可见元素） |
| `SCAN_IMPORT_EMPTY` | 422 | 导入请求的 candidates 为空 |

---

## 4. 前端设计

新增页面 `/scan`（元素扫描）：

```
┌─ 1. 扫描 ────────────────────────────────────────────┐
│ 项目 [下拉]   URL [http://.../todo.html]  [开始扫描]   │
├─ 2. 候选清单（勾选确认）──────────────────────────────┤
│ ☑ 输入框        input   testid=new-todo    [强] [改名] │
│ ☑ 添加按钮      button  testid=add         [强] [改名] │
│ ☐ 标题          h1      text=待办清单      [弱]        │
│ …                                                    │
│ 已选 2 个 · [导入选中]                                │
├─ 3. 结果 ────────────────────────────────────────────┤
│ ✅ 导入 2 个元素（新增 / 复用）                        │
└──────────────────────────────────────────────────────┘
```

交互细节：

- 每行显示 tag、建议名、主定位符、稳定性标签（强/中/弱）；
- **默认只勾选"强/中"等级**，弱等级默认不勾（降低误导入）；
- 可展开看全部候选定位符，可删除某条；
- 导入成功后跳元素库，能看到新元素。

---

## 5. 测试与验收

### 5.1 单元测试

| # | 用例 | 断言 |
|---|---|---|
| 1 | `domain/scan.py` 优先级：testid > id > name | 返回的主定位符正确 |
| 2 | 稳定性分级：class/text 判 weak | — |
| 3 | 容器过滤：无属性 div 被跳过，带 testid 的保留 | — |
| 4 | 命名：input 取 placeholder，button 取文本 | — |
| 5 | `scan_dom` 桩适配器抛 NotImplementedError | — |
| 6 | 扫描无目标（无 url 无 target）→ 422 | 不产生会话 |
| 7 | 导入空 candidates → 422 | — |
| 8 | 导入：元素创建 + 定位符落库 + 幂等 | 重复导入同名元素报 `ELEMENT_NAME_DUPLICATED` |

### 5.2 端到端（`scripts/smoke_m35.py`）

真扫 `todo.html` + `login.html`：

| # | 检查 | 判定 |
|---|---|---|
| V1 | 扫描返回候选 | `stats.total > 0`，`candidates` 非空 |
| V2 | 主定位符正确 | todo 页「添加按钮」主定位是 `testid=add` |
| V3 | 强/中/弱分级 | 弱等级候选默认不导（脚本模拟勾选） |
| V4 | 导入落库 | `POST /element-scan/import` 返回 `created`，元素库能查到 |
| V5 | 幂等/冲突 | 同名再导 → `ELEMENT_NAME_DUPLICATED` 进 `failed` |
| V6 | 无目标 | 无 url 无 target 的项目 → 422 |

### 5.3 验收关键节点

1. **扫描不落库**：扫描接口调用后，元素库数量不变（这是"候选池"的边界）；
2. **主定位符可用**：扫出来的 `testid`/`id` 直接能通过「验证当前端」；
3. **确认才落库**：只有导入接口才会产生 `element` / `element_locator` 行；
4. **分级可信**：`class`/纯文本定位不会混进"强"级。

---

## 6. 对后续批次的接口冻结声明

| # | 冻结项 | 变更影响 |
|---|---|---|
| **FR60** | `POST /element-scan` 与 `/element-scan/import` 的请求/响应结构 | 前端与脚本全改 |
| **FR61** | 扫描**不落库**，导入**才落库**；两者是两个端点 | 合并会破坏"人工确认"前提 |
| **FR62** | `scan_dom()` 是诊断方法，**不进 action_catalog**（动作字典保持 51 条） | 字典纯洁性被破坏 |
| **FR63** | 定位符生成优先级顺序（§2.3） | 已导元素的定位方式会变 |
| **FR64** | 候选默认过滤规则（容器跳过，除非有 testid/id） | 扫描结果集变化 |

---

## 7. 实现记录（2026-10-19 交付）

### 7.1 落点

| 层 | 文件 | 说明 |
|---|---|---|
| 诊断方法 | `engines/base.py::scan_dom()`（基类默认抛 NotImplementedError）+ `playwright_adapter.py` 覆写 | 不进 action_catalog（FR62）；桩适配器不实现，运行时自然报"不支持" |
| 纯逻辑 | `domain/scan.py`（新） | 定位符优先级 / 稳定性分级 / 容器过滤 / 命名建议，**零依赖可单测** |
| 服务 | `services/scan_service.py`（新） | 目标解析（`_resolve_target`）、会话编排（复用 SessionManager）、导入（复用 element/locator service） |
| 端点 | `api/v1/scan.py`（新） | `POST /projects/{id}/element-scan` + `POST /projects/{id}/element-scan/import` |
| 前端 | `views/ScanView.vue`（新） | 勾选确认表格；默认只勾强/中；可改名/删定位符 |
| 测试 | `tests/unit/test_scan.py`（15 条）+ `scripts/smoke_m35.py`（15 项） | 见 §7.3 |

### 7.2 实现期修正

| # | 问题 | 修正 |
|---|---|---|
| **F-M3.5-1** | `form` 标签被当作可交互元素扫出来，自动命名成 "form"（无意义） | 把 `form/table/tr/td/th` 移入容器类：默认跳过，带 id/testid 时保留（是"表单锚点"，留给人判断） |
| **F-M3.5-2** | 执行目标（`execution_target`）**没有独立创建端点**（只有 GET），smoke 建项目后无法用 API 建 target | smoke 改用 `url` 参数直接扫描（更贴合"用户输入 URL"的需求）；target 管理缺口登记 GAP-42 |

### 7.3 验证结果

| 命令 | 结果 |
|---|---|
| `pytest -q` | **149 passed**（+15：优先级 5 / 分级 2 / 过滤 1 / 命名 2 / 去重 1 / 不可见 1 / 服务 4） |
| `scripts/smoke_m35.py` | **15/15**（V1 扫描 6 · V2 分级 1 · V3 导入 3 · V4 落库 2 · V5 冲突 1 · V6 无目标 2） |
| `scripts/smoke_m34.py` / `smoke_m32.py` | 30/30 · 24/24 回归 |
| `scripts/smoke_ui.py` | **11/11**（新增 `/scan` 页 + 扫描交互） |
| `lint-imports` / `alembic check` | 2 kept / 无差异 |

端到端实证（todo.html）：

- 扫描 8 个候选（强 7 · 弱 1 · 跳过 0），**元素数前后不变**（不落库验证）；
- 「添加」按钮主定位自动识别为 `testid=add`；
- 导入 7 个（只勾强/中）→ 元素库落库 7 个、每个 1 条定位符；
- 同名再导 → `ELEMENT_NAME_DUPLICATED` 进 `failed`（不中断）；
- 无 url 无 target → 422 `SCAN_TARGET_REQUIRED`。

### 7.4 已知限制

| 限制 | 说明 |
|---|---|
| 只支持 Web 端 | Appium/u2 的 `scan_dom()` 走基类默认（NotImplementedError），M4 实现 |
| 无扫描历史 | 每次扫描都是独立请求，不做"两次扫描对比"（阶段二） |
| 无登录态扫描 | 需要登录的页面要先给项目配带 `storage_state` 的执行目标 |
| 动态页等待固定 networkidle | 极端 SPA 可能仍等不到位；暂无自定义等待入口 |
| 同项目串行扫描 | 进程内锁，避免并发开多个浏览器；扫描耗时 = 打开页面 + networkidle |

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-10-19 | v1.0 初稿：D28 放开 D14 边界、scan_dom 诊断方法、扫描/导入两端点、FR60–FR64 | 用户确认"自动扫描 + 人工确认落库" |
| 2 | 2026-10-19 | **v1.1 已实现**：新增 §7 实现记录；修正 F-M3.5-1（form 归容器）/F-M3.5-2（target 无创建端点，登记 GAP-42） | `pytest` 149 passed；`smoke_m35.py` 15/15；`smoke_ui.py` 11/11 |
