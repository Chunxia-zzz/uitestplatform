"""Playwright 适配器（一期唯一真实实现）。

定位符翻译（语义 → Playwright 语汇）全部收敛在 ``_locator()``：
库里的 ``locator_type`` 是语义（testid / role / resource_id …），
Playwright 的语汇（``[data-testid=…]`` / ``role=…`` / ``get_by_label``）只出现在这里。
"""
from __future__ import annotations

import asyncio
import json as _jsonlib
import logging
import os
import re
import time
from collections import deque
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.core.errors import ValidationFailed
from app.domain.enums import Platform
from app.engines.base import (
    ActionContext,
    EngineAdapter,
    Locator,
    LocatorChain,
    LocatorProbe,
    SessionConfig,
)

logger = logging.getLogger(__name__)


def _esc(value: str) -> str:
    return value.replace('"', '\\"')


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Playwright URL glob → 正则（wait_for_response 的收集器匹配用）。

    语义与 page.route 的 URL 通配一致：``**`` 匹配任意字符（含 /）、
    ``*`` 匹配除 / 外的任意字符、``?`` 单个非 / 字符，其余字面量。
    """
    parts: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*" and pattern[i:i + 2] == "**":
            parts.append(".*")
            i += 2
        elif ch == "*":
            parts.append("[^/]*")
            i += 1
        elif ch == "?":
            parts.append("[^/]")
            i += 1
        else:
            parts.append(re.escape(ch))
            i += 1
    return re.compile("".join(parts) + "$", re.IGNORECASE)


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
        # M3.8（GAP-09）：mock 注册表与网络响应收集器
        # key = (pattern, method或None)；value = 注册的 handler（供精确 unroute）
        self._active_routes: dict[tuple[str, str | None], Any] = {}
        # (ts, url, status, method) —— ts 为 time.perf_counter 语义，与
        # 执行器 case_started_ts 同钟；maxlen 防长执行内存膨胀。
        self._responses: deque[tuple[float, str, int, str]] = deque(maxlen=500)

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
            if isinstance(storage_state, str) and not await asyncio.to_thread(
                    os.path.isfile, storage_state):
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
        # M3.8（GAP-09）：网络响应收集器 —— wait_for_response 的数据源；
        # 只做内存记录，异常吞掉绝不影响页面/执行（R5 风格）。
        self._page.on("response", self._on_response)
        self._session_id = f"pw-{int(time.time() * 1000)}"

    def _on_response(self, response) -> None:
        try:
            self._responses.append((time.perf_counter(), response.url,
                                    response.status, response.request.method))
        except Exception:                              # pragma: no cover
            logger.debug("collect response failed", exc_info=True)

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
                target = await asyncio.to_thread(
                    os.path.abspath, self._save_storage_state)
                await asyncio.to_thread(
                    os.makedirs, os.path.dirname(target), exist_ok=True)
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
        self._active_routes.clear()
        self._responses.clear()

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

    async def reset_case_scope(self) -> None:
        """用例边界清理（M3.8 FR-M3.8-4）：mock 全部解除 + iframe 弹栈清空。

        同执行串行复用 adapter，上一用例遗留的 route/frame 状态会污染下一用例；
        执行器在每个用例开始时调用本钩子（前用例异常中断也能兜住）。
        """
        if self._page is None:
            self._active_routes.clear()
            return
        try:
            await self._page.unroute_all()
        except Exception:
            logger.warning("unroute_all failed", exc_info=True)
        self._active_routes.clear()
        self._frame_stack.clear()

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
        size_bytes = await asyncio.to_thread(os.path.getsize, target_path)
        ctx.artifacts.append({"kind": "SCREENSHOT", "path": target_path,
                              "size_bytes": size_bytes})
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
          const SKIP = new Set(['SCRIPT','STYLE','META','LINK','HEAD',
                                'TITLE','NOSCRIPT','TEMPLATE','BR'])
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
        """D12：带参进、无参弹栈（单动作，不新增 switch_to_main_frame）。

        M3.8（GAP-12）新增"按元素进入"：步骤绑定 iframe 元素即进入该 iframe
        （与出现顺序无关）；绑定与 index 互斥由写入口保证，此处只做防御。
        """
        if chain is not None:
            if index is not None:                      # 防御：写入口已拦
                raise ValidationFailed("switch_to_iframe 绑定元素与 index 只能二选一")
            locator, _, _ = await self._first_visible(chain, ctx)
            handle = await locator.element_handle()
            frame = await handle.content_frame() if handle is not None else None
            if frame is None:
                raise ValidationFailed(
                    f"元素 {chain.element_id} 命中的不是 iframe 节点，无法进入"
                    "（请检查定位符是否指向 <iframe>/<frame>）")
            self._frame_stack.append(frame)
            return
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

    # ─────────────── 网络动作（M3.8 / GAP-09）───────────────
    async def mock_route(self, chain, ctx, *, pattern: str, method: str | None = None,
                         status: int = 200, content_type: str | None = None,
                         body: str | None = None, json: dict | None = None,
                         abort: bool = False) -> None:
        """声明接口 mock：匹配请求不再到达真实后端（FR-M3.8-1/2）。

        * key = (pattern, method)；同 key 重复声明**后写覆盖**（先摘旧 handler）。
        * method 过滤在 handler 内判断：不匹配的请求 ``route.fallback()``
          交给下一个 handler（同 pattern 不同 method 可各自 mock）。
        * 响应体：``json``（application/json）或 ``body``（text/plain）
          二选一，写入口已拦同给；``abort=True`` 时直接中断、其余字段忽略。
        * 参数名 ``json`` 遮蔽模块是 FR4 冻结约定（kwargs 名 == schema 属性名）
          的代价 —— 模块引用走 ``_jsonlib`` 别名。
        """
        method_key = method.upper() if method else None
        key = (pattern, method_key)

        async def handler(route) -> None:
            if method_key and route.request.method.upper() != method_key:
                await route.fallback()
                return
            if abort:
                await route.abort()
                return
            if json is not None:
                payload = _jsonlib.dumps(json, ensure_ascii=False)
                ctype = content_type or "application/json"
            elif body is not None:
                payload = body
                ctype = content_type or "text/plain"
            else:
                payload = ""
                ctype = content_type or "text/plain"
            await route.fulfill(status=status, body=payload,
                                content_type=ctype)

        old = self._active_routes.get(key)
        if old is not None:                            # 覆盖：先摘旧 handler
            try:
                await self._page.unroute(pattern, old)
            except Exception:
                logger.warning("unroute old mock failed: %s", pattern, exc_info=True)
        await self._page.route(pattern, handler)
        self._active_routes[key] = handler

    async def unmock_route(self, chain, ctx, *, pattern: str,
                           method: str | None = None) -> None:
        """解除 mock（FR-M3.8-3）：key 精确匹配；不存在报 ValidationFailed。"""
        method_key = method.upper() if method else None
        key = (pattern, method_key)
        handler = self._active_routes.pop(key, None)
        if handler is None:
            raise ValidationFailed(
                f"mock 声明不存在：pattern={pattern!r} method={method_key!r}"
                "（解除必须与声明时完全一致）",
                {"pattern": pattern, "method": method_key})
        try:
            await self._page.unroute(pattern, handler)
        except Exception:
            logger.warning("unroute failed: %s", pattern, exc_info=True)

    async def wait_for_response(self, chain, ctx, *, pattern: str,
                                method: str | None = None,
                                expect_status: int | None = None,
                                output_var: str | None = None) -> dict:
        """等待/检索网络响应（FR-M3.8-5/6）。

        在 ``ctx.timeout_ms`` 窗口内轮询收集器，匹配**自当前用例开始以来**的
        最新一条；``expect_status`` 给出则状态不符视为未命中继续等。
        超时抛 ValidationFailed，message 附近邻请求摘要（排查模式写错）。
        """
        regex = _glob_to_regex(pattern)
        method_key = method.upper() if method else None
        since = ctx.case_started_ts
        interval = max(1, settings.assert_poll_interval_ms) / 1000
        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0, ctx.timeout_ms) / 1000
        while True:
            hit = self._search_responses(regex, method_key, expect_status, since)
            if hit is not None:
                return ctx.set_var(output_var, hit)
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, remaining))

        recent = [f"{u} -> {s}" for _, u, s, _ in list(self._responses)[-5:]]
        raise ValidationFailed(
            f"等待网络响应超时（{ctx.timeout_ms}ms）：没有匹配 {pattern!r}"
            + (f" 且 method={method_key}" if method_key else "")
            + (f" 且 status={expect_status}" if expect_status is not None else "")
            + " 的响应；近期请求：" + ("; ".join(recent) if recent else "（无记录）"),
            {"pattern": pattern, "method": method_key, "expect_status": expect_status})

    def _search_responses(self, regex: re.Pattern[str], method_key: str | None,
                          expect_status: int | None,
                          since: float | None) -> dict | None:
        """倒序找最新一条匹配记录；无 case_started_ts 参考时不做时间过滤。"""
        for ts, url, status, m in reversed(self._responses):
            if since is not None and ts < since:
                continue
            if method_key and m.upper() != method_key:
                continue
            if expect_status is not None and status != expect_status:
                continue
            if regex.match(url):
                return {"url": url, "status": status, "method": m}
        return None

    async def download_file(self, chain, ctx, *, output_var: str | None = None) -> str:
        """点击绑定元素并接管浏览器下载（M3.8 / GAP-10，FR-M3.8-7/8/9）。

        文件保存为 ``{artifacts_dir}/exec-{id}/downloads/{seq}-{文件名}``，
        经 ``ctx.artifacts``（kind=DOWNLOAD）由执行器落库（FR34）；
        多文件只保存第一个；未产生下载则超时失败。
        """
        if ctx.execution_id is None:
            raise ValidationFailed("download_file 只能在执行链路中使用（缺 execution_id）")
        locator, _, _ = await self._first_visible(chain, ctx)
        download_dir = os.path.join(settings.artifacts_dir,
                                    f"exec-{ctx.execution_id}", "downloads")
        await asyncio.to_thread(os.makedirs, download_dir, exist_ok=True)
        async with self._page.expect_download(timeout=ctx.timeout_ms) as dl_info:
            await locator.click(timeout=ctx.timeout_ms)
        download = await dl_info.value
        suggested = os.path.basename(download.suggested_filename or "download.bin")
        target_path = os.path.join(download_dir, f"{ctx.step_seq}-{suggested}")
        await download.save_as(target_path)
        size_bytes = await asyncio.to_thread(os.path.getsize, target_path)
        # FR34：只登记"路径事实"，落库由执行器负责（同 screenshot 通道）
        ctx.artifacts.append({"kind": "DOWNLOAD", "path": target_path,
                              "size_bytes": size_bytes})
        return ctx.set_var(output_var, os.path.basename(target_path))
