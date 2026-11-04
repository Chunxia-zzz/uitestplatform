"""运行配置（环境变量前缀 ``UIP_``）。"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.enums import MAX_TREE_DEPTH, MAX_VERIFY_LOCATORS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="UIP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "UI 自动化平台"
    env: str = "dev"
    log_level: str = "INFO"

    #: 默认 SQLite（零依赖起步）；生产改 mysql+aiomysql://user:pwd@host:3306/uitest
    database_url: str = "sqlite+aiosqlite:///./data/uitest.db"
    db_echo: bool = False

    #: 前端 dev server 与本地预览
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    #: D11：run_python 默认禁用；开启时受限命名空间 + 超时强杀
    allow_run_python: bool = False
    run_python_timeout_s: float = 5.0

    #: 树形（D15）
    max_tree_depth: int = MAX_TREE_DEPTH

    #: 执行 / 验证
    default_timeout_ms: int = 15_000
    #: GAP-03：断言在 timeout_ms 窗口内轮询的间隔（不是"重试 N 次"，见 Q-05）
    assert_poll_interval_ms: int = 200
    verify_total_timeout_s: float = 30.0
    verify_probe_timeout_s: float = 5.0
    verify_max_locators: int = MAX_VERIFY_LOCATORS
    headless: bool = True

    #: M3.1 执行内核（D21 / D23）
    max_concurrent_executions: int = 2
    max_pending: int = 200
    report_dir: str = "./reports"
    event_log_dir: str = "./events"
    #: 定时任务时区（M3.3）
    timezone: str = "Asia/Shanghai"

    artifacts_dir: str = "./artifacts"

    # ── M3.6 GAP-08：诊断录制（D35）────────────────────────────
    #: 全局 trace 模式：off / on-failure / always（target options 可覆盖）
    trace: str = "on-failure"
    #: 全程录屏（Playwright 限制：无法按执行结果取舍，开启即全程）
    video: bool = False
    #: 全程录制 HAR
    har: bool = False

    # ── M3.6 GAP-20 / M3.7 GAP-43：通知（D32 / D33 / D39 / D41）────
    #: 通知渠道单选：wecom（默认，向后兼容）/ feishu
    notify_channel: Literal["wecom", "feishu"] = "wecom"
    #: 企微群机器人 webhook 完整 URL；空串 = 该渠道禁用
    notify_wecom_webhook: str = ""
    #: 飞书自定义机器人 webhook；空串 = 该渠道禁用
    notify_feishu_webhook: str = ""
    #: 飞书机器人「自定义关键词」；非空时必须出现在卡片标题（默认命中用户群机器人）
    notify_feishu_keyword: str = "UI自动化平台"
    #: 推送门控：none / failure（FAILED+ERROR）/ all；CANCELLED 在 failure 模式不发
    notify_on: str = "failure"
    #: 单次推送超时（秒）
    notify_timeout_s: float = 5.0

    # ── M3.6：对外可访问的平台基址（通知里拼报告链接；空 = 不带链接）──
    public_base_url: str = ""

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
