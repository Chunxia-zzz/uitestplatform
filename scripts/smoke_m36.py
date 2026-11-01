"""M3.6 端到端验收：执行目标 CRUD / 企微通知 / trace-video-HAR / 推送失败隔离。

用法（分四阶段跑，对应设计文档 §4.2 V1–V12 的环境切换）：

    # 阶段一（V1–V6 + V9 + V10）：后端 .env 需
    #   UIP_NOTIFY_WECOM_WEBHOOK=http://127.0.0.1:18999/webhook
    #   UIP_NOTIFY_ON=failure
    #   UIP_PUBLIC_BASE_URL=http://127.0.0.1:5173
    #   UIP_TRACE=always  UIP_VIDEO=true  UIP_HAR=true
    # 后端(8000) + fixture(8899) 已起，然后：
    python scripts/smoke_m36.py

    # 阶段二（V7）：.env 清空 UIP_NOTIFY_WECOM_WEBHOOK 并重启后端
    python scripts/smoke_m36.py --phase off

    # 阶段三（V8）：.env webhook 指回 stub、stub 以 500 模式运行
    python scripts/smoke_m36.py --phase bad

    # 阶段四（V11）：.env UIP_TRACE=off UIP_VIDEO=false UIP_HAR=false 并重启后端
    python scripts/smoke_m36.py --phase offdiag

    # 阶段五（V12）：.env webhook 指向一个**不监听**的端口并重启后端
    #   （脚本用失败用例触发推送，因为 UIP_NOTIFY_ON 默认 failure）
    python scripts/smoke_m36.py --phase nostub

判定标准见 docs/UI自动化平台M3.6详细设计.md §4.2。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api/v1"
FIXTURE = "http://127.0.0.1:8899"
STUB_HOST, STUB_PORT = "127.0.0.1", 18999

PROJECT_CODE = f"m36-{int(time.time())}"
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


def err_code(resp) -> str:
    try:
        return resp.json()["error"]["code"]
    except Exception:                                   # noqa: BLE001
        return f"<no-envelope {resp.status_code}>"


# ─────────────────────────── 企微 webhook stub ───────────────────────────
class StubWebhook:
    """最小 HTTP stub：记录请求体；mode=ok 返回 errcode 0，mode=bad 返回 500。"""

    def __init__(self) -> None:
        self.received: list[dict] = []
        self.mode = "ok"
        self._server: asyncio.Server | None = None

    async def _handle(self, reader: asyncio.StreamReader,
                      writer: asyncio.StreamWriter) -> None:
        try:
            request_line = await reader.readline()
            length = 0
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break
                if line.lower().startswith(b"content-length:"):
                    length = int(line.split(b":", 1)[1].strip())
            body = await reader.read(length) if length else b"{}"
            if self.mode == "ok":
                try:
                    self.received.append(json.loads(body.decode("utf-8")))
                except ValueError:
                    self.received.append({"_raw": body.decode("utf-8", "replace")})
                payload = b'{"errcode":0,"errmsg":"ok"}'
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             + f"Content-Length: {len(payload)}\r\n\r\n".encode()
                             + payload)
            else:
                writer.write(b"HTTP/1.1 500 Internal Server Error\r\n"
                             b"Content-Length: 0\r\n\r\n")
            await writer.drain()
        except Exception:                               # noqa: BLE001
            pass                                        # stub 自身绝不崩
        finally:
            writer.close()

    async def start(self, mode: str = "ok") -> None:
        self.mode = mode
        self.received.clear()
        self._server = await asyncio.start_server(self._handle, STUB_HOST, STUB_PORT)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None


# ─────────────────────────── 公共步骤 ───────────────────────────
async def new_project(client: httpx.AsyncClient) -> dict:
    resp = await client.post(f"{API}/projects", json={
        "name": "M3.6 验收项目", "code": PROJECT_CODE,
        "platform": "WEB", "engine_key": "playwright"})
    resp.raise_for_status()
    return resp.json()


async def new_case(client: httpx.AsyncClient, project_id: int, title: str,
                   failing: bool) -> int:
    case = (await client.post(f"{API}/projects/{project_id}/cases",
                              json={"title": title})).json()
    if failing:
        steps = [
            {"seq": 1, "action_key": "navigate",
             "params": {"url": f"{FIXTURE}/login.html"}},
            {"seq": 2, "action_key": "assert_equals",
             "params": {"actual": "${missing_var}", "expected": "永远不相等"}},
        ]
    else:
        steps = [
            {"seq": 1, "action_key": "navigate",
             "params": {"url": f"{FIXTURE}/login.html"}},
            {"seq": 2, "action_key": "assert_equals",
             "params": {"actual": "a", "expected": "a"}},
        ]
    for step in steps:
        resp = await client.post(f"{API}/cases/{case['id']}/steps", json=step)
        resp.raise_for_status()
    return case["id"]


async def run_and_poll(client: httpx.AsyncClient, project_id: int,
                       case_id: int, timeout: float = 120) -> dict:
    resp = await client.post(f"{API}/executions",
                             json={"project_id": project_id, "case_ids": [case_id]})
    resp.raise_for_status()
    execution_id = resp.json()["id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = (await client.get(f"{API}/executions/{execution_id}")).json()
        if data["status"] in TERMINAL:
            return data
        await asyncio.sleep(0.5)
    raise TimeoutError(f"execution {execution_id} 未在 {timeout}s 内结束")


async def artifacts_of(client: httpx.AsyncClient, execution_id: int) -> list[dict]:
    data = (await client.get(f"{API}/executions/{execution_id}/artifacts")).json()
    return data["items"]


# ─────────────────────────── 阶段一：V1–V6 + V9 + V10 ───────────────────────────
async def phase_full() -> None:
    stub = StubWebhook()
    await stub.start("ok")
    try:
        async with httpx.AsyncClient(timeout=150) as client:
            project = await new_project(client)
            pid = project["id"]

            # ── V1 创建 target ──
            resp = await client.post(f"{API}/projects/{pid}/execution-targets", json={
                "name": "t36", "platform": "WEB", "engine_key": "playwright",
                "base_url": FIXTURE, "options": {}})
            check("V1 创建 target 201", resp.status_code == 201,
                  f"status={resp.status_code}")
            target = resp.json()
            check("V1 字段回读一致",
                  target["name"] == "t36" and target["platform"] == "WEB"
                  and target["engine_key"] == "playwright"
                  and target["base_url"] == FIXTURE and target["enabled"] is True)

            # ── V2 同名 409 / 路由不匹配 422 ──
            dup = await client.post(f"{API}/projects/{pid}/execution-targets", json={
                "name": "t36", "platform": "WEB", "engine_key": "playwright"})
            check("V2 同名再建 409", dup.status_code == 409
                  and err_code(dup) == "TARGET_NAME_DUPLICATED",
                  f"status={dup.status_code} code={err_code(dup)}")
            mismatch = await client.post(f"{API}/projects/{pid}/execution-targets", json={
                "name": "t36-bad", "platform": "WEB", "engine_key": "appium"})
            check("V2 WEB+appium 422", mismatch.status_code == 422
                  and err_code(mismatch) == "PROJECT_PLATFORM_ENGINE_MISMATCH",
                  f"status={mismatch.status_code} code={err_code(mismatch)}")

            # ── V3 PATCH 改 base_url ──
            patched = await client.patch(
                f"{API}/execution-targets/{target['id']}",
                json={"base_url": f"{FIXTURE}/"})
            check("V3 PATCH 200", patched.status_code == 200
                  and patched.json()["base_url"] == f"{FIXTURE}/")
            detail = (await client.get(
                f"{API}/execution-targets/{target['id']}")).json()
            check("V3 仅该字段变化", detail["name"] == "t36"
                  and detail["base_url"] == f"{FIXTURE}/")

            # ── V4 引用置空后删除 ──
            await client.patch(f"{API}/projects/{pid}",
                               json={"target_id": target["id"]})
            deleted = await client.delete(f"{API}/execution-targets/{target['id']}")
            check("V4 DELETE 204", deleted.status_code == 204,
                  f"status={deleted.status_code}")
            proj = (await client.get(f"{API}/projects/{pid}")).json()
            check("V4 project.target_id 已置空", proj["target_id"] is None,
                  f"target_id={proj['target_id']}")

            # ── V5 软删后同名重建 ──
            recreated = await client.post(f"{API}/projects/{pid}/execution-targets",
                                          json={"name": "t36", "platform": "WEB",
                                                "engine_key": "playwright",
                                                "base_url": FIXTURE})
            check("V5 同名重建 201", recreated.status_code == 201,
                  f"status={recreated.status_code}")
            new_target = recreated.json()
            check("V5 新 id 不同于软删行", new_target["id"] != target["id"])

            # ── V6 通知测试端点 ──
            test_resp = await client.post(f"{API}/notifications:test", json={})
            check("V6 notifications:test 200", test_resp.status_code == 200
                  and test_resp.json().get("sent") is True,
                  f"status={test_resp.status_code}")
            check("V6 stub 收到 msgtype=markdown",
                  bool(stub.received) and stub.received[0].get("msgtype") == "markdown")
            check("V6 响应 webhook 已掩码",
                  "***" in test_resp.json().get("webhook", "")
                  and test_resp.json().get("webhook") != "http://127.0.0.1:18999/webhook",
                  test_resp.json().get("webhook", ""))

            # ── V9 失败用例：on-failure 语义（此处全局 always 也应存 TRACE）──
            fail_case = await new_case(client, pid, "V9 失败用例", failing=True)
            execution = await run_and_poll(client, pid, fail_case)
            check("V9 终态 FAILED", execution["status"] == "FAILED",
                  execution["status"])
            await asyncio.sleep(1.0)                # 等 fire-and-forget 推送落地
            check("V9 stub 收到失败消息（含「失败」）",
                  any("失败" in (m.get("markdown", {}).get("content") or "")
                      for m in stub.received))
            check("V9 消息含计数 / 执行 ID / 报告链接",
                  any("#" in (m.get("markdown", {}).get("content") or "")
                      and "查看报告" in (m.get("markdown", {}).get("content") or "")
                      for m in stub.received))
            arts = await artifacts_of(client, execution["id"])
            check("V9 artifacts 含 TRACE", "TRACE" in [a["kind"] for a in arts],
                  str([a["kind"] for a in arts]))

            # ── V10 通过用例：TRACE + VIDEO + HAR 三类俱全且可下载 ──
            pass_case = await new_case(client, pid, "V10 通过用例", failing=False)
            execution2 = await run_and_poll(client, pid, pass_case)
            check("V10 终态 PASSED", execution2["status"] == "PASSED",
                  execution2["status"])
            arts2 = await artifacts_of(client, execution2["id"])
            kinds2 = [a["kind"] for a in arts2]
            check("V10 artifacts 含 TRACE/VIDEO/HAR",
                  {"TRACE", "VIDEO", "HAR"} <= set(kinds2), str(sorted(set(kinds2))))
            for art in [a for a in arts2 if a["kind"] in ("TRACE", "VIDEO", "HAR")]:
                dl = await client.get(
                    f"{API}/executions/{execution2['id']}/artifacts/{art['id']}")
                check(f"V10 下载 {art['kind']} 200", dl.status_code == 200
                      and len(dl.content) > 0, f"{len(dl.content)} bytes")
    finally:
        await stub.stop()


# ─────────────────────────── 阶段二：V7（未配置 422）───────────────────────────
async def phase_off() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{API}/notifications:test", json={})
        check("V7 未配置 webhook → 422", resp.status_code == 422
              and err_code(resp) == "NOTIFY_NOT_CONFIGURED",
              f"status={resp.status_code} code={err_code(resp)}")


# ─────────────────────────── 阶段三：V8（发送失败 502）─────────────────────────
async def phase_bad() -> None:
    stub = StubWebhook()
    await stub.start("bad")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{API}/notifications:test", json={})
            check("V8 stub 500 → 502", resp.status_code == 502
                  and err_code(resp) == "NOTIFY_SEND_FAILED",
                  f"status={resp.status_code} code={err_code(resp)}")
    finally:
        await stub.stop()


# ─────────────────────────── 阶段四：V11（诊断全关）───────────────────────────
async def phase_offdiag() -> None:
    async with httpx.AsyncClient(timeout=150) as client:
        project = await new_project(client)
        case_id = await new_case(client, project["id"], "V11 通过用例", failing=False)
        execution = await run_and_poll(client, project["id"], case_id)
        check("V11 终态 PASSED", execution["status"] == "PASSED", execution["status"])
        arts = await artifacts_of(client, execution["id"])
        kinds = [a["kind"] for a in arts]
        check("V11 无 TRACE/VIDEO/HAR",
              not {"TRACE", "VIDEO", "HAR"} & set(kinds), str(kinds))


# ─────────────────────────── 阶段五：V12（推送失败不影响执行）─────────────────
async def phase_nostub() -> None:
    async with httpx.AsyncClient(timeout=150) as client:
        project = await new_project(client)
        # 必须用**失败**用例：notify_on=failure 下通过用例根本不会触发推送，
        # 用通过用例这条断言就是空转（2026-11-02 验收走查发现并修正）。
        case_id = await new_case(client, project["id"], "V12 失败用例", failing=True)
        execution = await run_and_poll(client, project["id"], case_id)
        check("V12 推送失败后执行仍正常终态", execution["status"] == "FAILED",
              execution["status"])
        print("  [INFO] 请在服务端日志确认仅出现 event=notify.failed、无未捕获异常")


async def main() -> int:
    parser = argparse.ArgumentParser(description="M3.6 端到端验收")
    parser.add_argument("--phase", default="full",
                        choices=["full", "off", "bad", "offdiag", "nostub"])
    args = parser.parse_args()

    print(f"=== M3.6 smoke · phase={args.phase} ===")
    phases = {
        "full": phase_full, "off": phase_off, "bad": phase_bad,
        "offdiag": phase_offdiag, "nostub": phase_nostub,
    }
    await phases[args.phase]()

    print(f"\n结果：{passed} passed, {len(failed)} failed")
    if failed:
        print("失败项：", "；".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
