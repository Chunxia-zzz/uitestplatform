"""M3.8 端到端验收：网络 mock / 下载产物化 / iframe 按元素 / 执行级变量。

用法：先起后端(8000) + fixture(8899)，然后
    python scripts/smoke_m38.py

判定标准对应 specs/001-web-exec-capabilities/spec.md 验收场景（V1–V12）：
    V1–V3  mock 全链路 + 泄漏检查（US1 场景 1/4 · SC-001/SC-002）
    V4     解除 mock 恢复真实接口（US1 · wait_for_response）
    V5     中断型 mock（US1 场景 2）
    V6–V7  下载产物化 + 产物取回一致（US2 · SC-003）
    V8–V9  iframe 按元素：原序 + 调换序（US3 · SC-004）
    V10    互斥 422（US3 场景 3，写入口）
    V11    执行级变量跨用例共享（US4 场景 1/2 · SC-005）
    V12    缺省 scope 对照：变量缺失保留字面量（US4 场景 3，向后兼容）
"""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://127.0.0.1:8000/api/v1")
FIXTURE = "http://127.0.0.1:8899"

RUN = f"m38-{int(time.time())}"

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


# ─────────────────────────── 资源构造 helpers ───────────────────────────
def add_step(client: httpx.Client, case_id: int, seq: int, action_key: str,
             *, element_id: int | None = None, **params) -> None:
    body: dict = {"action_key": action_key, "seq": seq, "params": params}
    if element_id is not None:
        body["element_id"] = element_id
    r = client.post(f"{BASE}/cases/{case_id}/steps", json=body)
    assert r.status_code in (200, 201), f"add_step {action_key} -> {r.status_code} {r.text[:200]}"


def make_element(client: httpx.Client, project_id: int, name: str,
                 loc_type: str, value: str) -> int:
    r = client.post(f"{BASE}/projects/{project_id}/elements",
                    json={"element_name": name})
    element_id = r.json()["id"]
    lr = client.post(f"{BASE}/elements/{element_id}/locators", json={
        "platform": "WEB", "engine_key": "*", "locator_type": loc_type,
        "locator_value": value, "priority": 1})
    assert lr.status_code in (200, 201), f"locator -> {lr.status_code} {lr.text[:200]}"
    return element_id


def make_case(client: httpx.Client, project_id: int, title: str) -> int:
    r = client.post(f"{BASE}/projects/{project_id}/cases", json={"title": title})
    return r.json()["id"]


def run_and_wait(client: httpx.Client, *, project_id: int,
                 case_ids: list[int] | None = None, suite_id: int | None = None,
                 timeout: float = 120) -> dict:
    body: dict = {"project_id": project_id}
    if case_ids:
        body["case_ids"] = case_ids
    if suite_id:
        body["suite_id"] = suite_id
    r = client.post(f"{BASE}/executions", json=body)
    assert r.status_code == 202, f"submit -> {r.status_code} {r.text[:300]}"
    exec_id = r.json()["id"]
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"{BASE}/executions/{exec_id}").json()
        if data["status"] in ("PASSED", "FAILED", "ERROR", "CANCELLED"):
            return data
        time.sleep(1)
    raise TimeoutError(f"execution {exec_id} not finished in {timeout}s")


def step_results(client: httpx.Client, exec_id: int) -> list[dict]:
    """展开 detail 响应的 cases[].steps 为平铺列表。"""
    data = client.get(f"{BASE}/executions/{exec_id}").json()
    rows: list[dict] = []
    for case in data.get("cases") or []:
        for step in case.get("steps") or []:
            rows.append({**step, "case_id": case.get("case_id")})
    return rows


