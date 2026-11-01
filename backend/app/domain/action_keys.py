"""统一动作字典 —— 51 条（M1 附录 B 的代码化版本，单一事实来源）。

约定（D6）：
* ``key`` 英文 ``snake_case``、语义自明；中文名只放 ``name`` 展示。
* ``engines=()`` 表示**平台内建动作**（不经过适配器，由 ``actions.dispatch`` 直接执行）。
* ``params_schema`` 由 ``props`` 生成 JSON Schema，供前端表单与写入期校验共用。

★ 冻结约定（M1 FR4）：适配器 **方法名 == key**、**关键字参数名 == props 的键名**，
   因此分发时可以直接 ``getattr(adapter, key)(chain, ctx, **params)``，不写映射表。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ALL = ("WEB", "ANDROID", "IOS")
WEB = ("WEB",)
MOBILE = ("ANDROID", "IOS")

PW = ("playwright",)
AP = ("appium",)
U2 = ("uiautomator2",)
PW_AP = ("playwright", "appium")
ALL_ENGINES = ("playwright", "appium", "uiautomator2")


@dataclass(frozen=True, slots=True)
class ActionDef:
    key: str
    name: str
    category: str
    platforms: tuple[str, ...]
    engines: tuple[str, ...]
    requires_element: bool
    props: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    note: str = ""

    @property
    def is_builtin(self) -> bool:
        return not self.engines

    @property
    def params_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "type": "object",
            "properties": dict(self.props),
            "additionalProperties": False,
        }
        if self.required:
            schema["required"] = list(self.required)
        if self.note:
            schema["description"] = self.note
        return schema


def _s(desc: str = "") -> dict[str, Any]:
    return {"type": "string", **({"description": desc} if desc else {})}


def _i(desc: str = "", default: int | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "integer"}
    if desc:
        d["description"] = desc
    if default is not None:
        d["default"] = default
    return d


def _b(desc: str = "", default: bool | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"type": "boolean"}
    if desc:
        d["description"] = desc
    if default is not None:
        d["default"] = default
    return d


_ACTIONS: list[ActionDef] = [
    # ───────────────── ELEMENT（20）─────────────────
    ActionDef("click", "点击", "ELEMENT", ALL, ALL_ENGINES, True),
    ActionDef("input", "输入", "ELEMENT", ALL, ALL_ENGINES, True,
              {"text": _s("要输入的文本"), "clear": _b("先清空")}, ("text",)),
    ActionDef("get_text", "取文本", "ELEMENT", ALL, ALL_ENGINES, True,
              {"output_var": _s("结果存入变量")}),
    ActionDef("get_attribute", "取属性", "ELEMENT", ALL, ALL_ENGINES, True,
              {"name": _s("属性名"), "output_var": _s()}, ("name",)),
    ActionDef("wait_element", "等待元素", "ELEMENT", ALL, ALL_ENGINES, True,
              {"state": _s("visible/attached/hidden"), "timeout_ms": _i()}),
    ActionDef("check_exists", "判断存在", "ELEMENT", ALL, ALL_ENGINES, True,
              {"output_var": _s("true/false 存入变量")}),
    ActionDef("hover", "悬停", "ELEMENT", ALL, PW_AP, True),
    ActionDef("select_option", "下拉选择", "ELEMENT", ("WEB", "IOS"), PW_AP, True,
              {"value": _s(), "label": _s(), "index": _i()}),
    ActionDef("double_click", "双击", "ELEMENT", ALL, ALL_ENGINES, True),
    ActionDef("long_press", "长按", "ELEMENT", MOBILE, ("appium", "uiautomator2"), True,
              {"duration_ms": _i(default=1000)}),
    ActionDef("scroll_to_element", "滚动到元素", "ELEMENT", ALL, ALL_ENGINES, True),
    ActionDef("drag", "拖拽", "ELEMENT", ALL, ALL_ENGINES, True,
              {"target_element_id": {"type": "integer"}, "duration_ms": _i()}),
    ActionDef("coordinate_click", "坐标点击", "ELEMENT", ALL, ALL_ENGINES, True,
              {"x": _i(), "y": _i()}, ("x", "y")),
    ActionDef("upload_file", "上传文件", "ELEMENT", WEB, PW, True,
              {"file_path": _s()}, ("file_path",)),
    ActionDef("element_scroll", "元素内滚动", "ELEMENT", MOBILE, ("appium", "uiautomator2"), True,
              {"direction": _s("up/down"), "distance": _i()}),
    ActionDef("page_swipe", "页面滑动", "ELEMENT", MOBILE, ("appium", "uiautomator2"), True,
              {"direction": _s("up/down/left/right"), "distance": _i()}),
    ActionDef("multi_finger_swipe", "多指滑动", "ELEMENT", MOBILE,
              ("appium", "uiautomator2"), True, {"direction": _s(), "distance": _i()}),
    ActionDef("swipe_up", "上滑", "ELEMENT", MOBILE, ("appium", "uiautomator2"), True,
              {"distance": _i()}),
    ActionDef("swipe_down", "下滑", "ELEMENT", MOBILE, ("appium", "uiautomator2"), True,
              {"distance": _i()}),
    ActionDef("element_list", "取元素列表", "ELEMENT", ALL, ALL_ENGINES, True,
              {"output_var": _s()}, note="返回匹配到的全部元素文本/属性"),

    # ───────────────── NAVIGATION（7）─────────────────
    ActionDef("navigate", "前往 URL", "NAVIGATION", WEB, PW, False,
              {"url": _s("绝对或相对 target.base_url"),
               "wait_until": {"type": "string",
                              "enum": ["commit", "domcontentloaded", "load", "networkidle"],
                              "description": "页面就绪条件；默认 domcontentloaded（GAP-11 / M3.4）"}},
              ("url",),
              note="SPA 建议 wait_until=load 或 networkidle"),
    ActionDef("go_back", "后退", "NAVIGATION", WEB, PW, False),
    ActionDef("go_forward", "前进", "NAVIGATION", WEB, PW, False),
    ActionDef("refresh", "刷新", "NAVIGATION", WEB, PW, False),
    ActionDef("switch_to_iframe", "进入/退出 iframe", "NAVIGATION", WEB, PW, False,
              {"index": _i("为空且无 element 时弹栈（D12）")},
              note="带参进、无参弹栈；单动作栈语义（D12），不新增 switch_to_main_frame"),
    ActionDef("switch_to_page", "切换标签页", "NAVIGATION", WEB, PW, False,
              {"index": _i(default=-1)}),
    ActionDef("page_scroll", "页面滚动", "NAVIGATION", WEB, PW, False,
              {"direction": _s("up/down"), "distance": _i(), "to": _s("top/bottom")}),

    # ───────────────── CONTEXT（2）─────────────────
    ActionDef("get_contexts", "取上下文列表", "CONTEXT", MOBILE, AP, False,
              {"output_var": _s()}, note="Appium context（NATIVE_APP / WEBVIEW_*）"),
    ActionDef("switch_to_context", "切换上下文", "CONTEXT", MOBILE, AP, False,
              {"context": _s()}, ("context",)),

    # ───────────────── APP_LIFECYCLE（6）─────────────────
    ActionDef("start_app", "启动 App", "APP_LIFECYCLE", MOBILE, ("appium", "uiautomator2"), False,
              {"app_package": _s(), "app_activity": _s()}),
    ActionDef("stop_app", "停止 App", "APP_LIFECYCLE", MOBILE, ("appium", "uiautomator2"), False,
              {"app_package": _s()}),
    ActionDef("restart_app", "重启 App", "APP_LIFECYCLE", MOBILE, ("appium", "uiautomator2"), False,
              {"app_package": _s()}),
    ActionDef("background_foreground", "前后台切换", "APP_LIFECYCLE", MOBILE,
              ("appium", "uiautomator2"), False, {"seconds": _i(default=3)}),
    ActionDef("go_home", "回到桌面", "APP_LIFECYCLE", MOBILE, ("appium", "uiautomator2"), False),
    ActionDef("fix_orientation", "固定屏幕方向", "APP_LIFECYCLE", MOBILE,
              ("appium", "uiautomator2"), False, {"orientation": _s("PORTRAIT/LANDSCAPE")}),

    # ───────────────── ASSERT（5，平台内建）─────────────────
    ActionDef("assert_equals", "断言相等", "ASSERT", ALL, (), False,
              {"actual": {}, "expected": {}}, ("actual", "expected"),
              note="字符串化后比较，避免 1 vs '1' 误判"),
    ActionDef("assert_contains", "断言包含", "ASSERT", ALL, (), False,
              {"actual": {}, "expected": {}}, ("actual", "expected")),
    ActionDef("assert_matches", "断言正则匹配", "ASSERT", ALL, (), False,
              {"actual": {}, "pattern": _s()}, ("actual", "pattern")),
    ActionDef("assert_visible", "断言可见", "ASSERT", ALL, (), True,
              {"element_id": {"type": "integer"}}),
    ActionDef("assert_not_exists", "断言不存在", "ASSERT", ALL, (), True,
              {"element_id": {"type": "integer"}}),

    # ───────────────── DATA（3）─────────────────
    ActionDef("set_variable", "设置变量", "DATA", ALL, (), False,
              {"name": _s(), "value": {}}, ("name", "value")),
    ActionDef("eval_expression", "变量表达式求值", "DATA", ALL, (), False,
              {"expression": _s(), "output_var": _s()}, ("expression",),
              note="仅支持白名单运算，禁止任意代码执行"),
    ActionDef("db_query", "数据库查询", "DATA", ALL, (), False,
              {"sql": _s(), "params": {"type": "array"}, "output_var": _s()}, ("sql",),
              note="只读连接 + 结果行数上限"),

    # ───────────────── SYSTEM（8）─────────────────
    ActionDef("screenshot", "截图", "SYSTEM", ALL, ALL_ENGINES, False,
              {"path": _s(), "full_page": _b(),
               "target": {"type": "string", "enum": ["page", "element"],
                          "description": "element 表示只截绑定元素（需步骤绑定元素）；默认 page"}},
              note="M3.2 新增 target=element（元素级截图，GAP-07）"),
    ActionDef("get_url", "取当前 URL", "SYSTEM", WEB, PW, False, {"output_var": _s()}),
    ActionDef("get_title", "取页面标题", "SYSTEM", WEB, PW, False, {"output_var": _s()}),
    ActionDef("get_cookies", "取 Cookie", "SYSTEM", WEB, PW, False, {"output_var": _s()}),
    ActionDef("set_cookies", "设置 Cookie", "SYSTEM", WEB, PW, False,
              {"cookies": {"type": "array"}}, ("cookies",)),
    ActionDef("delete_cookies", "清空 Cookie", "SYSTEM", WEB, PW, False),
    ActionDef("accept_dialog", "处理弹窗", "SYSTEM", WEB, PW, False,
              {"accept": _b(default=True), "dialog_text": _s()},
              note="需预注册 dialog handler，否则页面永久阻塞（M1 §2.5.8）"),
    ActionDef("run_python", "执行 Python 代码", "SYSTEM", ALL, (), False,
              {"code": _s(), "output_var": _s()}, ("code",),
              note="默认禁用（UIP_ALLOW_RUN_PYTHON=false）；开启时受限命名空间 + 强制超时（D11）"),
]

#: 动作全集（顺序即展示顺序与 sort 值来源）
ACTION_CATALOG: tuple[ActionDef, ...] = tuple(_ACTIONS)
ACTION_BY_KEY: dict[str, ActionDef] = {a.key: a for a in ACTION_CATALOG}
ACTION_KEYS: frozenset[str] = frozenset(ACTION_BY_KEY)

#: 平台内建动作（不经过适配器）
BUILTIN_ACTION_KEYS: frozenset[str] = frozenset(a.key for a in ACTION_CATALOG if a.is_builtin)

assert len(ACTION_CATALOG) == 51, f"动作字典应为 51 条，实际 {len(ACTION_CATALOG)}"
assert len(ACTION_BY_KEY) == 51, "动作 key 有重复"


def sort_of(key: str) -> int:
    """稳定排序值：按声明顺序 ×10，便于插入。"""
    for i, a in enumerate(ACTION_CATALOG, start=1):
        if a.key == key:
            return i * 10
    return 9990
