"""M4.2 真机验收：手势 / 滑动 / 上下文 / 元素级截图（全部走平台 REST 执行）。

为什么要两个沙箱 App：
  * **系统设置**：适合滑动类动作（`page_swipe` / `element_scroll` / `scroll_to_element`），
    只有滚动没有副作用，且「关于本机」在首屏之外，能真正验证「滚到元素」；
    **注意**：ColorOS 设置在清单里锁了竖屏，`fix_orientation` 在这里必然失败（实测）；
  * **计算器**：适合点击类动作（`long_press` / `double_click` / `coordinate_click` / `drag`）
    与 `fix_orientation`（支持旋转），点错也只是多按一个数字，不会改到用户数据。

前置补充：设备需打开「自动旋转」（`adb shell settings put system accelerometer_rotation 1`），
否则任何 App 都转不动——适配器会把这种情况翻译成一句能排障的话。

前置：
    * 后端 8000 已启动（M4.2 代码）
    * Appium Server 4723 已启动，真机已连接并解锁
    * 设备已开「自动旋转」（否则 fix_orientation 会如实报错）
    * 环境变量可覆盖：UIP_ANDROID_UDID / UIP_APPIUM_URL / UIP_API_BASE

用法：
    NO_PROXY=127.0.0.1,localhost python scripts/smoke_android_gestures.py

预期：两个用例集均 PASSED；设置用例 15 步、计算器用例 9 步。
重复执行：复用项目/目标/元素/用例/用例集，不重复写入步骤。
"""
from __future__ import annotations

import os
import sys
import time

import httpx

API = os.environ.get("UIP_API_BASE", "http://127.0.0.1:8000/api/v1")
UDID = os.environ.get("UIP_ANDROID_UDID", "3149dfe3")
APPIUM_URL = os.environ.get("UIP_APPIUM_URL", "http://127.0.0.1:4723")
TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

SETTINGS_SPEC = {
    "project": {"name": "Android 手势自检 · 设置", "code": "android-gesture-m42-settings",
                "platform": "ANDROID", "engine_key": "appium"},
    "target": {"name": "系统设置 · PJA110", "package": "com.android.settings",
               "activity": ".Settings"},
    "case": {"title": "M4.2 · 设置页手势与上下文",
             "description": "滑动 / 滚动到元素 / 上下文 / 元素级截图 / 方向 / 前后台"},
    "suite": "M4.2 手势自检（设置）",
    "elements": [
        ("WLAN 行", [("text", "WLAN", 10)]),
        ("设置列表", [("resource_id", "com.android.settings:id/recycler_view", 10)]),
        ("关于本机 行", [("text", "关于本机", 10)]),
        ("设置条目文本", [("resource_id", "android:id/title", 10)]),
        ("不存在的提示", [("text", "__m42_never_exists__", 10)]),
    ],
    "steps": [
        {"action_key": "restart_app", "params": {}, "remark": "冷启动到设置首页"},
        {"action_key": "get_contexts", "params": {"output_var": "ctxs"}},
        {"action_key": "switch_to_context", "params": {"context": "NATIVE_APP"}},
        {"action_key": "wait_element", "element": "WLAN 行", "params": {"state": "visible"}},
        {"action_key": "screenshot", "element": "WLAN 行",
         "params": {"target": "element"}, "remark": "元素级截图"},
        {"action_key": "page_swipe", "element": "设置列表",
         "params": {"direction": "up", "distance": 600},
         "remark": "元素仅为满足契约（整屏滑动本身不依赖元素）"},
        {"action_key": "swipe_down", "element": "设置列表", "params": {"distance": 600}},
        {"action_key": "element_scroll", "element": "设置列表",
         "params": {"direction": "down", "distance": 600}},
        {"action_key": "scroll_to_element", "element": "关于本机 行",
         "params": {}, "timeout_ms": 25000, "remark": "首屏之外，必须滚动才会出现"},
        {"action_key": "element_list", "element": "设置条目文本",
         "params": {"output_var": "titles"}},
        {"action_key": "multi_finger_swipe", "element": "设置列表",
         "params": {"direction": "down", "distance": 400}},
        {"action_key": "wait_element", "element": "不存在的提示",
         "params": {"state": "hidden"}, "timeout_ms": 3000},
        {"action_key": "background_foreground", "params": {"seconds": 2}},
        {"action_key": "screenshot", "params": {"target": "page"}},
        {"action_key": "restart_app", "params": {}, "remark": "恢复到首页，方便下次复跑"},
    ],
}

