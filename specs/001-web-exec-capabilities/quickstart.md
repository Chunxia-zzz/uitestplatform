# Quickstart: Web 执行能力补齐（M3.8）端到端验证

> 前置：后端 8000、fixture 静态站 8899（`python scripts/serve_fixtures.py`）、前端可选（API 驱动验证即可）。
> 冒烟脚本：`python scripts/smoke_m38.py`（覆盖本页全部场景，一一对应 spec 验收场景）。

## 1. 网络 mock 全链路（US1 / SC-001 / SC-002）

1. 对 fixture 站的演示页建用例：
   - S1 `mock_route`：pattern=`**/api/demo`，json=`{"ok": true, "msg": "from-mock"}`
   - S2 `navigate` 打开演示页（页面脚本 fetch 该接口并渲染结果）
   - S3 `assert_contains`：页面文本含 `from-mock`
   - S4 `unmock_route`：pattern=`**/api/demo`
   - S5 `wait_for_response`：pattern=`**/api/demo`，expect_status=200，output_var=`resp`
   - S6 `assert_contains`：`${resp.status}` 相关断言，且页面最终显示真实内容（fixture 站提供 `/api/demo` 真实响应 `from-real`）
2. 预期：执行 PASSED；把 S4 去掉后另建对照用例，确认页面始终显示 `from-mock`。
3. 泄漏检查（SC-002）：同一执行放入两条用例——A 设置 mock 不解除，B 打开同页断言看到**真实**内容 → PASSED 即自动清理生效。

## 2. 中断型 mock（US1 场景 2）

- `mock_route`：pattern=`**/api/demo`，abort=true → 页面展示失败态 → `assert_contains` 失败文案 → PASSED。

## 3. 下载产物化（US2 / SC-003）

1. fixture 站 `/downloads` 页提供 `download` 属性链接（服务端返回 `Content-Disposition: attachment`）。
2. 用例：`navigate` → `download_file` 绑定该链接，output_var=`fname`。
3. 预期：执行 PASSED；产物列表出现 DOWNLOAD 项；`GET /api/v1/executions/{id}/artifacts/{aid}` 取回文件内容与 fixture 源文件一致；响应中无服务器路径。

## 4. iframe 按元素（US3 / SC-004）

1. fixture 站双 iframe 页：两个 iframe 内容不同（`panel-alpha` / `panel-beta`），且提供调换顺序的变体页。
2. 用例（顺序无关）：元素 `结算面板容器` 定位符=css `iframe#pay` → `switch_to_iframe`（绑定该元素）→ `assert_visible` 绑定 iframe 内元素（testid=`pay-amount`）→ `switch_to_iframe`（无参，弹栈）→ `assert_visible` 主文档元素。
3. 预期：原序页与调换序页均 PASSED；绑元素+index 同给的步骤在创建时被 422 拒绝（错误信封 code=VALIDATION_FAILED）。

## 5. 执行级变量（US4 / SC-005）

1. 建套件含 A、B 两用例：A `set_variable`(name=`token`, value=`T-123`, scope=execution) → B `assert_equals`(actual=`${token}`, expected=`T-123`)。
2. 对照组：A 另设 `local_var`（缺省 scope），B 断言 `${local_var}` 渲染保持原样（变量缺失不静默变空——既有语义）→ 断言 actual 含 `${local_var}` 字面量。
3. 预期：两条均 PASSED；重跑执行结果一致（执行结束变量销毁）。

## 6. 回归门禁（SC-006）

```bash
cd /f/jerryyang-uitestplatform/backend && ../.venv/Scripts/python.exe -m pytest -q     # 275+ 基线全绿 + 新增用例
../.venv/Scripts/python.exe ../scripts/audit_status.py --check                          # 矩阵 vs 实现一致
bash scripts/ci_local.sh                                                                # 与 CI 同源检查
python scripts/smoke_m38.py                                                             # 本批次冒烟全绿
python scripts/smoke_m3.py && python scripts/smoke_m32.py && python scripts/smoke_m34.py \
  && python scripts/smoke_m35.py && python scripts/smoke_m36.py --phase full            # 既有五册冒烟零回归
```
