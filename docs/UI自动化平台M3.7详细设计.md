# UI 自动化平台 M3.7 详细设计 · 飞书通知渠道（GAP-43）

| 项 | 内容 |
|---|---|
| **版本** | v1.0（2026-11-04） |
| **范围** | 仅通知渠道扩展：新增飞书自定义机器人；企微渠道行为不变；无前端改动、无表结构改动 |
| **依据** | GAP-43（《待办与缺口跟踪》）；D26（不做通知管理 UI）；D39（通知绝不影响执行）；飞书《自定义机器人使用指南》 |
| **决策** | **D41**：通知渠道由 `UIP_NOTIFY_CHANNEL` 单选（`wecom` / `feishu`），默认 `wecom` 保持向后兼容；飞书走 `interactive` 卡片 |

---

## 1. 目标与验收

### 1.1 目标

1. **渠道可切换**：同一个平台既能推企微也能推飞书，通过一个环境变量选择，不引入渠道管理 UI（D26）。
2. **飞书卡片**：执行终态推送 `interactive` 卡片（标题按状态着色 + 统计 + 报告按钮），比纯文本更易读。
3. **关键词兼容**：用户群机器人启用了「自定义关键词 = `UI自动化平台`」，消息必须稳定命中，否则飞书返回 `19024 Key Words Not Found`。
4. **失败隔离不变**：沿用 D39 —— fire-and-forget、超时、全异常吞掉、日志只记 `event=notify.failed`，绝不改变执行终态。
5. **企微零回归**：`UIP_NOTIFY_CHANNEL=wecom`（默认）时，现有 markdown 文案、掩码、测试端点三态、`smoke_m36` V6–V8 全部保持原样。

### 1.2 非目标（明确不做）

- 多渠道**同时**推送（fan-out）；per-project webhook；@成员；签名 / IP 白名单安全模式；
- 通知管理页面、通知历史、重试队列（D26 / D39）；
- 卡片按钮回调（飞书自定义机器人本身不支持回调）。

### 1.3 验收锚点

| # | 场景 | 预期 |
|---|---|---|
| V1 | `channel=feishu` + 有效 webhook → `POST /notifications:test` | 200；群里收到卡片；标题含「UI自动化平台」；响应含 `channel=feishu` + 掩码 |
| V2 | 关键词不匹配（模拟） | 502 `NOTIFY_SEND_FAILED`，detail 带飞书 `code=19024` |
| V3 | `channel=wecom`（默认）回归 | `smoke_m36` V6/V7/V8 与 `test_notify_service.py` 全绿，行为不变 |
| V4 | 当前渠道 webhook 为空 | 422 `NOTIFY_NOT_CONFIGURED` |
| V5 | 失败执行 + webhook 不可达 | 执行终态不变；日志仅 `event=notify.failed`；服务健康 |
| V6 | 掩码 | 响应/日志不出现 webhook 完整 token（`/hook/<uuid>` 只留前 4 位） |
| V7 | 质量门禁 | `pytest` 全绿；`lint-imports` 2 kept；CI 三 job 绿 |

---

## 2. 后端设计

### 2.1 配置（`app/core/config.py`）

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `UIP_NOTIFY_CHANNEL` | `wecom` | 渠道单选：`wecom` / `feishu`；非法值在启动时被 Pydantic `Literal` 拒绝 |
| `UIP_NOTIFY_WECOM_WEBHOOK` | `""` | 既有；空 = 该渠道禁用 |
| `UIP_NOTIFY_FEISHU_WEBHOOK` | `""` | 飞书自定义机器人 webhook（`https://open.feishu.cn/open-apis/bot/v2/hook/...`） |
| `UIP_NOTIFY_FEISHU_KEYWORD` | `UI自动化平台` | 机器人「自定义关键词」；非空时必须出现在卡片标题里 |
| `UIP_NOTIFY_ON` | `failure` | 既有门控：`none` / `failure` / `all` |
| `UIP_NOTIFY_TIMEOUT_S` | `5.0` | 既有 |
| `UIP_PUBLIC_BASE_URL` | `""` | 既有；空则卡片不带「查看报告」按钮 |

> **为什么默认仍是 wecom**：升级不能改变既有部署行为；用户切飞书只需改 `UIP_NOTIFY_CHANNEL=feishu`。

### 2.2 服务分层（`app/services/notify_service.py`）

```text
active_channel()                 # 归一化 + 小写；未知值按 wecom 处理（防御）
channel_webhook(channel)         # feishu → notify_feishu_webhook；否则 wecom
build_markdown(payload)          # 既有，纯函数，企微
build_feishu_card(payload, kw)   # 新增，纯函数，返回 card dict
send_markdown(webhook, text, t)  # 既有，企微，签名冻结
send_feishu(webhook, card, t)    # 新增，POST {"msg_type":"interactive","card":...}
notify_execution_result(payload) # 改为按 active_channel() 分派
```

