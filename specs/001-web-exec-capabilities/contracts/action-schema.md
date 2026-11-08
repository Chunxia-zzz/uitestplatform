# Contract: 动作 params_schema（M3.8 新增与扩展）

> 本批次无新 REST 端点；对外契约 = 用例编排协议（动作字典）。
> `additionalProperties: false` 为全字典既有约定；以下 JSON Schema 将由 `gen_seed_sql.py` 从 `action_keys.py` 生成为 seed（勿手工维护两份）。

## 新增动作 ×4

### 1. `mock_route` — 声明接口 mock（NETWORK / WEB / playwright / requires_element=0）

```json
{
  "type": "object",
  "properties": {
    "pattern": {"type": "string", "description": "URL 通配模式，如 **/api/demo"},
    "method": {"type": "string", "description": "HTTP 方法过滤，如 GET；缺省匹配全部"},
    "status": {"type": "integer", "description": "mock 响应状态码，默认 200"},
    "content_type": {"type": "string", "description": "响应 Content-Type，默认按 body 形态推断"},
    "body": {"type": "string", "description": "响应体文本；与 json 二选一"},
    "json": {"type": "object", "description": "响应体 JSON 对象；与 body 二选一"},
    "abort": {"type": "boolean", "description": "true=直接中断请求（status/body/json 被忽略）"}
  },
  "additionalProperties": false,
  "required": ["pattern"]
}
```

语义：声明后，匹配请求不再到达真实后端；同 `(pattern, method)` 重复声明后写覆盖；`abort=true` 时其余响应字段非法与 `json`/`body` 同时给出的组合在写入口拒绝。

### 2. `unmock_route` — 解除 mock（NETWORK / WEB / playwright / requires_element=0）

```json
{
  "type": "object",
  "properties": {
    "pattern": {"type": "string", "description": "必须与声明时完全一致"},
    "method": {"type": "string", "description": "必须与声明时完全一致（若声明时给了）"}
  },
  "additionalProperties": false,
  "required": ["pattern"]
}
```

语义：按 `(pattern, method)` 精确解除；不存在时步骤 ValidationFailed（拒绝静默成功）。用例边界会自动清理全部 mock（FR-004），本动作用于用例中途恢复真实接口。

### 3. `wait_for_response` — 等待/检索网络响应（NETWORK / WEB / playwright / requires_element=0）

```json
{
  "type": "object",
  "properties": {
    "pattern": {"type": "string", "description": "URL 通配模式"},
    "method": {"type": "string", "description": "HTTP 方法过滤"},
    "expect_status": {"type": "integer", "description": "期望状态码；给出则状态不符视为未命中，继续在窗口内轮询"},
    "output_var": {"type": "string", "description": "命中结果存入变量：{url, status, method}"}
  },
  "additionalProperties": false,
  "required": ["pattern"]
}
```

语义：在步骤 `timeout_ms` 窗口内轮询检索**自当前用例开始以来**收集的响应；命中即返回。超时失败，message 附最近 5 条响应（url+status）辅助排查模式写错。

### 4. `download_file` — 下载并产物化（ELEMENT / WEB / playwright / requires_element=1）

```json
{
  "type": "object",
  "properties": {
    "output_var": {"type": "string", "description": "保存后的文件名（含扩展名）存入变量"}
  },
  "additionalProperties": false
}
```

语义：点击步骤绑定元素并接管浏览器下载；文件保存为本次执行产物（kind=DOWNLOAD，出现在产物列表与报告）；未产生下载则超时失败；多文件只保存第一个。

## 扩展动作 ×2（冻结项向后兼容扩展，走变更留痕）

### 5. `set_variable`（DATA / 全平台内建）— props 新增可选 `scope`

```json
{
  "type": "object",
  "properties": {
    "name": {"type": "string"},
    "value": {},
    "scope": {"type": "string", "enum": ["case", "execution"], "default": "case",
              "description": "case=本用例内（默认，现状不变）；execution=本次执行内跨用例共享"}
  },
  "additionalProperties": false,
  "required": ["name", "value"]
}
```

不变量：`scope` 缺省时行为与现状逐字节一致；读取解析恒为"用例级优先、执行级兜底"；其余动作的 `output_var` 一律落用例级。

### 6. `switch_to_iframe`（NAVIGATION / WEB / playwright）— 新增"按元素进入"形态

```json
{
  "type": "object",
  "properties": {
    "index": {"type": "integer", "description": "按出现顺序进入（既有语义）；与绑定元素互斥；两者都不给=弹栈退出（D12）"}
  },
  "additionalProperties": false
}
```

形态判定（优先级从上到下）：
1. 步骤绑定元素 → 进入该 iframe（元素定位符必须命中 iframe 节点，否则 ValidationFailed）
2. `index` 给定 → 按顺序进入（既有语义）
3. 两者同给 → 写入口与执行口均 ValidationFailed
4. 都不给 → 弹栈（D12 语义不变）

## 能力矩阵同步（capabilities.py）

`_WEB` 集合 += {mock_route, unmock_route, wait_for_response, download_file}；`_APPIUM`/`_U2` 不变（这些动作不进入其矩阵，前端按项目引擎自动过滤）。`audit_status.py --check` 门禁自动覆盖。
