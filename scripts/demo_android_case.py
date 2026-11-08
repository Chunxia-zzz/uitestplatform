"""M4.1 星财富 Android 用例固化 demo（纯 REST，不依赖前端）。

它等价于在平台上手工做下面 7 步（也是「用例固化」的可执行说明）：

    1. POST /projects                         建 ANDROID + appium 项目
    2. POST /projects/{id}/execution-targets  建设备目标（udid / app_package）
    3. POST /projects/{id}/elements           建元素（自选 Tab / SPY 行 / 详情标题）
    4. POST /elements/{id}/locators           加 Android 定位符（含故意写错的首选，验证回退）
    5. POST /projects/{id}/cases              建用例
    6. POST /cases/{id}/steps                 写 5 个步骤
    7. POST /projects/{id}/suites → 加成员 → :run   固化为用例集并执行

前置：
    * 后端 8000 已启动（加载 M4.1 代码）
    * Appium Server 4723 已启动
    * 真机已连接、测试包已安装、屏幕已解锁
    * 设备序列号 / 包名可用环境变量覆盖：
        UIP_ANDROID_UDID / UIP_ANDROID_PACKAGE / UIP_ANDROID_ACTIVITY / UIP_APPIUM_URL

用法：
    NO_PROXY=127.0.0.1,localhost python scripts/demo_android_case.py

预期：5/5 步 PASSED；第 2 步 fallback_index=1（首选 resource_id 故意写错）。
重复执行：复用项目/目标/元素/用例/用例集，不重复创建。
"""
from __future__ import annotations

import os
import sys
import time

import httpx

API = os.environ.get("UIP_API_BASE", "http://127.0.0.1:8000/api/v1")
UDID = os.environ.get("UIP_ANDROID_UDID", "3149dfe3")
PACKAGE = os.environ.get("UIP_ANDROID_PACKAGE", "com.fosunhani.stock.debug")
ACTIVITY = os.environ.get("UIP_ANDROID_ACTIVITY", "com.fosunhani.stock.enter.activity.LauncherActivity")
APPIUM_URL = os.environ.get("UIP_APPIUM_URL", "http://127.0.0.1:4723")

PROJECT = {"name": "星财富 Android 演示项目", "code": "xcf-android-demo",
           "platform": "ANDROID", "engine_key": "appium"}
TARGET_NAME = "星财富测试包 · PJA110"
CASE_TITLE = "星财富 · 自选 → 个股详情"
SUITE_NAME = "星财富 Android 冒烟"

ELEMENTS = [
    ("自选 Tab", [
        # 首选故意写错，验证回退链（fallback_index=1）
        ("resource_id", "com.fosunhani.stock.debug:id/not_a_real_tab", 10),
        ("text", "自选", 20),
    ]),
    ("标普500ETF-SPDR 行", [("text", "标普500ETF-SPDR", 10)]),
    ("个股详情标题", [("text_contains", "标普500ETF-SPDR", 10)]),
]

STEPS = [
    {"action_key": "restart_app", "params": {}, "remark": "冷启动测试包到主界面"},
    {"action_key": "click", "element": "自选 Tab", "params": {}},
    {"action_key": "click", "element": "标普500ETF-SPDR 行", "params": {}},
    {"action_key": "assert_visible", "element": "个股详情标题", "params": {}},
    {"action_key": "screenshot", "params": {"target": "page"}},
]

TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}


def call(client: httpx.Client, method: str, path: str, **kwargs):
    resp = client.request(method, f"{API}{path}", **kwargs)
    return resp


def get_or_create_project(client: httpx.Client) -> dict:
    items = call(client, "GET", "/projects").json()["items"]
    for item in items:
        if item["code"] == PROJECT["code"]:
            print(f"   复用项目 #{item['id']}")
            return item
    resp = call(client, "POST", "/projects", json=PROJECT)
    resp.raise_for_status()
    project = resp.json()
    print(f"   新建项目 #{project['id']}")
    return project


def get_or_create_target(client: httpx.Client, project_id: int) -> dict:
    resp = call(client, "GET", "/execution-targets", params={"project_id": project_id})
    items = resp.json().get("items", []) if resp.status_code == 200 else []
    for item in items:
        if item["name"] == TARGET_NAME:
            print(f"   复用执行目标 #{item['id']}")
            target = item
            break
    else:
        body = {
            "name": TARGET_NAME, "platform": "ANDROID", "engine_key": "appium",
            "options": {
                "udid": UDID, "app_package": PACKAGE, "app_activity": ACTIVITY,
                "appium_url": APPIUM_URL, "no_reset": True,
                "new_command_timeout": 180, "auto_grant_permissions": True,
            },
        }
        resp = call(client, "POST", f"/projects/{project_id}/execution-targets", json=body)
        resp.raise_for_status()
        target = resp.json()
        print(f"   新建执行目标 #{target['id']}（{UDID} / {PACKAGE}）")
    return target


def find_element(client: httpx.Client, project_id: int, name: str) -> dict | None:
    resp = call(client, "GET", f"/projects/{project_id}/elements",
                params={"keyword": name})
    for item in resp.json().get("items", []):
        if item.get("element_name") == name:
            return item
    return None


def get_or_create_element(client: httpx.Client, project_id: int, name: str) -> int:
    found = find_element(client, project_id, name)
    if found:
        return found["id"]
    resp = call(client, "POST", f"/projects/{project_id}/elements",
                json={"parent_id": 0, "element_name": name, "node_type": "ELEMENT"})
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_locator(client: httpx.Client, element_id: int,
                   locator_type: str, value: str, priority: int) -> None:
    resp = call(client, "POST", f"/elements/{element_id}/locators", json={
        "platform": "ANDROID", "engine_key": "appium",
        "locator_type": locator_type, "locator_value": value, "priority": priority,
    })
    if resp.status_code not in (201, 409):
        resp.raise_for_status()


