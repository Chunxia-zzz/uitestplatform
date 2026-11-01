"""演示：从零为一个简单 Web 场景（待办清单）建用例并执行。

这个脚本等价于你在界面上做下面这几步（也是回答"怎么写用例"的可执行版本）：

    1. 打开 http://127.0.0.1:5173/scaffold（快速接入）
    2. 网页地址填 http://127.0.0.1:8899/todo.html
    3. 点「添加动作」，按下面 11 步配好元素与动作
    4. 点「生成并运行」

前置条件：
    * 后端 8000 已启动（python -m uvicorn app.main:app --port 8000）
    * fixture 8899 已启动（python scripts/serve_fixtures.py）
    * 已装 Chromium（python -m playwright install chromium）

用法：
    python scripts/demo_web_case.py

预期：全部步骤 PASSED，且最后一步断言"删除后计数从 2 变 1"通过。
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
FIXTURE = "http://127.0.0.1:8899"
TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

PAYLOAD = {
    "project": {"name": "Todo 演示项目", "code": "demo-web-todo",
                "platform": "WEB", "engine_key": "playwright"},
    "url": f"{FIXTURE}/todo.html",
    "target": {"name": "本地 fixture (8899)"},
    "elements": [
        {"key": "new_todo", "name": "新待办输入框",
         "locators": [{"locator_type": "testid", "locator_value": "new-todo"}]},
        {"key": "add", "name": "添加按钮",
         "locators": [{"locator_type": "testid", "locator_value": "add"}]},
        {"key": "count", "name": "待办计数",
         "locators": [{"locator_type": "testid", "locator_value": "count"}]},
        {"key": "first_item", "name": "第一条待办",
         "locators": [{"locator_type": "css",
                       "locator_value": 'li[data-testid="todo-item"]'}]},
        {"key": "first_delete", "name": "第一条的删除按钮",
         "locators": [{"locator_type": "css",
                       "locator_value": 'li[data-testid="todo-item"] button'}]},
    ],
    "actions": [
        # 1) 打开页面（用相对路径：换环境只改 target.base_url）
        {"action_key": "navigate", "params": {"url": "/todo.html",
                                              "wait_until": "load"}},
        # 2) 输入第一项 → 3) 添加
        {"action_key": "input", "element_key": "new_todo",
         "params": {"text": "买牛奶"}},
        {"action_key": "click", "element_key": "add", "params": {}},
        # 4) 断言列表里出现了待办
        {"action_key": "assert_visible", "element_key": "first_item", "params": {}},
        # 5~6) 第二项
        {"action_key": "input", "element_key": "new_todo",
         "params": {"text": "写周报", "clear": True}},
        {"action_key": "click", "element_key": "add", "params": {}},
        # 7) 读取计数 → 8) 断言等于 2
        {"action_key": "get_text", "element_key": "count", "output_var": "count_text"},
        {"action_key": "assert_equals", "params": {
            "actual": "${count_text}", "expected": "2"}},
        # 9) 删除第一条
        {"action_key": "click", "element_key": "first_delete", "params": {}},
        # 10) 再读计数 → 11) 断言变成 1
        {"action_key": "get_text", "element_key": "count", "output_var": "count_after"},
        {"action_key": "assert_equals", "params": {
            "actual": "${count_after}", "expected": "1"}},
    ],
    "case": {"title": "待办清单：增删与计数", "description": "演示用例，由 scripts/demo_web_case.py 创建"},
    "suite": {"name": "Todo 冒烟"},
    "run": True,
}


def wait_execution(client: httpx.Client, execution_id: int, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"{BASE}/executions/{execution_id}").json()
        if data["status"] in TERMINAL:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"执行 {execution_id} 超时未结束")


def main() -> int:
    client = httpx.Client(timeout=120)

    for name, url in (("后端", f"{BASE}/engines"), ("fixture", f"{FIXTURE}/todo.html")):
        try:
            if client.get(url).status_code >= 400:
                raise RuntimeError(f"HTTP {url}")
        except Exception as exc:
            print(f"[前置条件不满足] {name} 不可访问：{url}（{exc}）")
            return 2

    print("1) POST /scaffold —— 建项目 / 元素 / 用例 / 用例集并提交执行")
    resp = client.post(f"{BASE}/scaffold", json=PAYLOAD)
    if resp.status_code != 200:
        print(f"   失败：HTTP {resp.status_code}\n   {resp.text[:800]}")
        return 1
    data = resp.json()
    print(f"   项目 #{data['project']['id']} · 执行目标 #{data['target']['id']} · "
          f"元素 {len(data['elements'])} 个 · 用例 #{data['case']['id']}"
          f"（{data['case']['step_count']} 步）· 用例集 #{data['suite']['id']}")

    execution = data["execution"]
    if not execution:
        print(f"   未提交执行：{data['warnings']}")
        return 1
    print(f"   执行 #{execution['id']} 已入队")

    print("\n2) 等待执行结束并打印每一步")
    detail = wait_execution(client, execution["id"])
    for case in detail.get("cases", []):
        print(f"   用例 #{case['case_id']} «{case['title']}»")
        for step in case["steps"]:
            extra = ""
            if step.get("fallback_index"):
                extra += f"  fallback={step['fallback_index']}"
            if step.get("used_locator_id"):
                extra += f"  locator={step['used_locator_id']}"
            if step.get("message"):
                extra += f"  {step['message'][:70]}"
            print(f"     {step['seq']:>2}. {step['action_key']:<16} "
                  f"{step['status']:<8}{step['duration_ms'] or 0:>5}ms{extra}")

    print(f"\n3) 结果：{detail['status']}  "
          f"通过 {detail['passed']} / 失败 {detail['failed']} / 异常 {detail['errored']}")
    print(f"   报告：http://127.0.0.1:8000/api/v1/executions/{execution['id']}/report")
    return 0 if detail["status"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
