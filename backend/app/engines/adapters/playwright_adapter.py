"""Playwright 适配器（一期唯一真实实现）。

定位符翻译（语义 → Playwright 语汇）全部收敛在 ``_locator()``：
库里的 ``locator_type`` 是语义（testid / role / resource_id …），
Playwright 的语汇（``[data-testid=…]`` / ``role=…`` / ``get_by_label``）只出现在这里。
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.engines.base import (
    ActionContext, EngineAdapter, Locator, LocatorChain, LocatorProbe, SessionConfig,
)
from app.domain.enums import Platform

logger = logging.getLogger(__name__)


def _esc(value: str) -> str:
    return value.replace('"', '\\"')


class PlaywrightAdapter(EngineAdapter):
    key = "playwright"
    platforms = frozenset({Platform.WEB})

    def __init__(self) -> None:
        super().__init__()
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._frame_stack: list[Any] = []      # D12：单动作 + 栈语义
        self._dialog_policy: dict[str, Any] = {"accept": False, "text": None}
        self._config: SessionConfig | None = None
        self._save_storage_state: str | None = None
        # M3.6 GAP-08：诊断录制状态
        self._trace_started: bool = False
        self._diagnostics_dir: str | None = None

    # ─────────────────────── 生命周期 ───────────────────────
    async def start(self, config: SessionConfig) -> None:
        from playwright.async_api import async_playwright

        self._config = config
        self._pw = await async_playwright().start()
        options = dict(config.options or {})
        browser_name = options.pop("browser", "chromium")
        launcher = getattr(self._pw, browser_name)
        self._browser = await launcher.launch(headless=config.headless)

        context_opts: dict[str, Any] = {}
        device_name = options.pop("device", None)
        if device_name:
            device = self._pw.devices.get(device_name)
            if not device:
                raise ValueError(f"未知设备描述符：{device_name}")
            context_opts.update(device)
        for key in ("viewport", "is_mobile", "has_touch", "locale", "timezone_id",
                    "user_agent", "base_url", "ignore_https_errors", "extra_http_headers"):
            if key in options:
                context_opts[key] = options.pop(key)

        # GAP-06：登录态复用。storage_state 可以是文件路径，也可以是 dict。
        # 路径不存在时**不能让 Playwright 报错**（首次运行本来就没有），只告警并跳过。
        storage_state = options.pop("storage_state", None)
        if storage_state:
            if isinstance(storage_state, str) and not os.path.isfile(storage_state):
                logger.warning("storage_state 文件不存在，按未登录状态启动：%s", storage_state)
            else:
                context_opts["storage_state"] = storage_state
        # 执行结束把登录态写回这个路径（下次执行直接复用）
        self._save_storage_state = options.pop("save_storage_state", None)

        # ── M3.6 GAP-08：诊断录制（D35/D36）─────────────────────
        # options 里的 trace/video/har 是执行器用 resolve_diagnostics 解析后的
        # **规范值**；验证器/扫描等旧调用点没有 diagnostics_dir → 一律不录制，
        # 避免"开了 tracing 却永远没人 stop"的悬空状态。
        self._diagnostics_dir = config.diagnostics_dir
        trace_mode = str(options.pop("trace", "off") or "off")
        want_video = bool(options.pop("video", False))
        want_har = bool(options.pop("har", False))
        diagnostics = self._diagnostics_dir
        if diagnostics:
            os.makedirs(os.path.join(diagnostics, "trace"), exist_ok=True)
            os.makedirs(os.path.join(diagnostics, "video"), exist_ok=True)
            os.makedirs(os.path.join(diagnostics, "har"), exist_ok=True)
            if want_video:
                context_opts["record_video_dir"] = os.path.join(diagnostics, "video")
            if want_har:
                har_path = os.path.join(diagnostics, "har", "execution.har")
                context_opts["record_har_path"] = har_path

        if config.base_url and "base_url" not in context_opts:
            context_opts["base_url"] = config.base_url
        self._context = await self._browser.new_context(**context_opts)
        self._context.set_default_timeout(config.timeout_ms)

        # trace 从 context 创建即开启（D35）；off 不开
        if trace_mode in ("on-failure", "always") and diagnostics:
            await self._context.tracing.start(screenshots=True, snapshots=True,
                                              sources=True)
            self._trace_started = True

        self._page = await self._context.new_page()
        # ★ 必须预注册：弹窗是事件驱动，不预注册页面会永久阻塞（M1 §2.5.8）
        self._page.on("dialog", self._on_dialog)
        self._session_id = f"pw-{int(time.time() * 1000)}"

    def _on_dialog(self, dialog) -> None:
        policy = self._dialog_policy
        if policy.get("text") and policy["text"] not in (dialog.message or ""):
            asyncio.create_task(dialog.dismiss())
            return
        asyncio.create_task(dialog.accept() if policy.get("accept") else dialog.dismiss())

    async def stop(self) -> None:
        # GAP-06：先保存登录态，再关 context —— 关掉之后就拿不到 storage_state 了
        if self._save_storage_state and self._context is not None:
            try:
                target = os.path.abspath(self._save_storage_state)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                await self._context.storage_state(path=target)
            except Exception:
                logger.warning("保存 storage_state 失败：%s", self._save_storage_state,
                               exc_info=True)
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    await closer.close()
            except Exception:
                logger.warning("playwright close failed", exc_info=True)
        try:
            if self._pw is not None:
                await self._pw.stop()
        except Exception:
            logger.warning("playwright stop failed", exc_info=True)
        self._pw = self._browser = self._context = self._page = None
        self._frame_stack.clear()
        self._session_id = None
        self._save_storage_state = None
        self._trace_started = False
        self._diagnostics_dir = None

    async def finalize_diagnostics(self, *, save_trace: bool) -> None:
        """诊断收尾（D35/D37）：保存或丢弃 trace。

        ★ 必须在 context close 之前调用；video / har 由 context close 落盘
        （文件名随机，产物登记由执行器在 close 后扫描目录完成）。
        幂等：trace 未开启时直接 return；异常吞掉只记日志（R5 防御式写法）。
        """
        if not self._trace_started or self._context is None:
            return
        try:
            if save_trace and self._diagnostics_dir:
                trace_path = os.path.join(self._diagnostics_dir, "trace", "trace.zip")
                os.makedirs(os.path.dirname(trace_path), exist_ok=True)
                await self._context.tracing.stop(path=trace_path)
            else:
                await self._context.tracing.stop()      # 无 path = 丢弃
        except Exception:
            logger.warning("trace 收尾失败", exc_info=True)
        finally:
            self._trace_started = False

    async def create(self, config: SessionConfig) -> str:
        await self.start(config)
        return self._session_id or ""

    def session_id(self) -> str | None:
        return self._session_id

    # ─────────────────────── 定位翻译 ───────────────────────
    @property
    def _frame(self):
        if not self._page:
            raise RuntimeError("Playwright 会话未启动")
        return self._frame_stack[-1] if self._frame_stack else self._page

    def _locator(self, loc: Locator):
        """语义类型 → Playwright locator。**唯一的翻译点。**"""
        frame, value = self._frame, loc.value
        t = loc.type
        if t == "testid":
            return frame.locator(f'[data-testid="{_esc(value)}"]')
        if t == "css":
            return frame.locator(value)
        if t == "xpath":
            return frame.locator(f"xpath={value}")
        if t == "id":
            return frame.locator(f"#{value.lstrip('#')}")
        if t == "class":
            return frame.locator(f".{value.lstrip('.')}")
        if t == "title":
            return frame.locator(f'[title="{_esc(value)}"]')
        if t == "alt":
            return frame.locator(f'[alt="{_esc(value)}"]')
        if t == "role":
            return frame.locator(f"role={value}")
        if t == "text":
            return frame.get_by_text(value, exact=True)
        if t == "label":
            return frame.get_by_label(value, exact=False)
        if t == "placeholder":
            return frame.get_by_placeholder(value, exact=False)
        raise ValueError(f"Playwright 不支持的定位类型：{t}")

    async def _first_visible(self, chain: LocatorChain, ctx: ActionContext,
                             *, state: str = "visible"):
        """沿回退链找到第一条命中的定位符，返回 (locator, fallback_index, Locator)。

        ★ 每条候选只等 ``min(总超时, 2.5s)``；**最后一条**才用满总超时。
        否则"首选写错、第二条正确"这种最常见的情形要白白等 15 秒才回退 ——
        用户会以为平台卡死了。
        """
        last_error: Exception | None = None
        total = len(chain.locators)
        for index, loc in enumerate(chain.locators):
            per_timeout = ctx.timeout_ms if index == total - 1 else min(ctx.timeout_ms, 2500)
            try:
                candidate = self._locator(loc)
                await candidate.first.wait_for(state=state, timeout=per_timeout)
                ctx.emit("locator.hit", element_id=chain.element_id,
                         locator_id=loc.locator_id, fallback_index=index)
                return candidate.first, index, loc
            except Exception as exc:                      # 本条失败 → 回退下一条
                last_error = exc
                ctx.emit("locator.miss", element_id=chain.element_id,
                         locator_id=loc.locator_id, fallback_index=index,
                         error=str(exc)[:200])
        raise RuntimeError(
            f"元素 {chain.element_id} 的全部 {total} 条定位符均未命中：{last_error}")

    # ─────────────────────── 核心动作 ───────────────────────
    async def click(self, chain, ctx, **_) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        await locator.click(timeout=ctx.timeout_ms)

    async def input(self, chain, ctx, *, text: str, clear: bool = False) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        if clear:
            await locator.fill("")
        await locator.fill(str(text), timeout=ctx.timeout_ms)

    async def get_text(self, chain, ctx, *, output_var: str | None = None) -> str:
        locator, _, _ = await self._first_visible(chain, ctx)
        text = (await locator.inner_text()).strip()
        return ctx.set_var(output_var, text)

    async def get_attribute(self, chain, ctx, *, name: str,
                            output_var: str | None = None) -> str | None:
        locator, _, _ = await self._first_visible(chain, ctx)
        return ctx.set_var(output_var, await locator.get_attribute(name))

    async def wait_element(self, chain, ctx, *, state: str = "visible",
                           timeout_ms: int | None = None) -> None:
        locator, _, _ = await self._first_visible(chain, ctx, state=state)
        await locator.wait_for(state=state, timeout=timeout_ms or ctx.timeout_ms)

    async def check_exists(self, chain, ctx, *, output_var: str | None = None) -> bool:
        """元素是否存在 —— **沿回退链逐条试**，不是只看首选。

        M3.2 修正：此前只 ``_locator(chain.first).count()``，导致
        "首选定位符写错、第 2 条能命中"的元素被断言为不可见 ——
        而回退链正是 M1/M2 的核心能力，断言却绕过了它。
        计数不等待（轮询由 assert_* 在 timeout_ms 窗口内做）。
        """
        for loc in chain.locators:
            try:
                if await self._locator(loc).count() > 0:
                    return ctx.set_var(output_var, True)
            except Exception:
                continue
        return ctx.set_var(output_var, False)

    async def screenshot(self, chain, ctx, *, path: str | None = None,
                         full_page: bool = False, target: str = "page") -> str:
        """截图。``target='element'`` 时只截绑定元素（GAP-07）。

        元素级截图走 ``locator.screenshot()``：失败时能看到"到底哪个控件不对"，
        页面级截图只能证明"页面当时长这样"。
        """
        os.makedirs(settings.artifacts_dir, exist_ok=True)
        target_path = path or os.path.join(
            settings.artifacts_dir,
            f"shot-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.png")

        if target == "element":
            if chain is None:
                raise ValueError("screenshot(target=element) 需要步骤绑定元素")
            locator, _, _ = await self._first_visible(chain, ctx)
            await locator.screenshot(path=target_path)
        elif target == "page":
            await self._page.screenshot(path=target_path, full_page=full_page)
        else:
            raise ValueError(f"未知截图目标：{target}（只支持 page / element）")

        # FR34：只登记"路径事实"，落库由执行器负责（适配器不依赖 DB）
        ctx.artifacts.append({"kind": "SCREENSHOT", "path": target_path,
                              "size_bytes": os.path.getsize(target_path)})
        return target_path

    async def probe_locator(self, chain, ctx, **_) -> LocatorProbe:
        """精确计数 + 样例（M2 验证器依赖）。"""
        started = time.perf_counter()
        try:
            locator = self._locator(chain.first)
            count = await locator.count()
            sample = None
            if count:
                first = locator.first
                sample = {
                    "tag": await first.evaluate("el => el.tagName.toLowerCase()"),
                    "text": (await first.inner_text())[:80],
                    "visible": await first.is_visible(),
                }
            return LocatorProbe(count=count, sample=sample,
                                elapsed_ms=int((time.perf_counter() - started) * 1000))
        except Exception as exc:
            return LocatorProbe(count=0, error=str(exc)[:300],
                                elapsed_ms=int((time.perf_counter() - started) * 1000))

    async def scan_dom(self, ctx, *, max_elements: int = 200) -> list[dict]:
        """抓取当前页面可见元素的可定位属性（M3.5 / D28）。

        只做"采集"，不做分类 —— 候选生成在 ``domain.scan.build_candidates``。
        上限放宽到 max_elements 的 4 倍（容器/不可见会再被过滤掉）。
        """
        limit = max(50, max_elements * 4)
        script = """
        (limit) => {
          const SKIP = new Set(['SCRIPT','STYLE','META','LINK','HEAD','TITLE','NOSCRIPT','TEMPLATE','BR'])
          const out = []
          for (const el of document.querySelectorAll('body *')) {
            if (SKIP.has(el.tagName)) continue
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
              classes: (typeof el.className === 'string'
                ? el.className.trim().split(/\\s+/).filter(Boolean) : []).slice(0, 3),
              text: el.childElementCount === 0
                ? (el.innerText || el.textContent || '').trim().slice(0, 60) : '',
              visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length),
            })
            if (out.length >= limit) break
          }
          return out
        }
        """
        items = await self._page.evaluate(script, limit)
        return items or []

    # ─────────────────────── 其余动作 ───────────────────────
    async def hover(self, chain, ctx, **_) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        await locator.hover(timeout=ctx.timeout_ms)

    async def select_option(self, chain, ctx, *, value: str | None = None,
                            label: str | None = None, index: int | None = None) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        if value is not None:
            await locator.select_option(value=value)
        elif label is not None:
            await locator.select_option(label=label)
        elif index is not None:
            await locator.select_option(index=index)
        else:
            raise ValueError("select_option 需要 value / label / index 之一")

    async def double_click(self, chain, ctx, **_) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        await locator.dblclick(timeout=ctx.timeout_ms)

    async def scroll_to_element(self, chain, ctx, **_) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        await locator.scroll_into_view_if_needed(timeout=ctx.timeout_ms)

    async def drag(self, chain, ctx, *, target_element_id: int | None = None,
                   duration_ms: int = 500) -> None:
        if target_element_id is None:
            raise ValueError("drag 需要 target_element_id")
        target_chain = ctx.resolved_chains.get(target_element_id)
        if target_chain is None:
            raise ValueError(f"执行器未预解析目标元素 {target_element_id} 的定位链")
        source, _, _ = await self._first_visible(chain, ctx)
        target = self._locator(target_chain.first).first
        await source.drag_to(target, timeout=ctx.timeout_ms)

    async def coordinate_click(self, chain, ctx, *, x: int, y: int) -> None:
        await self._page.mouse.click(x, y)

    async def upload_file(self, chain, ctx, *, file_path: str) -> None:
        locator, _, _ = await self._first_visible(chain, ctx)
        await locator.set_input_files(file_path)

    async def element_list(self, chain, ctx, *, output_var: str | None = None) -> list:
        locator = self._locator(chain.first)
        count = await locator.count()
        items = []
        for i in range(min(count, 200)):
            item = locator.nth(i)
            items.append({
                "index": i,
                "text": (await item.inner_text())[:200],
                "visible": await item.is_visible(),
            })
        return ctx.set_var(output_var, items)

    async def navigate(self, chain, ctx, *, url: str,
                       wait_until: str = "domcontentloaded") -> None:
        """GAP-11：等待条件可配。

        ``domcontentloaded`` 对 SPA 常常太早（DOM 有了但业务组件还没挂载），
        一键接入场景用 ``load`` 更稳；需要"等到没有网络请求"才用 ``networkidle``。
        """
        await self._page.goto(url, wait_until=wait_until, timeout=ctx.timeout_ms)

    async def go_back(self, chain, ctx, **_) -> None:
        await self._page.go_back(wait_until="domcontentloaded")

    async def go_forward(self, chain, ctx, **_) -> None:
        await self._page.go_forward(wait_until="domcontentloaded")

    async def refresh(self, chain, ctx, **_) -> None:
        await self._page.reload(wait_until="domcontentloaded")

    async def switch_to_iframe(self, chain, ctx, *, index: int | None = None) -> None:
        """D12：带参进、无参弹栈（单动作，不新增 switch_to_main_frame）。"""
        if index is None:
            if self._frame_stack:
                self._frame_stack.pop()
            return
        frames = self._page.frames
        # index=0 表示第一个子 frame（frames[0] 是 main frame）
        target = frames[index + 1] if len(frames) > index + 1 else None
        if target is None:
            raise ValueError(f"iframe index={index} 不存在（共 {len(frames) - 1} 个子 frame）")
        self._frame_stack.append(target)

    async def switch_to_page(self, chain, ctx, *, index: int = -1) -> None:
        pages = self._context.pages
        self._page = pages[index]
        self._frame_stack.clear()

    async def page_scroll(self, chain, ctx, *, direction: str = "down",
                          distance: int = 500, to: str | None = None) -> None:
        if to == "bottom":
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        elif to == "top":
            await self._page.evaluate("window.scrollTo(0, 0)")
        else:
            dy = distance if direction == "down" else -distance
            await self._page.mouse.wheel(0, dy)

    async def get_url(self, chain, ctx, *, output_var: str | None = None) -> str:
        return ctx.set_var(output_var, self._page.url)

    async def get_title(self, chain, ctx, *, output_var: str | None = None) -> str:
        return ctx.set_var(output_var, await self._page.title())

    async def get_cookies(self, chain, ctx, *, output_var: str | None = None) -> list:
        return ctx.set_var(output_var, await self._context.cookies())

    async def set_cookies(self, chain, ctx, *, cookies: list) -> None:
        await self._context.add_cookies(cookies)

    async def delete_cookies(self, chain, ctx, **_) -> None:
        await self._context.clear_cookies()

    async def accept_dialog(self, chain, ctx, *, accept: bool = True,
                            dialog_text: str | None = None) -> None:
        """只设置"后续弹窗策略"；handler 已在 start() 预注册。"""
        self._dialog_policy = {"accept": bool(accept), "text": dialog_text}
