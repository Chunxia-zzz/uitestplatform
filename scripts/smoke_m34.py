"""M3.4 端到端验收：URL + 动作 → 自动建项目/元素/用例/用例集 → 执行。

用法：先把后端(8000)、前端(5173, 可选)、fixture(8899) 起好，然后

    python scripts/smoke_m34.py

判定标准见 docs/UI自动化平台M3.4详细设计.md §5.2（V1–V8）。
"""
from __future__ import annotations

import os
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
FIXTURE = "http://127.0.0.1:8899"
TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

# 每次运行用唯一 code：这样"首次创建"与"幂等复用"两个分支都能被验证，
# 且不会受上一次运行残留的影响。
PROJECT_CODE = f"smoke-m34-{int(time.time())}"
CASE_TITLE = "登录主链路（scaffold）"
SUITE_NAME = "冒烟回归（scaffold）"

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


def build_payload(*, run: bool = True, code: str = PROJECT_CODE) -> dict:
    return {
        "project": {"name": "Scaffold 验收项目", "code": code,
                    "platform": "WEB", "engine_key": "playwright"},
        "url": f"{FIXTURE}/login.html",
        "target": {"name": "fixture 8899"},
        "elements": [
            {"key": "username", "name": "用户名输入框",
             "locators": [{"locator_type": "testid", "locator_value": "username"}]},
            {"key": "password", "name": "密码输入框",
             "locators": [{"locator_type": "testid", "locator_value": "password"}]},
            # 首条定位符故意写错，用来验证回退链在 scaffold 生成的用例里同样生效
            {"key": "submit", "name": "登录按钮",
             "locators": [
                 {"locator_type": "testid", "locator_value": "submit-not-exist"},
                 {"locator_type": "css", "locator_value": "#submit"},
             ]},
            {"key": "welcome", "name": "欢迎语",
             "locators": [{"locator_type": "testid", "locator_value": "welcome"}]},
        ],
        "actions": [
            {"action_key": "navigate", "params": {"url": "/login.html"}},
            {"action_key": "input", "element_key": "username",
             "params": {"text": "jerry"}},
            {"action_key": "input", "element_key": "password",
             "params": {"text": "s3cret"}},
            {"action_key": "click", "element_key": "submit", "params": {}},
            {"action_key": "wait_element", "element_key": "welcome",
             "params": {"state": "visible"}},
            {"action_key": "get_text", "element_key": "welcome",
             "output_var": "welcome_text"},
            {"action_key": "assert_contains", "params": {
                "actual": "${welcome_text}", "expected": "欢迎"}},
        ],
        "case": {"title": CASE_TITLE, "description": "由 scaffold 自动生成"},
        "suite": {"name": SUITE_NAME},
        "run": run,
    }


def wait_execution(client: httpx.Client, execution_id: int, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"{BASE}/executions/{execution_id}").json()
        if data["status"] in TERMINAL:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"执行 {execution_id} 超时")


