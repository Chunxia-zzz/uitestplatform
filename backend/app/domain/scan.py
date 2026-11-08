"""页面扫描的候选分类与定位符生成（纯函数，零依赖，可单测）。

这里不碰 Playwright、不碰数据库 —— 只把"扫描脚本抓到的原始 DOM 项"变成
"候选元素 + 建议定位符 + 稳定性分级"。真正的 DOM 抓取在 ``playwright_adapter.scan_dom()``，
这里只做纯逻辑。

定位符优先级（FR63）：
    data-testid → id → name → role+aria-label → aria-label → placeholder
    → alt → title → href → src → text(叶子且 2~30 字) → css(tag 限定)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# 结构噪音 / 默认不参与交互的标签
NOISE_TAGS = frozenset({
    "script", "style", "meta", "link", "head", "title", "noscript", "template", "br",
    "html", "body",
})

# 纯容器：默认跳过，除非带 data-testid / id / role
# form 本质是容器（真正的交互在 input/button），但带 id/testid 时是"表单锚点"，保留
CONTAINER_TAGS = frozenset({
    "div", "span", "section", "article", "main", "header", "footer", "nav",
    "ul", "ol", "li", "aside", "figure", "form", "table", "tr", "td", "th",
})

# 交互 / 可断言标签（默认保留）
INTERACTIVE_TAGS = frozenset({
    "a", "button", "input", "select", "textarea", "option", "label",
    "img", "iframe", "h1", "h2", "h3", "h4", "h5", "h6", "p",
})

STRONG = "strong"
MEDIUM = "medium"
WEAK = "weak"


@dataclass
class LocatorHint:
    locator_type: str
    locator_value: str
    primary: bool = False


@dataclass
class Candidate:
    key: str
    tag: str
    name: str
    text: str
    strength: str
    locators: list[LocatorHint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "tag": self.tag, "name": self.name, "text": self.text,
            "strength": self.strength,
            "locators": [
                {"locator_type": loc.locator_type, "locator_value": loc.locator_value,
                 "primary": loc.primary}
                for loc in self.locators
            ],
        }


# ─────────────────────────── 定位符生成 ───────────────────────────
def _hints(item: dict[str, Any]) -> list[LocatorHint]:
    """按优先级产出定位符建议；第一命中的是 primary。"""
    out: list[LocatorHint] = []

    def add(typ: str, value: Any) -> bool:
        if value is not None and str(value).strip():
            out.append(LocatorHint(typ, str(value).strip()))
            return True
        return False

    add("testid", item.get("testid"))
    add("id", item.get("id"))
    add("name", item.get("name"))

    # role + aria-label 组合（Playwright get_by_role(name=...) 的标准形态）
    if item.get("role") and item.get("ariaLabel"):
        out.append(LocatorHint("role", item["role"], primary=False))
        # 附加 name 提示，供前端展示
        out.append(LocatorHint("label", item["ariaLabel"]))
    elif add("ariaLabel", item.get("ariaLabel")):
        # 语义类型里用 label 表达 aria-label（M2 字典：WEB 支持 label）
        out[-1] = LocatorHint("label", item["ariaLabel"])

    add("placeholder", item.get("placeholder"))
    add("alt", item.get("alt"))
    add("title", item.get("title"))
    add("href", item.get("href"))
    add("src", item.get("src"))

    # 文本定位：仅叶子节点 + 长度适中（避免整段文章当定位符）
    text = (item.get("text") or "").strip()
    if 2 <= len(text) <= 30:
        add("text", text)

    # css 兜底：tag 限定 + 类名（最弱）
    classes = item.get("classes") or []
    if classes:
        add("css", f"{item['tag']}.{'.'.join(classes)}")

    if out:
        out[0].primary = True
    return out


def _strength(locators: list[LocatorHint]) -> str:
    primary_type = locators[0].locator_type if locators else ""
    if primary_type in ("testid", "id", "name"):
        return STRONG
    if primary_type in ("role", "label", "placeholder", "alt", "title", "href", "src"):
        return MEDIUM
    return WEAK


def _default_name(item: dict[str, Any]) -> str:
    """人工可改的默认名：可读属性 > 文本 > tag。"""
    for attr in ("ariaLabel", "placeholder", "name", "alt", "title"):
        value = (item.get(attr) or "").strip()
        if value:
            return value[:40]
    text = (item.get("text") or "").strip()
    if text:
        return text[:40]
    return item.get("tag", "元素")


# ─────────────────────────── 过滤 ───────────────────────────
def should_include(item: dict[str, Any]) -> bool:
    """容器默认跳过，除非带唯一属性；噪音标签一律跳过。"""
    tag = item.get("tag", "")
    if tag in NOISE_TAGS:
        return False
    if tag in CONTAINER_TAGS:
        # 带 testid / id / role 的容器是"区块锚点"，保留给人判断
        return bool(item.get("testid") or item.get("id") or item.get("role"))
    return True


# ─────────────────────────── 主入口 ───────────────────────────
def build_candidates(raw_items: list[dict[str, Any]], *,
                     max_elements: int = 200) -> tuple[list[Candidate], dict[str, int]]:
    """把扫描脚本返回的原始 DOM 项 → 候选清单 + 统计。"""
    candidates: list[Candidate] = []
    stats = {"total": 0, "strong": 0, "medium": 0, "weak": 0, "skipped": 0}
    seen_primary: set[tuple[str, str]] = set()

    for item in raw_items:
        if not item.get("visible"):
            stats["skipped"] += 1
            continue
        if not should_include(item):
            stats["skipped"] += 1
            continue

        locators = _hints(item)
        if not locators:
            stats["skipped"] += 1
            continue

        # 主定位符去重（同一 testid/id 出现两次，只留第一个）
        primary = (locators[0].locator_type, locators[0].locator_value)
        if primary in seen_primary:
            stats["skipped"] += 1
            continue
        seen_primary.add(primary)

        strength = _strength(locators)
        candidates.append(Candidate(
            key=f"c{len(candidates) + 1}",
            tag=item.get("tag", ""),
            name=_default_name(item),
            text=(item.get("text") or "")[:80],
            strength=strength,
            locators=locators,
        ))
        stats["total"] += 1
        stats[strength] += 1

        if len(candidates) >= max_elements:
            break

    return candidates, stats