def get_or_create_case(client: httpx.Client, project_id: int) -> dict:
    items = call(client, "GET", f"/projects/{project_id}/cases").json()["items"]
    for item in items:
        if item["title"] == CASE_TITLE:
            print(f"   复用用例 #{item['id']}")
            return item
    resp = call(client, "POST", f"/projects/{project_id}/cases",
                json={"title": CASE_TITLE, "description": "M4.1 演示：由 demo_android_case.py 固化"})
    resp.raise_for_status()
    case = resp.json()
    print(f"   新建用例 #{case['id']}")
    return case


def ensure_steps(client: httpx.Client, case_id: int, element_ids: dict[str, int]) -> None:
    existing = call(client, "GET", f"/cases/{case_id}/steps").json()
    if existing.get("total", 0) > 0:
        print(f"   复用已有 {existing['total']} 个步骤（不重复写入）")
        return
    for index, step in enumerate(STEPS, start=1):
        body = {"seq": index, "action_key": step["action_key"], "params": step["params"]}
        if step.get("element"):
            body["element_id"] = element_ids[step["element"]]
        if step.get("remark"):
            body["remark"] = step["remark"]
        resp = call(client, "POST", f"/cases/{case_id}/steps", json=body)
        if resp.status_code != 201:
            print(f"   步骤 {index} 写入失败：HTTP {resp.status_code} {resp.text[:400]}")
            sys.exit(1)
    print(f"   写入 {len(STEPS)} 个步骤")


def get_or_create_suite(client: httpx.Client, project_id: int) -> dict:
    items = call(client, "GET", f"/projects/{project_id}/suites").json()["items"]
    for item in items:
        if item["name"] == SUITE_NAME:
            print(f"   复用用例集 #{item['id']}")
            return item
    resp = call(client, "POST", f"/projects/{project_id}/suites",
                json={"name": SUITE_NAME, "description": "M4.1 Android 冒烟"})
    resp.raise_for_status()
    suite = resp.json()
    print(f"   新建用例集 #{suite['id']}")
    return suite


def ensure_member(client: httpx.Client, suite_id: int, case_id: int) -> None:
    items = call(client, "GET", f"/suites/{suite_id}/cases").json()["items"]
    if any(item["case_id"] == case_id for item in items):
        return
    resp = call(client, "POST", f"/suites/{suite_id}/cases", json={"case_ids": [case_id]})
    resp.raise_for_status()


def wait_execution(client: httpx.Client, execution_id: int, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = call(client, "GET", f"/executions/{execution_id}").json()
        if data["status"] in TERMINAL:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"执行 {execution_id} 超时未结束")


def main() -> int:
    client = httpx.Client(timeout=120, trust_env=False)
    try:
        client.get(f"{API}/engines").raise_for_status()
    except Exception as exc:
        print(f"[前置条件] 后端不可访问：{API}（{exc}）")
        return 2

    print("1) 项目")
    project = get_or_create_project(client)
    pid = project["id"]

    print("2) 执行目标（设备 / App）")
    target = get_or_create_target(client, pid)
    call(client, "PATCH", f"/projects/{pid}", json={"target_id": target["id"]})
    print(f"   target #{target['id']} options={target.get('options')}")

    print("3) 元素")
    element_ids = {}
    for name, _ in ELEMENTS:
        element_ids[name] = get_or_create_element(client, pid, name)
    print(f"   {element_ids}")

    print("4) 定位符")
    for name, locators in ELEMENTS:
        for locator_type, value, priority in locators:
            ensure_locator(client, element_ids[name], locator_type, value, priority)
    print("   完成（含 1 条故意写错的 resource_id，用于验证回退链）")

    print("5) 用例")
    case = get_or_create_case(client, pid)

    print("6) 步骤")
    ensure_steps(client, case["id"], element_ids)

    print("7) 用例集 + 执行")
    suite = get_or_create_suite(client, pid)
    ensure_member(client, suite["id"], case["id"])
    resp = call(client, "POST", f"/suites/{suite['id']}:run")
    resp.raise_for_status()
    execution_id = resp.json()["id"]
    print(f"   执行 #{execution_id} 已入队，等待终态…")

    detail = wait_execution(client, execution_id)
    print(f"\n终态：{detail['status']}  "
          f"通过 {detail['passed']} / 失败 {detail['failed']} / 异常 {detail['errored']}")
    for group in detail.get("cases", []):
        print(f"  用例 #{group['case_id']} {group['title']}")
        for step in group.get("steps", []):
            print(f"    {step['seq']}. {step['action_key']:<15} {step['status']:<8} "
                  f"fallback={step.get('fallback_index')} {step.get('message') or ''}")

    report = call(client, "GET", f"/executions/{execution_id}/report",
                  params={"format": "json"})
    print(f"\n报告 JSON：HTTP {report.status_code}；"
          f"HTML：{API}/executions/{execution_id}/report?format=html")

    artifacts = call(client, "GET", f"/executions/{execution_id}/artifacts").json()["items"]
    shots = [a for a in artifacts if a["kind"] == "SCREENSHOT"]
    print(f"截图产物：{len(shots)} 个"
          + (f"；下载：{API}/executions/{execution_id}/artifacts/{shots[0]['id']}" if shots else ""))

    return 0 if detail["status"] == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
