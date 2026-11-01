"""命令行工具：体检 / 自检 / 演示数据。

    python -m app.cli doctor                    # 字典与注册表一致性
    python -m app.cli audit --project 1 --platform WEB
    python -m app.cli schema list
    python -m app.cli seed-demo                 # 建 demo 项目 + 元素 + 用例
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.db import SessionLocal, init_db
from app.engines.registry import assert_catalog_consistency, assert_locator_dict_consistency
from app.models import ActionCatalog


async def _doctor() -> int:
    await init_db(seed=True)
    async with SessionLocal() as session:
        rows = (await session.execute(select(ActionCatalog.action_key, ActionCatalog.engines))).all()
    assert_catalog_consistency([(k, list(v or [])) for k, v in rows])
    assert_locator_dict_consistency()
    print(f"OK: action_catalog={len(rows)} actions")
    return 0


async def _audit(project_id: int, platform: str) -> int:
    """对某项目跑一遍定位符体检（M2 附录 / CLI）。"""
    from app.repositories.element_repo import element_repo
    from app.services import locator_service, locator_verify_service

    await init_db(seed=False)
    async with SessionLocal() as session:
        elements = await element_repo.list_by_project(session, project_id)
        rows: list[tuple[str, str, str, str]] = []
        for element in elements:
            if element.node_type != "ELEMENT":
                continue
            payload = await locator_service.group_payload(session, element.id)
            for group in payload["groups"]:
                if group["platform"] != platform:
                    continue
                try:
                    result = await locator_verify_service.verify(
                        session, element.id, platform=platform,
                        engine_key=group["engine_key"], include_saved=True)
                except Exception as exc:                     # noqa: BLE001
                    rows.append((element.element_name, "-", "ERROR", str(exc)[:40]))
                    continue
                for item in result["results"]:
                    rows.append((
                        element.element_name,
                        f'{item["locator_type"]}={item["locator_value"]}'[:44],
                        item["verdict"], f'{item["matched"]} / {item["duration_ms"]}ms'))

    print(f"{'元素':<18}{'定位符':<46}{'状态':<10}{'命中 / 耗时'}")
    print("-" * 90)
    for row in rows:
        print(f"{row[0]:<18}{row[1]:<46}{row[2]:<10}{row[3]}")
    return 0


async def _seed_demo() -> int:
    from app.services.demo_seed import seed_demo
    await init_db(seed=True)
    async with SessionLocal() as session:
        summary = await seed_demo(session)
    print(f"OK: {summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="UI 自动化平台命令行")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="校验动作字典 / 定位字典与引擎注册表")

    audit = sub.add_parser("audit", help="批量体检某项目的定位符")
    audit.add_argument("--project", type=int, required=True)
    audit.add_argument("--platform", default="WEB", choices=["WEB", "ANDROID", "IOS"])

    sub.add_parser("seed-demo", help="写入演示项目 / 元素 / 定位符 / 用例")

    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return asyncio.run(_doctor())
    if args.cmd == "audit":
        return asyncio.run(_audit(args.project, args.platform))
    if args.cmd == "seed-demo":
        return asyncio.run(_seed_demo())
    return 1


if __name__ == "__main__":
    sys.exit(main())
