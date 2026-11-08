"""M3.8 iframe 按元素进入 + 下载产物化单测（GAP-12 执行侧 / GAP-10 / spec US2、US3）。"""
from __future__ import annotations

import pytest

from app.core.errors import ValidationFailed
from app.engines.adapters.playwright_adapter import PlaywrightAdapter
from app.engines.base import ActionContext, Locator, LocatorChain


def chain_one() -> LocatorChain:
    return LocatorChain.of(7, [Locator(type="css", value="iframe#pay", locator_id=1)])


class FakeFirst:
    def __init__(self, handle):
        self._handle = handle

    async def wait_for(self, state=None, timeout=None):  # noqa: ASYNC109  # Playwright signature parity
        return None

    async def element_handle(self):
        return self._handle

    async def click(self, timeout=None):  # noqa: ASYNC109  # Playwright signature parity
        return None


class FakeLocator:
    def __init__(self, handle):
        self.first = FakeFirst(handle)


def base_adapter() -> PlaywrightAdapter:
    adapter = PlaywrightAdapter()
    adapter._page = object()      # type: ignore[assignment]
    adapter._frame_stack = []     # type: ignore[attr-defined]
    return adapter


class FrameHandle:
    def __init__(self, frame):
        self._frame = frame

    async def content_frame(self):
        return self._frame


class NullHandle:
    async def content_frame(self):
        return None


# ─────────────────────────── switch_to_iframe 元素形态 ───────────────────────────
@pytest.mark.asyncio
async def test_switch_to_iframe_by_element_pushes_frame():
    marker = object()
    adapter = base_adapter()
    adapter._locator = lambda loc: FakeLocator(FrameHandle(marker))  # type: ignore[method-assign]
    await adapter.switch_to_iframe(chain_one(), ActionContext())
    assert adapter._frame_stack == [marker]


@pytest.mark.asyncio
async def test_switch_to_iframe_element_not_iframe_fails():
    adapter = base_adapter()
    adapter._locator = lambda loc: FakeLocator(NullHandle())  # type: ignore[method-assign]
    with pytest.raises(ValidationFailed) as ei:
        await adapter.switch_to_iframe(chain_one(), ActionContext())
    assert "不是 iframe" in str(ei.value)


@pytest.mark.asyncio
async def test_switch_to_iframe_element_with_index_defensive_fail():
    """写入口已拦互斥；执行口再拦一道（防御）。"""
    adapter = base_adapter()
    adapter._locator = lambda loc: FakeLocator(FrameHandle(object()))  # type: ignore[method-assign]
    with pytest.raises(ValidationFailed):
        await adapter.switch_to_iframe(chain_one(), ActionContext(), index=0)


@pytest.mark.asyncio
async def test_switch_to_iframe_pop_keeps_semantics():
    adapter = base_adapter()
    adapter._frame_stack = [object(), object()]  # type: ignore[attr-defined]
    await adapter.switch_to_iframe(None, ActionContext())
    assert len(adapter._frame_stack) == 1


# ─────────────────────────── download_file ───────────────────────────
class FakeDownload:
    suggested_filename = "report.csv"

    async def save_as(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("col1,col2\n1,2\n")


class FakeDownloadCm:
    """模拟 Playwright expect_download：``cm.value`` 可被 await 拿到 download。"""

    def __init__(self):
        self._dl = FakeDownload()
        self.value = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __await__(self):
        async def _get():
            return self._dl
        return _get().__await__()


class FakeDownloadPage:
    def expect_download(self, timeout=None):
        return FakeDownloadCm()


@pytest.mark.asyncio
async def test_download_file_saves_and_registers_artifact(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    adapter = base_adapter()
    adapter._page = FakeDownloadPage()  # type: ignore[assignment]
    adapter._locator = lambda loc: FakeLocator(object())  # type: ignore[method-assign]
    ctx = ActionContext(execution_id=42, step_seq=3, timeout_ms=5000)
    name = await adapter.download_file(chain_one(), ctx, output_var="fname")
    assert name == "3-report.csv"
    assert ctx.variables["fname"] == "3-report.csv"
    assert len(ctx.artifacts) == 1
    art = ctx.artifacts[0]
    assert art["kind"] == "DOWNLOAD"
    assert "exec-42" in art["path"] and "downloads" in art["path"]
    assert art["size_bytes"] > 0


@pytest.mark.asyncio
async def test_download_file_requires_execution_id():
    adapter = base_adapter()
    adapter._page = FakeDownloadPage()  # type: ignore[assignment]
    adapter._locator = lambda loc: FakeLocator(object())  # type: ignore[method-assign]
    with pytest.raises(ValidationFailed):
        await adapter.download_file(chain_one(), ActionContext())