def main() -> int:
    client = httpx.Client(timeout=120)

    # ───────────── 项目与公共元素 ─────────────
    project = client.post(f"{BASE}/projects", json={
        "name": "M3.8 冒烟", "code": RUN,
        "platform": "WEB", "engine_key": "playwright"}).json()
    pid = project["id"]

    el_out = make_element(client, pid, "接口输出", "testid", "api-out")
    el_reload = make_element(client, pid, "重新请求按钮", "testid", "reload")
    el_dl = make_element(client, pid, "下载链接", "testid", "download-link")
    el_pay_frame = make_element(client, pid, "结算面板iframe", "css", "iframe#pay")
    el_pay_amount = make_element(client, pid, "应付金额", "testid", "pay-amount")
    el_main_flag = make_element(client, pid, "主文档标记", "testid", "main-flag")

    # ═════════ V1–V3 mock 全链路 + 泄漏检查 ═════════
    print("\nV1–V3 网络 mock 全链路与用例边界清理")
    case_mock = make_case(client, pid, "mock 生效")
    add_step(client, case_mock, 1, "mock_route",
             pattern="**/api/demo", json={"ok": True, "msg": "from-mock"})
    add_step(client, case_mock, 2, "navigate", url=f"{FIXTURE}/mock-demo.html")
    add_step(client, case_mock, 3, "get_text", element_id=el_out, output_var="t")
    add_step(client, case_mock, 4, "assert_contains", actual="${t}", expected="from-mock")

    case_leak = make_case(client, pid, "mock 不跨用例泄漏")
    add_step(client, case_leak, 1, "navigate", url=f"{FIXTURE}/mock-demo.html")
    add_step(client, case_leak, 2, "get_text", element_id=el_out, output_var="t2")
    add_step(client, case_leak, 3, "assert_contains", actual="${t2}", expected="from-real")

    data = run_and_wait(client, project_id=pid, case_ids=[case_mock, case_leak])
    check("V1 mock 生效：页面显示 from-mock（执行 PASSED）", data["status"] == "PASSED",
          f"status={data['status']}")
    rows = step_results(client, data["id"])
    leak_rows = [r for r in rows if r.get("case_id") == case_leak]
    check("V2 收集器/变量随用例推进（wait_for_response 通路就绪）",
          all(r["status"] in ("PASSED", "FAILED") for r in rows), f"{len(rows)} steps")
    check("V3 mock 不泄漏：用例 B 看到 from-real",
          all(r["status"] == "PASSED" for r in leak_rows),
          str([(r["seq"], r["status"]) for r in leak_rows]))

    # ═════════ V4 解除 mock 恢复真实 + wait_for_response ═════════
    print("\nV4 解除 mock 恢复真实接口")
    case_unmock = make_case(client, pid, "解除 mock 恢复")
    add_step(client, case_unmock, 1, "mock_route",
             pattern="**/api/demo", json={"ok": True, "msg": "from-mock"})
    add_step(client, case_unmock, 2, "navigate", url=f"{FIXTURE}/mock-demo.html")
    add_step(client, case_unmock, 3, "unmock_route", pattern="**/api/demo")
    add_step(client, case_unmock, 4, "click", element_id=el_reload)
    add_step(client, case_unmock, 5, "wait_for_response",
             pattern="**/api/demo", expect_status=200, output_var="resp")
    add_step(client, case_unmock, 6, "get_text", element_id=el_out, output_var="t3")
    add_step(client, case_unmock, 7, "assert_contains", actual="${t3}", expected="from-real")
    data = run_and_wait(client, project_id=pid, case_ids=[case_unmock])
    rows = step_results(client, data["id"])
    check("V4 解除后真实接口生效 + wait_for_response 命中",
          data["status"] == "PASSED",
          str([(r["seq"], r["status"], (r["message"] or "")[:60]) for r in rows
               if r["status"] != "PASSED"]))

    # ═════════ V5 中断型 mock ═════════
    print("\nV5 中断型 mock")
    case_abort = make_case(client, pid, "中断请求")
    add_step(client, case_abort, 1, "mock_route", pattern="**/api/demo", abort=True)
    add_step(client, case_abort, 2, "navigate", url=f"{FIXTURE}/mock-demo.html")
    add_step(client, case_abort, 3, "get_text", element_id=el_out, output_var="t4")
    add_step(client, case_abort, 4, "assert_contains", actual="${t4}", expected="请求失败")
    data = run_and_wait(client, project_id=pid, case_ids=[case_abort])
    check("V5 abort 后页面呈现失败态", data["status"] == "PASSED",
          f"status={data['status']}")

    # ═════════ V6–V7 下载产物化 ═════════
    print("\nV6–V7 下载产物化")
    case_dl = make_case(client, pid, "下载报表")
    add_step(client, case_dl, 1, "navigate", url=f"{FIXTURE}/download.html")
    add_step(client, case_dl, 2, "download_file", element_id=el_dl, output_var="fname")
    data = run_and_wait(client, project_id=pid, case_ids=[case_dl])
    check("V6 下载执行 PASSED", data["status"] == "PASSED", f"status={data['status']}")
    arts = client.get(f"{BASE}/executions/{data['id']}/artifacts").json()
    items = arts["items"] if isinstance(arts, dict) else arts
    dls = [a for a in items if a.get("kind") == "DOWNLOAD"]
    check("V7a 产物列表出现 DOWNLOAD", len(dls) == 1,
          str([(a.get("kind"), a.get("path", "")[-40:]) for a in items]))
    if dls:
        content = client.get(
            f"{BASE}/executions/{data['id']}/artifacts/{dls[0]['id']}").content
        check("V7b 取回内容一致且不带服务器路径",
              content == b"col1,col2\n1,2\n" and "path" not in (dls[0] or {}),
              f"{content[:30]!r} keys={sorted(dls[0].keys())}")

    # ═════════ V8–V9 iframe 按元素（顺序无关）═════════
    print("\nV8–V9 iframe 按元素进入")
    for tag, page in (("V8", "iframes.html"), ("V9", "iframes-swapped.html")):
        case_if = make_case(client, pid, f"iframe 按元素 {tag}")
        add_step(client, case_if, 1, "navigate", url=f"{FIXTURE}/{page}")
        add_step(client, case_if, 2, "switch_to_iframe", element_id=el_pay_frame)
        add_step(client, case_if, 3, "assert_visible", element_id=el_pay_amount)
        add_step(client, case_if, 4, "switch_to_iframe")
        add_step(client, case_if, 5, "assert_visible", element_id=el_main_flag)
        data = run_and_wait(client, project_id=pid, case_ids=[case_if])
        check(f"{tag} {'原序' if tag == 'V8' else '调换序'}页：进入→iframe 内断言→弹栈→主文档断言",
              data["status"] == "PASSED", f"status={data['status']}")

    # ═════════ V10 互斥 422（写入口）═════════
    print("\nV10 switch_to_iframe 绑元素与 index 互斥")
    case_mu = make_case(client, pid, "互斥校验")
    r = client.post(f"{BASE}/cases/{case_mu}/steps", json={
        "action_key": "switch_to_iframe", "seq": 1, "element_id": el_pay_frame,
        "params": {"index": 0}})
    check("V10 写入口拒绝互斥形态（4xx）", r.status_code in (400, 422),
          f"status={r.status_code} body={r.text[:120]}")

    # ═════════ V11–V12 执行级变量 ═════════
    print("\nV11–V12 执行级变量")
    case_set = make_case(client, pid, "设置执行级变量")
    add_step(client, case_set, 1, "set_variable",
             name="token", value="T-123", scope="execution")
    case_get = make_case(client, pid, "读取执行级变量")
    add_step(client, case_get, 1, "assert_equals", actual="${token}", expected="T-123")
    case_local = make_case(client, pid, "设置用例级变量")
    add_step(client, case_local, 1, "set_variable", name="local_var", value="L-1")
    case_check = make_case(client, pid, "用例级变量不跨用例")
    add_step(client, case_check, 1, "assert_matches",
             actual="${local_var}", pattern=r"\$\{local_var\}")
    data = run_and_wait(client, project_id=pid,
                        case_ids=[case_set, case_get, case_local, case_check])
    rows = step_results(client, data["id"])
    by_case = {r.get("case_id"): [s["status"] for s in rows if s.get("case_id") == r.get("case_id")]
               for r in rows}
    check("V11 execution 变量跨用例可见", by_case.get(case_get) == ["PASSED"],
          str(by_case.get(case_get)))
    check("V12 缺省 scope 行为不变（缺失保留字面量 → 用例级不跨用例）",
          by_case.get(case_check) == ["PASSED"], str(by_case.get(case_check)))

    # ═════════ 汇总 ═════════
    print(f"\n{'=' * 60}")
    print(f"M3.8 冒烟：{passed} passed, {len(failed)} failed")
    if failed:
        print("失败项：", "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