CALC_SPEC = {
    "project": {"name": "Android 手势自检 · 计算器", "code": "android-gesture-m42-calc",
                "platform": "ANDROID", "engine_key": "appium"},
    "target": {"name": "计算器 · PJA110", "package": "com.coloros.calculator",
               "activity": "com.android.calculator2.Calculator"},
    "case": {"title": "M4.2 · 计算器点击类手势",
             "description": "长按 / 双击 / 坐标点击 / 拖拽（点错也无副作用）"},
    "suite": "M4.2 手势自检（计算器）",
    "elements": [
        ("数字 1", [("text", "1", 10)]),
        ("数字 2", [("text", "2", 10)]),
        ("数字 5", [("text", "5", 10)]),
        ("数字 9", [("text", "9", 10)]),
    ],
    "steps": [
        {"action_key": "restart_app", "params": {}},
        {"action_key": "wait_element", "element": "数字 1", "params": {"state": "visible"}},
        {"action_key": "long_press", "element": "数字 1", "params": {"duration_ms": 800}},
        {"action_key": "double_click", "element": "数字 2", "params": {}},
        {"action_key": "coordinate_click", "element": "数字 9", "params": {"x": 620, "y": 900},
         "remark": "点显示区域（无副作用）；元素绑定仅为满足契约"},
        {"action_key": "drag", "element": "数字 5", "params": {"target_element_id": "数字 9"}},
        # 方向放这里而不是设置页：ColorOS 设置在清单里锁了竖屏，旋转会必然失败（已实测）
        {"action_key": "fix_orientation", "params": {"orientation": "LANDSCAPE"}},
        {"action_key": "fix_orientation", "params": {"orientation": "PORTRAIT"}},
        {"action_key": "screenshot", "params": {"target": "page"}},
    ],
}


def call(client: httpx.Client, method: str, path: str, **kwargs):
    return client.request(method, f"{API}{path}", **kwargs)


def get_or_create_project(client: httpx.Client, spec: dict) -> dict:
    body = spec["project"]
    for item in call(client, "GET", "/projects").json()["items"]:
        if item["code"] == body["code"]:
            print(f"   复用项目 #{item['id']} {item['name']}")
            return item
    resp = call(client, "POST", "/projects", json=body)
    resp.raise_for_status()
    project = resp.json()
    print(f"   新建项目 #{project['id']} {project['name']}")
    return project


def get_or_create_target(client: httpx.Client, project_id: int, spec: dict) -> dict:
    target = spec["target"]
    resp = call(client, "GET", "/execution-targets", params={"project_id": project_id})
    for item in resp.json().get("items", []) if resp.status_code == 200 else []:
        if item["name"] == target["name"]:
            print(f"   复用执行目标 #{item['id']}")
            return item
    body = {
        "name": target["name"], "platform": "ANDROID", "engine_key": "appium",
        "options": {
            "udid": UDID, "app_package": target["package"],
            "app_activity": target["activity"], "appium_url": APPIUM_URL,
            "no_reset": True, "new_command_timeout": 180, "auto_grant_permissions": True,
        },
    }
    resp = call(client, "POST", f"/projects/{project_id}/execution-targets", json=body)
    resp.raise_for_status()
    created = resp.json()
    print(f"   新建执行目标 #{created['id']}（{target['package']}）")
    return created


def get_or_create_element(client: httpx.Client, project_id: int, name: str) -> int:
    resp = call(client, "GET", f"/projects/{project_id}/elements", params={"keyword": name})
    for item in resp.json().get("items", []):
        if item.get("element_name") == name:
            return item["id"]
    resp = call(client, "POST", f"/projects/{project_id}/elements",
                json={"parent_id": 0, "element_name": name, "node_type": "ELEMENT"})
    resp.raise_for_status()
    return resp.json()["id"]


def ensure_locator(client: httpx.Client, element_id: int, locator_type: str,
                   value: str, priority: int) -> None:
    resp = call(client, "POST", f"/elements/{element_id}/locators", json={
        "platform": "ANDROID", "engine_key": "appium",
        "locator_type": locator_type, "locator_value": value, "priority": priority,
    })
    if resp.status_code not in (201, 409):
        resp.raise_for_status()


def get_or_create_case(client: httpx.Client, project_id: int, spec: dict) -> dict:
    case = spec["case"]
    for item in call(client, "GET", f"/projects/{project_id}/cases").json()["items"]:
        if item["title"] == case["title"]:
            print(f"   复用用例 #{item['id']}")
            return item
    resp = call(client, "POST", f"/projects/{project_id}/cases",
                json={"title": case["title"], "description": case["description"]})
    resp.raise_for_status()
    created = resp.json()
    print(f"   新建用例 #{created['id']}")
    return created


