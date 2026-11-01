"""M3.2 端到端验收（可重复执行，不依赖 pytest）。

覆盖：
  A. 用例编排：新增/改/排序/删除 + 写入期校验（未知动作、seq 冲突、跨项目元素）
  B. 元素级截图：screenshot(target=element) → artifact 落库 → 文件可下载
  C. 报告幂等：连续两次生成仍只有 2 行（HTML + JSON）
  D. 用例集成员启用开关：禁用后执行不包含该用例
  E. 执行列表按用例集筛选
  F. 断言轮询：assert_visible 在真实浏览器上通过
  G. storage_state：执行结束写回登录态文件

用法：先启动后端（8000）与 fixture（8899），再
    python scripts/smoke_m32.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "backend", "data", "uitest.db")
FIXTURE = "http://127.0.0.1:8899"
TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  [OK]   {name}" + (f"  ({detail})" if detail else ""))
    else:
        failed.append(name)
        print(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))


def wait_execution(client: httpx.Client, execution_id: int, timeout: float = 90) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"{BASE}/executions/{execution_id}").json()
        if data["status"] in TERMINAL:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"执行 {execution_id} 超时未结束")


def expect_error(client: httpx.Client, method: str, url: str, **kwargs) -> tuple[int, dict]:
    resp = client.request(method, url, **kwargs)
    try:
        body = resp.json()
    except Exception:
        body = {}
    return resp.status_code, body


def main() -> int:
    client = httpx.Client(timeout=90)

    # ─────────────────────────── A. 用例编排 ───────────────────────────
    print("\nA. 用例编排（StepEditor 后端）")
    case = client.post(f"{BASE}/projects/1/cases", json={
        "title": "M3.2 编排验收用例", "description": "自动创建，可重复删除",
    }).json()
    case_id = case["id"]

    navigate = client.post(f"{BASE}/cases/{case_id}/steps", json={
        "action_key": "navigate", "params": {"url": f"{FIXTURE}/login.html"},
    })
    check("新增步骤省略 seq 时自动为 1", navigate.status_code == 201
          and navigate.json()["seq"] == 1, f"status={navigate.status_code}")
    step1 = navigate.json()

    typed = client.post(f"{BASE}/cases/{case_id}/steps", json={
        "action_key": "input", "element_id": 3, "params": {"text": "admin"},
        "output_var": "typed_user",
    })
    check("新增绑定元素的 input 步骤 seq=2", typed.status_code == 201
          and typed.json()["seq"] == 2, f"status={typed.status_code}")
    step2 = typed.json()

    patched = client.patch(f"{BASE}/cases/{case_id}/steps/{step2['id']}",
                           json={"params": {"text": "admin2"}})
    check("PATCH 步骤只改 params", patched.status_code == 200
          and patched.json()["params"]["text"] == "admin2"
          and patched.json()["action_key"] == "input")

    ordered = client.put(f"{BASE}/cases/{case_id}/steps/order",
                         json={"ordered_ids": [step2["id"], step1["id"]]})
    check("重排交换相邻 seq 不撞唯一键", ordered.status_code == 200
          and [s["id"] for s in ordered.json()["items"]] == [step2["id"], step1["id"]],
          f"status={ordered.status_code}")

    bad_action, bad_body = expect_error(
        client, "POST", f"{BASE}/cases/{case_id}/steps",
        json={"action_key": "no_such_action", "params": {}})
    check("未知动作被拒（422）", bad_action == 422
          and bad_body.get("error", {}).get("code") == "VALIDATION_ERROR",
          f"code={bad_body.get('error', {}).get('code')}")

    missing_url, _ = expect_error(
        client, "POST", f"{BASE}/cases/{case_id}/steps",
        json={"action_key": "navigate", "params": {}})
    check("params 缺必填字段被拒（422）", missing_url == 422)

    foreign, _ = expect_error(
        client, "POST", f"{BASE}/cases/{case_id}/steps",
        json={"action_key": "click", "element_id": 9999, "params": {}})
    check("绑定不存在的元素被拒（404）", foreign == 404)

    dup, dup_body = expect_error(
        client, "POST", f"{BASE}/cases/{case_id}/steps",
        json={"seq": 2, "action_key": "navigate", "params": {"url": "https://x"}})
    check("seq 冲突被拒（409）", dup == 409
          and dup_body.get("error", {}).get("code") == "STEP_SEQ_DUPLICATED")

    # ───────────────────── B. 元素级截图 + 产物 ─────────────────────
    print("\nB. 元素级截图与产物下载")
    shot_case = client.post(f"{BASE}/projects/1/cases", json={
        "title": "M3.2 元素级截图", "description": "自动创建",
    }).json()
    shot_case_id = shot_case["id"]
    client.post(f"{BASE}/cases/{shot_case_id}/steps", json={
        "action_key": "navigate", "params": {"url": f"{FIXTURE}/login.html"}})
    client.post(f"{BASE}/cases/{shot_case_id}/steps", json={
        "action_key": "screenshot", "element_id": 5,
        "params": {"target": "element"}})
    client.post(f"{BASE}/cases/{shot_case_id}/steps", json={
        "action_key": "assert_visible", "element_id": 5, "params": {},
        "timeout_ms": 6000})

    exec_created = client.post(f"{BASE}/executions", json={
        "project_id": 1, "case_ids": [shot_case_id]}).json()
    detail = wait_execution(client, exec_created["id"])
    check("元素级截图用例执行通过", detail["status"] == "PASSED",
          f"status={detail['status']}")

    artifacts = client.get(f"{BASE}/executions/{exec_created['id']}/artifacts").json()
    check("artifact 已落库（>=1 条）", artifacts["total"] >= 1,
          f"total={artifacts['total']}")

    if artifacts["items"]:
        item = artifacts["items"][0]
        check("artifact 返回可访问 URL 且不含服务器路径",
              item["url"].startswith(f"/api/v1/executions/{exec_created['id']}/artifacts/")
              and "path" not in item)
        download = client.get(f"http://127.0.0.1:8000{item['url']}")
        check("artifact 下载返回 200 + image/png",
              download.status_code == 200
              and download.headers.get("content-type", "").startswith("image/png")
              and len(download.content) > 1000,
              f"{download.status_code}, {len(download.content)} bytes")

    html = client.get(f"{BASE}/executions/{exec_created['id']}/report?format=html").text
    check("报告 HTML 中的截图链接指向 API 路径",
          f"/api/v1/executions/{exec_created['id']}/artifacts/" in html)
    check("报告默认 inline（不是 attachment）",
          "inline" in client.get(
              f"{BASE}/executions/{exec_created['id']}/report?format=html").headers
          .get("content-disposition", ""))

    # ───────────────────────── C. 报告幂等 ─────────────────────────
    print("\nC. 报告幂等（GAP-35）")
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("delete from report where execution_id=?", (exec_created["id"],))
    conn.commit()
    conn.close()

    # 第一次 GET：报告不存在 → 补生成（两条 insert）
    client.get(f"{BASE}/executions/{exec_created['id']}/report?format=json")
    # 人为删掉 HTML 行，再要 HTML → JSON 走 update、HTML 走 insert（覆盖 upsert 两支）
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("delete from report where execution_id=? and format='HTML'",
                 (exec_created["id"],))
    conn.commit()
    conn.close()
    client.get(f"{BASE}/executions/{exec_created['id']}/report?format=html")

    conn = sqlite3.connect(DB, timeout=10)
    report_rows = conn.execute(
        "select format, count(*) from report where execution_id=? group by format order by format",
        (exec_created["id"],)).fetchall()
    conn.close()
    check("两条分支后每种格式仍只有 1 行", report_rows == [("HTML", 1), ("JSON", 1)],
          str(report_rows))

    # ────────────────── D. 用例集成员启用开关 ──────────────────
    print("\nD. 用例集成员启用开关（GAP-38）")
    client.post(f"{BASE}/suites/1/cases", json={"case_ids": [shot_case_id]})
    toggled = client.patch(f"{BASE}/suites/1/cases/1", json={"enabled": False})
    check("禁用成员返回 enabled=False", toggled.status_code == 200
          and toggled.json()["enabled"] is False)

    run = client.post(f"{BASE}/suites/1:run")
    check("用例集运行返回 202", run.status_code == 202, f"status={run.status_code}")
    suite_detail = wait_execution(client, run.json()["id"])
    executed_cases = {c["case_id"] for c in suite_detail.get("cases", [])}
    check("禁用的用例不在本次执行中", 1 not in executed_cases,
          f"executed={sorted(executed_cases)}")
    check("启用的用例仍在本次执行中", shot_case_id in executed_cases)

    # 恢复成员启用，避免污染后续手工验证
    client.patch(f"{BASE}/suites/1/cases/1", json={"enabled": True})

    # ────────────────── E. 执行列表按用例集筛选 ──────────────────
    print("\nE. 执行列表按用例集筛选（GAP-39）")
    filtered = client.get(f"{BASE}/executions", params={
        "project_id": 1, "suite_id": 1}).json()
    check("筛选结果全部属于该用例集",
          all(e["suite_id"] == 1 for e in filtered["items"]) and filtered["total"] >= 1,
          f"total={filtered['total']}")
    empty = client.get(f"{BASE}/executions", params={
        "project_id": 1, "suite_id": 999999}).json()
    check("不存在的用例集返回空列表", empty["total"] == 0)

    # ───────────────────── F. 断言轮询（真实浏览器）─────────────────────
    print("\nF. 断言轮询（GAP-03）")
    # 1) 元素已可见 + timeout_ms=1 → 不该因为窗口小就误判失败
    visible_case = client.post(f"{BASE}/projects/1/cases", json={
        "title": "M3.2 断言正向", "description": "自动创建"}).json()
    client.post(f"{BASE}/cases/{visible_case['id']}/steps", json={
        "action_key": "navigate", "params": {"url": f"{FIXTURE}/login.html"}})
    client.post(f"{BASE}/cases/{visible_case['id']}/steps", json={
        "action_key": "assert_visible", "element_id": 5, "params": {},
        "timeout_ms": 1})
    visible_exec = client.post(f"{BASE}/executions", json={
        "project_id": 1, "case_ids": [visible_case["id"]]}).json()
    visible_detail = wait_execution(client, visible_exec["id"])
    check("已可见元素在 timeout_ms=1 下仍通过", visible_detail["status"] == "PASSED",
          f"status={visible_detail['status']}")

    # 2) assert_not_exists 对确实存在的元素 → 轮询到窗口结束 → FAILED（不是 ERROR）
    negative_case = client.post(f"{BASE}/projects/1/cases", json={
        "title": "M3.2 断言反向", "description": "自动创建"}).json()
    client.post(f"{BASE}/cases/{negative_case['id']}/steps", json={
        "action_key": "navigate", "params": {"url": f"{FIXTURE}/login.html"}})
    client.post(f"{BASE}/cases/{negative_case['id']}/steps", json={
        "action_key": "assert_not_exists", "element_id": 5, "params": {},
        "timeout_ms": 120})
    negative_exec = client.post(f"{BASE}/executions", json={
        "project_id": 1, "case_ids": [negative_case["id"]]}).json()
    negative_detail = wait_execution(client, negative_exec["id"])
    step_status = negative_detail["cases"][0]["steps"][-1]["status"]
    check("断言超时判为 FAILED（不是 ERROR）", negative_detail["status"] == "FAILED"
          and step_status == "FAILED", f"status={negative_detail['status']}")

    # ───────────────────── G. storage_state ─────────────────────
    print("\nG. 登录态复用（GAP-06）")
    state_path = os.path.join(ROOT, "backend", "artifacts", "_smoke_state.json")
    if os.path.exists(state_path):
        os.remove(state_path)
    conn = sqlite3.connect(DB)
    conn.execute(
        "update execution_target set options=? where id=1",
        (json.dumps({"viewport": {"width": 1280, "height": 800},
                     "save_storage_state": state_path}),))
    conn.commit()
    conn.close()

    state_exec = client.post(f"{BASE}/executions", json={
        "project_id": 1, "case_ids": [shot_case_id]}).json()
    wait_execution(client, state_exec["id"])
    check("执行结束写出 storage_state 文件",
          os.path.exists(state_path) and os.path.getsize(state_path) > 10,
          f"exists={os.path.exists(state_path)}")

    conn = sqlite3.connect(DB)
    conn.execute("update execution_target set options=? where id=1",
                 (json.dumps({"viewport": {"width": 1280, "height": 800}}),))
    conn.commit()
    conn.close()
    if os.path.exists(state_path):
        os.remove(state_path)

    # ─────────────────────────── 清理 ───────────────────────────
    print("\n清理")
    for cid in (case_id, shot_case_id, visible_case["id"], negative_case["id"]):
        client.delete(f"{BASE}/cases/{cid}")
        client.delete(f"{BASE}/suites/1/cases/{cid}")
    print("  已软删本次创建的 4 个用例并移出用例集")

    print("\n" + "=" * 62)
    total = passed + len(failed)
    print(f"结果：{passed}/{total} 通过")
    if failed:
        print("失败项：")
        for name in failed:
            print("  -", name)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
