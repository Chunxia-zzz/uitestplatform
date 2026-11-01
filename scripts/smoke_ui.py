"""前端冒烟：用 Playwright 打开各页面，断言关键文本并截图。

    python scripts/smoke_ui.py [base_url]
前置：后端 8000、前端 5173 已启动，且已执行 `python -m app.cli seed-demo`。
M3.2 新增：用例编排页（/cases）与报告页（/executions/{id}/report）。
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request

from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5173"
API = "http://127.0.0.1:8000/api/v1"
SHOTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "backend", "artifacts")


def latest_execution_id() -> int | None:
    try:
        with urllib.request.urlopen(f"{API}/executions?project_id=1&limit=1", timeout=5) as resp:
            items = json.load(resp).get("items", [])
        return items[0]["id"] if items else None
    except Exception:
        return None


CHECKS = [
    ("/scaffold", ["快速接入", "网页地址", "动作清单"], "00-scaffold.png"),
    ("/scan", ["元素扫描", "开始扫描"], "00b-scan.png"),
    ("/elements", ["元素库", "登录模块"], "01-elements.png"),
    ("/cases", ["用例编排", "登录成功", "步骤"], "02-cases.png"),
    ("/suites", ["用例集", "冒烟回归"], "03-suites.png"),
    ("/engines", ["引擎与能力", "playwright", "动作字典"], "04-engines.png"),
    ("/executions", ["执行结果", "运行首个用例"], "05-executions.png"),
]


async def check_step_editor(page) -> bool:
    """M3.2：步骤表单必须按 params_schema 生成字段（不是裸 JSON 框）。"""
    await page.goto(f"{BASE}/cases", wait_until="networkidle")
    await page.wait_for_timeout(800)
    await page.click("text=添加步骤")
    await page.wait_for_timeout(400)
    if not await page.query_selector(".modal"):
        print("[FAIL] /cases 添加步骤：弹窗未出现")
        return False

    # 选 navigate → 应该出现它的必填参数 url
    await page.select_option(".modal select", "navigate")
    await page.wait_for_timeout(300)
    modal_text = await page.inner_text(".modal")
    ok = "url" in modal_text and "输出变量" in modal_text
    print(f"[{'OK ' if ok else 'FAIL'}] /cases 步骤表单按 schema 生成字段（navigate → url）")
    await page.screenshot(path=os.path.join(SHOTS, "07-step-editor.png"))
    await page.click(".modal button:has-text('取消')")
    return ok


async def check_scaffold_flow(page) -> bool:
    """M3.4：载入示例 → 生成并运行 → 结果面板出现（整条链路在 UI 上真的能跑）。"""
    await page.goto(f"{BASE}/scaffold", wait_until="networkidle")
    await page.wait_for_timeout(900)
    await page.click("text=载入登录示例")
    await page.wait_for_timeout(500)
    await page.click("text=生成并运行")

    body = ""
    for _ in range(40):                      # 最多等 20s
        await page.wait_for_timeout(500)
        body = await page.inner_text("body")
        if "生成结果" in body:
            break

    ok = "生成结果" in body and "用例集" in body and "执行" in body
    print(f"[{'OK ' if ok else 'FAIL'}] /scaffold 一键生成并运行")
    if ok:
        # 页面很长，滚到结果卡片再截图（否则截到的是动作清单底部）
        await page.locator("h2", has_text="生成结果").scroll_into_view_if_needed()
        await page.wait_for_timeout(300)
    await page.screenshot(path=os.path.join(SHOTS, "08-scaffold-result.png"))
    return ok


async def check_scan_flow(page) -> bool:
    """M3.5：输入 URL → 扫描 → 候选出现（勾选确认）→ 导入 → 结果面板。"""
    await page.goto(f"{BASE}/scan", wait_until="networkidle")
    await page.wait_for_timeout(900)

    # 选择项目：index=0 是"选择项目…"占位项，必须选 index=1（第一个真实项目）
    select = page.locator("select").first
    if await select.count():
        option_count = await select.locator("option").count()
        if option_count > 1:
            await select.select_option(index=1)

    # 填 URL 并扫描
    url_input = page.locator("input[placeholder*='127.0.0.1']")
    if await url_input.count():
        await url_input.fill("http://127.0.0.1:8899/todo.html")
    await page.click("text=开始扫描")

    body = ""
    for _ in range(40):
        await page.wait_for_timeout(500)
        body = await page.inner_text("body")
        if "候选元素" in body or "扫描失败" in body or "错误" in body:
            break

    ok = "候选元素" in body
    print(f"[{'OK ' if ok else 'FAIL'}] /scan 扫描出候选元素")
    await page.screenshot(path=os.path.join(SHOTS, "09-scan-result.png"))
    return ok


async def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    checks = list(CHECKS)

    execution_id = latest_execution_id()
    if execution_id:
        checks.append((f"/executions/{execution_id}/report",
                       ["执行报告", "HTML", "下载 HTML"], "06-report.png"))
    else:
        print("[WARN] 没有执行记录，跳过报告页冒烟")

    failed = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        for path, must_contain, shot in checks:
            await page.goto(f"{BASE}{path}", wait_until="networkidle")
            await page.wait_for_timeout(700)
            body = await page.inner_text("body")
            missing = [text for text in must_contain if text not in body]
            status = "OK " if not missing else "FAIL"
            print(f"[{status}] {path}  缺少={missing or '-'}")
            if missing:
                failed += 1
            await page.screenshot(path=os.path.join(SHOTS, shot), full_page=False)
        if not await check_step_editor(page):
            failed += 1
        if not await check_scaffold_flow(page):
            failed += 1
        if not await check_scan_flow(page):
            failed += 1
        await browser.close()
    print(f"截图目录：{SHOTS}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