def main() -> int:
    client = httpx.Client(timeout=120)

    # ───────────── V1：一次调用建全链 ─────────────
    print("\nV1 一键装配（项目 → 目标 → 元素 → 用例 → 用例集 → 执行）")
    resp = client.post(f"{BASE}/scaffold", json=build_payload())
    check("POST /scaffold 返回 200", resp.status_code == 200, f"status={resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:600])
        return 1
    data = resp.json()

    check("项目 id 存在且 created=true",
          data["project"]["id"] > 0 and data["project"]["created"] is True)
    check("执行目标 base_url 由 url 推导",
          data["target"]["base_url"] == FIXTURE, data["target"]["base_url"])
    check("4 个元素全部创建", len(data["elements"]) == 4
          and all(e["created"] for e in data["elements"]))
    check("7 个步骤", data["case"]["step_count"] == 7, str(data["case"]["step_count"]))
    check("用例集含 1 条用例", data["suite"]["case_count"] == 1)
    check("提交了执行", data["execution"] is not None and data["execution"]["id"] > 0)
    check("navigate 补了 wait_until 并给出 warning",
          any("wait_until" in w for w in data["warnings"]), str(data["warnings"]))

    case_id = data["case"]["id"]
    element_ids = {e["id"] for e in data["elements"]}

    # ───────────── V2：定位符落库 ─────────────
    print("\nV2 元素定位符")
    submit = next(e for e in data["elements"] if e["key"] == "submit")
    locators = client.get(f"{BASE}/elements/{submit['id']}/locators").json()
    total = sum(len(g["items"]) for g in locators["groups"])
    check("登录按钮有 2 条定位符（回退链）", total == 2, f"total={total}")

    # ───────────── V3：步骤绑定 ─────────────
    print("\nV3 步骤绑定")
    case_detail = client.get(f"{BASE}/cases/{case_id}").json()
    steps = case_detail["steps"]
    check("seq 与输入顺序一致", [s["seq"] for s in steps] == [1, 2, 3, 4, 5, 6, 7])
    check("元素步骤绑定到正确元素",
          all(s["element_id"] in element_ids for s in steps if s["element_id"]))
    check("非元素动作 element_id 为空",
          steps[0]["element_id"] is None and steps[6]["element_id"] is None)
    check("get_text 的输出变量已落列", steps[5]["output_var"] == "welcome_text")

    # ───────────── V4：执行结果 ─────────────
    print("\nV4 执行结果")
    detail = wait_execution(client, data["execution"]["id"])
    check("执行 PASSED", detail["status"] == "PASSED", f"status={detail['status']}")
    click_step = next(s for s in detail["cases"][0]["steps"] if s["action_key"] == "click")
    check("click 回退到第 2 条定位符", click_step["fallback_index"] == 1,
          f"fallback_index={click_step['fallback_index']}")
    check("used_locator_id 有值", click_step["used_locator_id"] is not None)
    assert_step = next(s for s in detail["cases"][0]["steps"]
                       if s["action_key"] == "assert_contains")
    check("断言用上了 get_text 的变量", assert_step["status"] == "PASSED")

    # ───────────── V5：报告 ─────────────
    print("\nV5 报告")
    report = client.get(f"{BASE}/executions/{detail['id']}/report?format=html")
    check("报告可访问且含用例集名",
          report.status_code == 200 and SUITE_NAME in report.text,
          f"{len(report.text)} bytes")

    # ───────────── V6：幂等 ─────────────
    print("\nV6 幂等（同输入再提交一次）")
    again = client.post(f"{BASE}/scaffold", json=build_payload()).json()
    check("项目复用（id 不变、created=false）",
          again["project"]["id"] == data["project"]["id"]
          and again["project"]["created"] is False)
    check("元素全部复用",
          [e["id"] for e in again["elements"]] == [e["id"] for e in data["elements"]])
    check("用例复用且步骤不翻倍",
          again["case"]["id"] == data["case"]["id"]
          and again["case"]["step_count"] == 7,
          f"steps={again['case']['step_count']}")
    check("用例集复用", again["suite"]["id"] == data["suite"]["id"])
    check("执行是新的（执行不可幂等）",
          again["execution"]["id"] > data["execution"]["id"])
    wait_execution(client, again["execution"]["id"])

    # ───────────── V7：失败不留垃圾 ─────────────
    print("\nV7 失败不残留")
    bad_code = f"smoke-m34-bad-{int(time.time())}"
    bad = client.post(f"{BASE}/scaffold", json=build_payload(code=bad_code) | {
        "url": "ftp://example.com/x"})
    check("非法 URL 返回 422", bad.status_code == 422, f"status={bad.status_code}")
    check("错误码是 SCAFFOLD_INVALID_URL",
          bad.json().get("error", {}).get("code") == "SCAFFOLD_INVALID_URL")

    projects = client.get(f"{BASE}/projects").json()["items"]
    check("非法输入没有留下项目", not any(p["code"] == bad_code for p in projects))

    unknown_key = client.post(f"{BASE}/scaffold", json=build_payload(code=f"{bad_code}-2") | {
        "actions": [{"action_key": "click", "element_key": "nope", "params": {}}]})
    check("未知元素 key 返回 422", unknown_key.status_code == 422)
    projects = client.get(f"{BASE}/projects").json()["items"]
    check("未知 key 也没有留下项目",
          not any(p["code"] in (f"{bad_code}-2",) for p in projects))

    # ───────────── V8：run=false ─────────────
    print("\nV8 只建资产不执行")
    dry = client.post(f"{BASE}/scaffold", json=build_payload(run=False)).json()
    check("execution 为 null", dry["execution"] is None)
    check("资产仍然齐全", dry["case"]["step_count"] == 7 and dry["suite"]["case_count"] == 1)

    # ───────────── 清理（按引用顺序逆序删）─────────────
    print("\n清理本次创建的数据")
    client.delete(f"{BASE}/suites/{data['suite']['id']}")
    client.delete(f"{BASE}/cases/{case_id}")
    for element in data["elements"]:
        client.delete(f"{BASE}/elements/{element['id']}")
    client.delete(f"{BASE}/projects/{data['project']['id']}")
    print("  已删除用例集 / 用例 / 元素 / 项目（软删）")

    print("\n" + "=" * 62)
    total_checks = passed + len(failed)
    print(f"结果：{passed}/{total_checks} 通过")
    for name in failed:
        print("  -", name)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
