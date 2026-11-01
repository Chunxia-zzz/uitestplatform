"""能力探查：用现有依赖扫描一个页面，统计"能抓到哪些元素、能自动生成哪些定位符"。

**这不是产品功能**，只是评估用的一次性工具 —— 用来回答
"如果我们实现 URL 抓取，覆盖率大概是多少、哪些元素注定抓不到"。

用法：
    python scripts/probe_dom_capability.py [url ...]
默认扫描 fixtures 里的三个页面。
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter

from playwright.async_api import async_playwright

DEFAULT_URLS = [
    "http://127.0.0.1:8899/login.html",
    "http://127.0.0.1:8899/todo.html",
    "http://127.0.0.1:8899/locators.html",
]

# 在页面里跑：把每个可见/结构元素的"可定位属性"抽出来
SCAN_JS = """
() => {
  const SKIP = new Set(['SCRIPT','STYLE','META','LINK','HEAD','TITLE','NOSCRIPT','TEMPLATE','BR'])
  const out = []
  for (const el of document.querySelectorAll('body *')) {
    if (SKIP.has(el.tagName)) continue
    const leaf = el.childElementCount === 0
    out.push({
      tag: el.tagName.toLowerCase(),
      id: el.id || null,
      testid: el.getAttribute('data-testid') || null,
      name: el.getAttribute('name') || null,
      role: el.getAttribute('role') || null,
      ariaLabel: el.getAttribute('aria-label') || null,
      placeholder: el.getAttribute('placeholder') || null,
      href: el.getAttribute('href') || null,
      src: el.getAttribute('src') || null,
      alt: el.getAttribute('alt') || null,
      title: el.getAttribute('title') || null,
      type: el.getAttribute('type') || null,
      classes: (typeof el.className === 'string'
        ? el.className.trim().split(/\\s+/).filter(Boolean) : []).slice(0, 3),
      text: leaf ? (el.innerText || el.textContent || '').trim().slice(0, 60) : '',
      visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
    })
  }
  return out
}
"""


def classify(item: dict) -> str:
    """给出一条"最强可用定位方式"，从强到弱。"""
    if item["testid"]:
        return "testid"
    if item["id"]:
        return "id"
    if item["name"]:
        return "name"
    if item["role"] and item["ariaLabel"]:
        return "role+name"
    if item["ariaLabel"]:
        return "label/aria"
    if item["placeholder"]:
        return "placeholder"
    if item["alt"]:
        return "alt"
    if item["title"]:
        return "title"
    if item["href"]:
        return "href"
    if item["src"]:
        return "src"
    if item["text"]:
        return "text"
    if item["classes"]:
        return "class"
    return "none"


STRENGTH = {
    "testid": "强", "id": "强", "name": "强",
    "role+name": "中", "label/aria": "中", "placeholder": "中",
    "alt": "中", "title": "中", "href": "中", "src": "中",
    "text": "弱", "class": "弱", "none": "不可用",
}


async def scan(page, url: str) -> dict:
    await page.goto(url, wait_until="networkidle", timeout=20000)
    items = await page.evaluate(SCAN_JS)
    items = [i for i in items if i["visible"]]        # 只统计用户能看到/能操作的

    kinds = Counter(classify(i) for i in items)
    tags = Counter(i["tag"] for i in items)
    return {
        "url": url,
        "total": len(items),
        "kinds": kinds,
        "tags": tags,
        "images": sum(1 for i in items if i["tag"] == "img"),
        "links": sum(1 for i in items if i["tag"] == "a"),
        "forms": sum(1 for i in items if i["tag"] in ("input", "select", "textarea", "form")),
        "buttons": sum(1 for i in items if i["tag"] == "button"),
        "strong": sum(n for k, n in kinds.items() if STRENGTH[k] == "强"),
        "medium": sum(n for k, n in kinds.items() if STRENGTH[k] == "中"),
        "weak": sum(n for k, n in kinds.items() if STRENGTH[k] == "弱"),
        "none": kinds.get("none", 0),
    }


def report(results: list[dict]) -> None:
    print("=" * 82)
    print("DOM 扫描结果（只统计可见元素；这是评估工具，不是产品功能）")
    print("=" * 82)
    for r in results:
        print(f"\n{r['url']}")
        print(f"  可见元素 {r['total']} 个 · "
              f"图片 {r['images']} · 链接 {r['links']} · 表单控件 {r['forms']} · 按钮 {r['buttons']}")
        print(f"  可自动生成定位符：强 {r['strong']}（{_pct(r['strong'], r['total'])}）"
              f" · 中 {r['medium']}（{_pct(r['medium'], r['total'])}）"
              f" · 弱 {r['weak']}（{_pct(r['weak'], r['total'])}）"
              f" · 不可用 {r['none']}（{_pct(r['none'], r['total'])}）")
        detail = " · ".join(f"{k}={v}" for k, v in r["kinds"].most_common())
        print(f"  定位方式分布：{detail}")
        top_tags = " ".join(f"{k}({v})" for k, v in r["tags"].most_common(6))
        print(f"  主要标签：{top_tags}")


def _pct(part: int, total: int) -> str:
    return f"{part / total * 100:.0f}%" if total else "0%"


async def main() -> int:
    urls = sys.argv[1:] or DEFAULT_URLS
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        results = []
        for url in urls:
            try:
                results.append(await scan(page, url))
            except Exception as exc:
                print(f"[跳过] {url}：{type(exc).__name__}: {exc}")
        await browser.close()
    report(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
