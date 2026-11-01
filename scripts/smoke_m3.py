"""M3.1 端到端验收：202 / 状态机 / 重试 / 产物 / 报告 / WS / 并发上限。

    python scripts/smoke_m3.py [base_http]

前置：后端 8000 已启动、fixture 8899 已启动、已 seed-demo。
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
WS_BASE = BASE.replace("http://", "ws://")
CASE_TITLE = "M3.1 smoke（截图 + 重试）"
TERMINAL = {"PASSED", "FAILED", "ERROR", "CANCELLED"}

results: list[tuple[bool, str]] = []


def check(ok: bool, label: str, extra: str = "") -> None:
    results.append((ok, label))
    print(f"[{'OK ' if ok else 'FAIL'}] {label}{('  ' + extra) if extra else ''}")


async def ensure_case(client: httpx.AsyncClient, project_id: int) -> int:
    cases = (await client.get(f"/api/v1/projects/{project_id}/cases")).json()["items"]
    for case in cases:
        if case["title"] == CASE_TITLE:
            return case["id"]
    case = (await client.post(f"/api/v1/projects/{project_id}/cases",
                              json={"title": CASE_TITLE, "description": "M3.1 验收用"})).json()
    steps = [
        {"seq": 1, "action_key": "navigate", "params": {"url": "/login.html"}},
        {"seq": 2, "action_key": "screenshot", "params": {"path": ""}},
        {"seq": 3, "action_key": "assert_equals",
         "params": {"actual": "${missing_var}", "expected": "永远不相等"},
         "on_failure": "RETRY", "retry_times": 2},
    ]
    for step in steps:
        step["params"] = {k: v for k, v in step["params"].items() if v != ""}
        resp = await client.post(f"/api/v1/cases/{case['id']}/steps", json=step)
        resp.raise_for_status()
    return case["id"]


async def collect_ws(execution_id: int, events: list[str]) -> None:
    try:
        async with websockets.connect(f"{WS_BASE}/ws/executions/{execution_id}") as ws:
            while True:
                message = json.loads(await asyncio.wait_for(ws.recv(), timeout=30))
                if message.get("event") == "subscribed":
                    continue
                events.append(message["event"])
                if message["event"] in ("execution.finished", "execution.cancelled"):
                    return
    except Exception as exc:                       # noqa: BLE001
        events.append(f"WS_ERROR:{type(exc).__name__}")


async def poll(client: httpx.AsyncClient, execution_id: int, timeout: float = 90) -> dict:
    elapsed = 0.0
    while elapsed < timeout:
        data = (await client.get(f"/api/v1/executions/{execution_id}")).json()
        if data["status"] in TERMINAL:
            return data
        await asyncio.sleep(0.4)
        elapsed += 0.4
    raise TimeoutError(f"execution {execution_id} 未在 {timeout}s 内结束")


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        health = (await client.get("/healthz")).json()
        check(health["status"] == "ok", "healthz", f"{len(health['engines'])} engines")

        project_id = (await client.get("/api/v1/projects")).json()["items"][0]["id"]
        case_id = await ensure_case(client, project_id)

        # ── V1 提交即返回 202 ──────────────────────────────
        import time
        started = time.perf_counter()
        resp = await client.post("/api/v1/executions",
                                 json={"project_id": project_id, "case_ids": [case_id]})
        submit_ms = (time.perf_counter() - started) * 1000
        check(resp.status_code == 202, "V1 POST /executions 返回 202", f"status={resp.status_code}")
        created = resp.json()
        execution_id = created["id"]
        check(created["status"] == "PENDING", "V1 初始状态 PENDING")
        check(submit_ms < 800, "V1 提交耗时 < 800ms", f"{submit_ms:.0f}ms")

        # ── V8 WS 事件 ────────────────────────────────────
        events: list[str] = []
        ws_task = asyncio.create_task(collect_ws(execution_id, events))

        # ── V2 状态推进 ───────────────────────────────────
        final = await poll(client, execution_id)
        await asyncio.wait_for(ws_task, timeout=35)
        check(True, "V2 到达终态", f"status={final['status']}")

        # ── V4 重试 ───────────────────────────────────────
        retry_rows = [s for c in final.get("cases", []) for s in c["steps"] if s["seq"] == 3]
        attempts = sorted({s.get("attempt") for s in retry_rows})
        check(attempts == [1, 2, 3], "V4 重试 3 次且逐次落行", f"attempt={attempts}")
        check(final["status"] == "FAILED", "V4 重试耗尽后用例 FAILED", final["status"])

        # ── V6 产物 ───────────────────────────────────────
        detail = (await client.get(f"/api/v1/executions/{execution_id}")).json()
        shot_rows = [s for c in detail.get("cases", []) for s in c["steps"] if s["seq"] == 2]
        check(bool(shot_rows) and shot_rows[-1]["status"] == "PASSED", "V6 screenshot 步骤 PASSED")

        # ── V7 报告 ───────────────────────────────────────
        html = await client.get(f"/api/v1/executions/{execution_id}/report?format=html")
        check(html.status_code == 200 and "执行报告" in html.text, "V7 HTML 报告可下载",
              f"{len(html.text)} bytes")
        report = (await client.get(f"/api/v1/executions/{execution_id}/report?format=json")).json()
        check(report["execution"]["id"] == execution_id, "V7 JSON 报告结构正确")
        check(report["summary"]["steps"] >= 3, "V7 报告含步骤统计",
              f"steps={report['summary']['steps']}")

        # ── V8 事件 ───────────────────────────────────────
        terminal_events = [e for e in events if e.startswith("execution.")]
        check(any(e == "step.finished" for e in events), "V8 收到 step.finished",
              f"{len(events)} events")
        check("execution.finished" in events or "execution.cancelled" in events,
              "V8 收到终态事件", ",".join(terminal_events[-2:]))
        check("step.retried" in events, "V8 收到 step.retried")
        check(not any(e.startswith("WS_ERROR") for e in events), "V8 WS 无异常")

        # ── V3 并发上限 ───────────────────────────────────
        demo_case = next(c["id"] for c in
                         (await client.get(f"/api/v1/projects/{project_id}/cases")).json()["items"]
                         if c["id"] != case_id)
        ids = []
        for _ in range(3):
            r = await client.post("/api/v1/executions",
                                  json={"project_id": project_id, "case_ids": [demo_case]})
            ids.append(r.json()["id"])
        peak = 0
        for _ in range(80):
            statuses = [(await client.get(f"/api/v1/executions/{i}")).json()["status"] for i in ids]
            peak = max(peak, statuses.count("RUNNING"))
            if all(s in TERMINAL for s in statuses):
                break
            await asyncio.sleep(0.3)
        check(peak <= 2, "V3 同时 RUNNING ≤ 2（并发上限）", f"peak={peak}")

        # ── V5 取消（对 PENDING 生效）─────────────────────
        r = await client.post("/api/v1/executions",
                              json={"project_id": project_id, "case_ids": [demo_case]})
        target = r.json()["id"]
        cancel = await client.post(f"/api/v1/executions/{target}:cancel")
        check(cancel.status_code == 200 and cancel.json()["status"] in ("CANCELLED", "RUNNING"),
              "V5 取消请求被接受", cancel.json()["status"])

    failed = [label for ok, label in results if not ok]
    print(f"\n通过 {len(results) - len(failed)}/{len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