**分派规则**（`notify_execution_result`）：

1. `channel = active_channel()`；`webhook = channel_webhook(channel)`；
2. webhook 为空 → 直接返回（全局禁用，不建任务）；
3. `should_notify(settings.notify_on, status)` 为假 → 返回；
4. 组消息体：飞书 `build_feishu_card`，企微 `build_markdown`；
5. `asyncio.create_task(_send_safe(...))`，强引用集合防 GC；异常只记 `event=notify.failed`。

### 2.3 飞书卡片结构（v1 经典结构，兼容 bot/v2 hook）

```json
{
  "msg_type": "interactive",
  "card": {
    "config": {"wide_screen_mode": true},
    "header": {
      "template": "red",
      "title": {"tag": "plain_text", "content": "UI自动化平台 · 执行失败"}
    },
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "**执行失败** 冒烟回归\n> 来源：用例集「冒烟回归」\n> 结果：通过 3 / 失败 1 / 异常 0 / 跳过 0\n> 耗时：42.3s\n> 执行：#123"}},
      {"tag": "action", "actions": [
        {"tag": "button", "text": {"tag": "plain_text", "content": "查看报告"},
         "url": "http://host:5173/executions/123/report", "type": "primary"}
      ]}
    ]
  }
}
```

- **状态 → header 模板**：`PASSED=green`、`FAILED=red`、`ERROR=orange`、`CANCELLED=grey`、未知 `blue`。
- **关键词命中点**：`header.title.content` 固定以 `{keyword} · ` 开头。飞书文档明确「自定义关键词只对 `text`、`title` 这类文本参数值生效」，标题属于该范围；若线上实测仍返回 `19024`，降级方案是在 `elements` 首位插入 `{"tag":"div","text":{"tag":"plain_text","content":keyword}}`（见 §5.2 实测记录）。
- **报告按钮**：`base_url` 与 `execution_id` 同时存在才加；否则整块省略，避免死链。
- **请求体大小**：单卡片远小于飞书 20 KB 限制。

### 2.4 响应判定与掩码

- 飞书 HTTP 200 也可能是业务失败：`code`（或兼容字段 `StatusCode`）不等于 0 → `NotifySendError(f"飞书 webhook code={code}")`；
- 非 2xx → `NotifySendError(f"飞书 webhook HTTP {status}")`；非 JSON → `NotifySendError("飞书 webhook 响应不是 JSON")`；
- `mask_webhook` 扩展：URL 含 `/hook/` 时保留到 `/hook/` + token 前 4 位 + `***`；含 `key=` 时沿用原逻辑（企微测试不受影响）。

### 2.5 文件清单

| 文件 | 动作 |
|---|---|
| `backend/app/core/config.py` | 加 `notify_channel` / `notify_feishu_webhook` / `notify_feishu_keyword` |
| `backend/app/services/notify_service.py` | 加卡片构建 / 飞书发送 / 渠道分派 / 掩码扩展；`send_markdown` 保持不变 |
| `backend/app/api/v1/notifications.py` | 按当前渠道发送；响应加 `channel`；错误 detail 带渠道与 code |
| `backend/app/core/errors.py` | `NotifyNotConfigured` 文案改为「当前通知渠道未配置 webhook」；**不新增错误码** |
| `backend/tests/unit/test_notify_feishu.py` | 新增（约 11 条） |
| `backend/tests/unit/test_notify_service.py` | 既有用例保持通过（必要时仅补 `channel=wecom` 显式设置） |
| `docs/UI自动化平台M3.7详细设计.md` | 本文档 |
| `docs/HANDOVER.md` / `docs/待办与缺口跟踪.md` / `README.md` / `docs/Web端能力与使用指南.md` | 收尾回填 |

---

## 3. 接口契约

### 3.1 `POST /api/v1/notifications:test`（仅响应增量）

请求不变：`{"content": "可选，≤2048"}`。

成功 200：

```json
{"sent": true, "channel": "feishu", "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/9f2c***"}
```

- `channel` 为**新增字段**，向后兼容；
- 飞书渠道的自定义 `content` 进入卡片正文；缺省文案仍为「UIP 通知测试消息」；
- 422 `NOTIFY_NOT_CONFIGURED` / 502 `NOTIFY_SEND_FAILED` 错误信封不变。

### 3.2 环境变量契约

见 §2.1。**约束**：`UIP_NOTIFY_CHANNEL` 只接受 `wecom` / `feishu`；changing it requires backend restart（无热加载，M3.6 既有语义）。

### 3.3 不变项

- 无新路由、无新错误码、无数据库变更、无 Alembic 迁移、无前端改动；
- 执行通知 payload 键（`execution_id / status / suite_name / counts / duration_ms`）不变；
- `send_markdown` 签名与企微 payload 不变（`smoke_m36` 依赖）。

