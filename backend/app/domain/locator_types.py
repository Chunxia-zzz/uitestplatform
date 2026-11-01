"""定位类型字典（三端）。

分层约束（冻结项 FR18 / M2 §2.5）：

1. 只表达**语义**，绝不出现引擎语汇（``-android uiautomator`` / ``resourceId=`` / ``-ios predicate string``）。
   同一个 resource-id 是**一条业务事实**，由适配器翻译成各引擎的写法。
2. ``engines`` 声明"哪些引擎能翻译这个语义" → 写入期做引擎维度校验。
3. 本模块零业务依赖（RL-M2-2），可被 registry / services / api 三方引用。
"""
from __future__ import annotations

from dataclasses import dataclass, field

PLATFORM_WEB, PLATFORM_ANDROID, PLATFORM_IOS = "WEB", "ANDROID", "IOS"

WEB_ENGINES = frozenset({"playwright"})
ANDROID_ENGINES = frozenset({"appium", "uiautomator2"})
IOS_ENGINES = frozenset({"appium"})


@dataclass(frozen=True, slots=True)
class LocatorTypeSpec:
    key: str
    label: str
    example: str
    engines: frozenset[str]
    rank: int          # 1 = 最稳；决定新建时默认 priority = rank * 10
    note: str = ""


@dataclass(frozen=True, slots=True)
class PlatformLocators:
    platform: str
    label: str
    engines: frozenset[str]
    types: dict[str, LocatorTypeSpec] = field(default_factory=dict)

    def get(self, key: str) -> LocatorTypeSpec | None:
        return self.types.get(key)


def _t(key: str, label: str, example: str, engines, rank: int, note: str = "") -> LocatorTypeSpec:
    return LocatorTypeSpec(key, label, example, frozenset(engines), rank, note)


WEB = PlatformLocators("WEB", "Web 端", WEB_ENGINES, {
    "testid": _t("testid", "测试标识", "login-submit", WEB_ENGINES, 1,
                 "首选。前后端约定 data-testid，最稳、与样式解耦"),
    "role": _t("role", "无障碍角色", 'button[name="登录"]', WEB_ENGINES, 2,
               "语义稳定，适合表单与可访问性良好的页面"),
    "label": _t("label", "表单标签", "用户名", WEB_ENGINES, 3, "对应 getByLabel"),
    "placeholder": _t("placeholder", "占位符", "请输入用户名", WEB_ENGINES, 4, "输入框专用"),
    "id": _t("id", "元素 ID", "loginForm", WEB_ENGINES, 5, "稳定，但易被前端重构改掉"),
    "css": _t("css", "CSS 选择器", "#loginForm .btn-primary", WEB_ENGINES, 6,
              "通用兜底；别写太深的层级"),
    "text": _t("text", "可见文本", "登录", WEB_ENGINES, 7, "文案会变；只用于稳定文案"),
    "title": _t("title", "title 属性", "提交登录", WEB_ENGINES, 8, "少用"),
    "alt": _t("alt", "图片 alt", "用户头像", WEB_ENGINES, 9, "图片专用"),
    "class": _t("class", "class 名", "btn-primary", WEB_ENGINES, 10, "最不稳：样式类名最易变"),
    "xpath": _t("xpath", "XPath", '//button[@type="submit"]', WEB_ENGINES, 11,
                "最后手段，慢且脆"),
})

ANDROID = PlatformLocators("ANDROID", "Android 端", ANDROID_ENGINES, {
    "resource_id": _t("resource_id", "资源 ID", "com.demo:id/login_btn", ANDROID_ENGINES, 1,
                      "首选。语义 = resource-id；Appium 译为 id=…，u2 译为 resourceId=…"),
    "accessibility_id": _t("accessibility_id", "无障碍 ID", "loginBtn", ANDROID_ENGINES, 2,
                           "对应 content-desc，跨引擎最一致"),
    "uiautomator": _t("uiautomator", "UiSelector 表达式",
                      'new UiSelector().text("登录")', {"appium"}, 3,
                      "引擎专属表达式，不能用于 engine_key='*'"),
    "text": _t("text", "精确文本", "登录", ANDROID_ENGINES, 4, "文案会变"),
    "text_contains": _t("text_contains", "文本包含", "登 录", ANDROID_ENGINES, 5,
                        "精确匹配不到时的兜底"),
    "class_name": _t("class_name", "控件类名", "android.widget.Button", ANDROID_ENGINES, 6,
                     "粒度太粗，常命中多个"),
    "xpath": _t("xpath", "XPath", '//android.widget.Button[@text="登录"]',
                ANDROID_ENGINES, 7, "最后手段，慢"),
})

#: ★ iOS 的 xpath 必须排最后：逐节点求值，复杂页面可慢到秒级（D1a）
IOS = PlatformLocators("IOS", "iOS 端", IOS_ENGINES, {
    "accessibility_id": _t("accessibility_id", "无障碍 ID", "loginBtn", IOS_ENGINES, 1,
                           "首选。需开发设 accessibilityIdentifier"),
    "predicate": _t("predicate", "谓词表达式",
                    "type == 'XCUIElementTypeButton' AND label == '登录'", IOS_ENGINES, 2,
                    "灵活，性能可接受"),
    "class_chain": _t("class_chain", "类链",
                      '**/XCUIElementTypeButton[`label == "登录"`]', IOS_ENGINES, 3,
                      "比 XPath 快得多"),
    "name": _t("name", "name 属性", "loginBtn", IOS_ENGINES, 4, "兼容旧写法"),
    "xpath": _t("xpath", "XPath", '//XCUIElementTypeButton[@name="loginBtn"]', IOS_ENGINES, 5,
                "⚠️ 必须放最后：iOS 上 XPath 性能极差"),
})

LOCATOR_TYPES: dict[str, PlatformLocators] = {
    PLATFORM_WEB: WEB,
    PLATFORM_ANDROID: ANDROID,
    PLATFORM_IOS: IOS,
}

#: 引擎语汇黑名单：出现在 locator_type 里就说明分层被破坏（U1 测试会扫）
FORBIDDEN_TYPE_TOKENS = (
    "uiautomator2", "-android", "-ios", "predicate string", "resourceId=", "classChain",
    "css=", "xpath=", "testid=", "~",
)


def get_spec(platform: str, locator_type: str) -> LocatorTypeSpec | None:
    pl = LOCATOR_TYPES.get(platform)
    return pl.get(locator_type) if pl else None


def default_priority(platform: str, locator_type: str) -> int:
    spec = get_spec(platform, locator_type)
    return (spec.rank * 10) if spec else 100


def platform_engines(platform: str) -> frozenset[str]:
    pl = LOCATOR_TYPES.get(platform)
    return pl.engines if pl else frozenset()


def as_dict() -> dict:
    """供 ``GET /locator-types`` 返回（前端下拉 + 不合选项过滤）。"""
    return {
        p: {
            "platform": pl.platform,
            "label": pl.label,
            "engines": sorted(pl.engines),
            "types": [
                {
                    "key": t.key, "label": t.label, "example": t.example,
                    "engines": sorted(t.engines), "rank": t.rank, "note": t.note,
                }
                for t in sorted(pl.types.values(), key=lambda x: x.rank)
            ],
        }
        for p, pl in LOCATOR_TYPES.items()
    }
