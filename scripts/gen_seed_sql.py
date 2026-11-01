"""按 Python 字典生成 action_catalog 种子 SQL（保证与代码同源，不会手抄漂移）。

用法：
    python scripts/gen_seed_sql.py
输出：
    backend/sql/seed_action_catalog.sql
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.domain.action_keys import ACTION_CATALOG, sort_of  # noqa: E402

HEADER = """-- ============================================================
--  action_catalog 种子数据（51 条，由 scripts/gen_seed_sql.py 生成）
--  单一事实来源：backend/app/domain/action_keys.py
--  勿手工编辑本文件 —— 改代码后重新生成
--  用法：mysql -u root -p uitest < seed_action_catalog.sql
-- ============================================================
SET NAMES utf8mb4;

DELETE FROM `action_catalog`;
"""


def sql_str(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def main() -> int:
    lines = [HEADER]
    for spec in ACTION_CATALOG:
        schema = json.dumps(spec.params_schema, ensure_ascii=False)
        lines.append(
            "INSERT INTO `action_catalog` "
            "(`action_key`,`name`,`category`,`platforms`,`engines`,`params_schema`,"
            "`requires_element`,`sort`,`enabled`) VALUES ("
            f"{sql_str(spec.key)}, {sql_str(spec.name)}, '{spec.category}', "
            f"{sql_str(json.dumps(list(spec.platforms), ensure_ascii=False))}, "
            f"{sql_str(json.dumps(list(spec.engines), ensure_ascii=False))}, "
            f"{sql_str(schema)}, "
            f"{1 if spec.requires_element else 0}, {sort_of(spec.key)}, 1);\n"
        )
    lines.append("\n-- 校验：应为 51\n")
    lines.append("-- SELECT COUNT(*) FROM `action_catalog`;\n")
    lines.append("-- SELECT COUNT(*) FROM `action_catalog` WHERE JSON_LENGTH(`engines`) = 0;  -- 9\n")

    target = ROOT / "backend" / "sql" / "seed_action_catalog.sql"
    target.write_text("".join(lines), encoding="utf-8")
    print(f"generated {target} ({len(ACTION_CATALOG)} actions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