---

## 4. 前端设计

**无改动。** 通知仍是部署期环境变量配置（D26 明确不做通知管理 UI）。
`/engines` 能力页不展示通知渠道（它只反映引擎与动作字典）。

---

## 5. 测试与验收

### 5.1 单元测试（`tests/unit/test_notify_feishu.py`）

| # | 用例 |
|---|---|
| 1 | `build_feishu_card` 标题含关键词、状态文案、header 颜色正确（FAILED→red） |
| 2 | 卡片正文含来源/结果/耗时/执行号；`base_url` 为空时无 action 块 |
| 3 | `PASSED` 卡片颜色 green、`CANCELLED` grey |
| 4 | `send_feishu` 成功（`code=0`）返回响应体 |
| 5 | `code=19024` → `NotifySendError` 且消息含 `19024` |
| 6 | HTTP 500 → `NotifySendError` |
| 7 | 非 JSON → `NotifySendError` |
| 8 | `notify_execution_result` 在 `channel=feishu` 时走 `send_feishu`（不碰 `send_markdown`） |
| 9 | `channel=wecom` 时仍走 `send_markdown`（回归） |
| 10 | 测试端点 `channel=feishu` 返回 `channel` 字段 + 掩码不含完整 token |
| 11 | 飞书掩码：`/hook/<uuid>` 只保留前 4 位 |

### 5.2 真实环境验收（需用户提供的群机器人）

1. `curl` 直连 webhook 发一条含关键词的文本，确认 `code=0`（验证网络与关键词）；
2. `backend/.env` 写入 `UIP_NOTIFY_CHANNEL=feishu` + webhook + keyword，重启后端；
3. `POST /notifications:test` → 群里收到卡片，响应 200；
4. 跑一条**失败**用例（`UIP_NOTIFY_ON=failure`）→ 群里收到红色失败卡片；执行终态仍 `FAILED`；
5. 记录实测结果（含关键词命中位置）；若 `19024` 则按 §2.3 降级方案修正并重测。

**实测记录（2026-11-04，用户提供的群机器人）：**

| 步骤 | 结果 |
|---|---|
| 直连 webhook 发含关键词文本 | HTTP 200，`code=0`（网络与关键词均 OK） |
| `POST /notifications:test`（channel=feishu） | 200 `{"sent":true,"channel":"feishu","webhook":"…/hook/***"}`；群里收到蓝色「UI自动化平台 · 通知测试」卡片 |
| 失败用例执行（exec #122） | 终态 `FAILED`；群里收到红色「执行失败」卡片（标题命中关键词，**无需降级方案**）；服务端无 `notify.failed` |
| 企微回归 `smoke_m36 --phase off` | 1/1（422 `NOTIFY_NOT_CONFIGURED`） |
| 企微回归 `smoke_m36 --phase bad` | 1/1（502 `NOTIFY_SEND_FAILED`） |
| 质量门禁 | `pytest` **225 passed + 1 skipped**；`lint-imports` 2 kept |

> 实测确认：`header.title.content` 中的关键词可满足飞书自定义关键词校验，§2.3 的降级方案未启用。

> **安全**：webhook 只写本地 `backend/.env`（已在 `.gitignore`），不进入仓库、文档、日志与测试断言；对外只展示掩码。

### 5.3 回归

- `pytest -q` 全绿（206 + 新增约 11）；
- `smoke_m36 --phase full`（企微 stub）+ `--phase off` 行为不变；
- `lint-imports` 2 kept；CI 三 job 绿。

---

## 6. 对后续 M 的接口冻结声明

1. **渠道枚举冻结**：`wecom` / `feishu`。新增渠道 = 新枚举值 + 新 builder + 新 sender + 测试，不改既有分派语义。
2. **签名冻结**：
   - `send_markdown(webhook: str, content: str, timeout_s: float = 5.0) -> dict`（企微，不可改）
   - `send_feishu(webhook: str, card: dict, timeout_s: float = 5.0) -> dict`（飞书）
   - `build_feishu_card(payload: dict, keyword: str = "UI自动化平台") -> dict`
3. **关键词语义**：非空关键词必须出现在卡片 `header.title`；为空则不注入。
4. **隔离语义不变**：通知永不阻塞、永不改变执行终态（D39）。
5. **不做**：多渠道并行、管理 UI、回调交互（D26 / D41）。

---

## 变更记录

| # | 日期 | 条目 | 依据 |
|---|---|---|---|
| 1 | 2026-11-04 | v1.0 初稿：渠道单选 + 飞书 interactive 卡片 + 关键词 + 掩码 + 11 条单测方案 | GAP-43；用户提供飞书群机器人（关键词 `UI自动化平台`）；飞书自定义机器人文档 |