def ensure_steps(client: httpx.Client, case_id: int, spec: dict,
                 element_ids: dict[str, int]) -> None:
    """把用例步骤对齐到 spec。

    已有步骤的 ``action_key`` 序列与 spec 一致 → 复用；不一致（spec 改了）→ 清空重写。
    只做全量对齐，不做逐条 diff —— 冒烟脚本的步骤本来就是一份整体。
    """
    resp = call(client, "GET", f"/cases/{case_id}/steps").json()
    existing = resp.get("items", [])
    wanted = [step["action_key"] for step in spec["steps"]]
    if [item["action_key"] for item in existing] == wanted:
        print(f"   复用已有 {len(existing)} 个步骤（与 spec 一致）")
        return
    for item in existing:
        call(client, "DELETE", f"/cases/{case_id}/steps/{item['id']}").raise_for_status()
    if existing:
        print(f"   spec 已变，清空 {len(existing)} 个旧步骤后重写")

    for index, step in enumerate(spec["steps"], start=1):
        params = dict(step["params"])
        # drag 的 target_element_id 在用例里写元素名，写库前换成真实 id（schema 要求 integer）
        if isinstance(params.get("target_element_id"), str):
            params["target_element_id"] = element_ids[params["target_element_id"]]
        body = {"seq": index, "action_key": step["action_key"], "params": params}
        if step.get("element"):
            body["element_id"] = element_ids[step["element"]]
        if step.get("remark"):
            body["remark"] = step["remark"]
        if step.get("timeout_ms"):
            body["timeout_ms"] = step["timeout_ms"]
        resp = call(client, "POST", f"/cases/{case_id}/steps", json=body)
        if resp.status_code != 201:
            print(f"   ❌ 步骤 {index}（{step['action_key']}）写入失败："
                  f"HTTP {resp.status_code} {resp.text[:300]}")
            sys.exit(1)
    print(f"   写入 {len(spec['steps'])} 个步骤")


def get_or_create_suite(client: httpx.Client, project_id: int, spec: dict) -> dict:
    for item in call(client, "GET", f"/projects/{project_id}/suites").json()["items"]:
        if item["name"] == spec["suite"]:
            print(f"   复用用例集 #{item['id']}")
            return item
    resp = call(client, "POST", f"/projects/{project_id}/suites",
                json={"name": spec["suite"], "description": "M4.2 真机验收"})
    resp.raise_for_status()
    created = resp.json()
    print(f"   新建用例集 #{created['id']}")
    return created


def ensure_member(client: httpx.Client, suite_id: int, case_id: int) -> None:
    items = call(client, "GET", f"/suites/{suite_id}/cases").json()["items"]
    if any(item["case_id"] == case_id for item in items):
        return
    resp = call(client, "POST", f"/suites/{suite_id}/cases", json={"case_ids": [case_id]})
    resp.raise_for_status()


def wait_execution(client: httpx.Client, execution_id: int, timeout: float = 300) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = call(client, "GET", f"/executions/{execution_id}").json()
        if data["status"] in TERMINAL:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"执行 {execution_id} 超时未结束")


def run_spec(client: httpx.Client, spec: dict) -> dict:
    print(f"\n=== {spec['project']['name']} ===")
    project = get_or_create_project(client, spec)
    pid = project["id"]

    target = get_or_create_target(client, pid, spec)
    call(client, "PATCH", f"/projects/{pid}", json={"target_id": target["id"]})

    element_ids: dict[str, int] = {}
    for name, locators in spec["elements"]:
        element_ids[name] = get_or_create_element(client, pid, name)
        for locator_type, value, priority in locators:
            ensure_locator(client, element_ids[name], locator_type, value, priority)
    print(f"   元素 {len(element_ids)} 个：{element_ids}")

    case = get_or_create_case(client, pid, spec)
    ensure_steps(client, case["id"], spec, element_ids)

    suite = get_or_create_suite(client, pid, spec)
    ensure_member(client, suite["id"], case["id"])
    resp = call(client, "POST", f"/suites/{suite['id']}:run")
    resp.raise_for_status()
    execution_id = resp.json()["id"]
    print(f"   执行 #{execution_id} 入队…")

    detail = wait_execution(client, execution_id)
    print(f"   终态 {detail['status']}：通过 {detail['passed']} / "
          f"失败 {detail['failed']} / 异常 {detail['errored']}")
    for group in detail.get("cases", []):
        for step in group.get("steps", []):
            mark = "✅" if step["status"] == "PASSED" else "❌"
            print(f"     {mark} {step['seq']:>2}. {step['action_key']:<20} "
                  f"{step['status']:<7} {step.get('message') or ''}")
    return detail


def main() -> int:
    client = httpx.Client(timeout=180, trust_env=False)
    try:
        client.get(f"{API}/engines").raise_for_status()
    except Exception as exc:
        print(f"[前置条件] 后端不可访问：{API}（{exc}）")
        return 2

    failures = 0
    for spec in (SETTINGS_SPEC, CALC_SPEC):
        detail = run_spec(client, spec)
        if detail["status"] != "PASSED":
            failures += 1

    print("\n" + "=" * 60)
    print("M4.2 真机验收：" + ("全部 PASSED" if failures == 0 else f"{failures} 个用例集未通过"))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
