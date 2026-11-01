"""GAP-25：MySQL schema 行为集成测试（M3.6 D38）。

门控：环境变量 ``UIP_TEST_MYSQL_URL`` 存在才跑（如
``mysql://root:pwd@127.0.0.1:3306/mysql``）；无库整文件 skip（本机预期 1 skipped）。
驱动用 pymysql（同步）延迟导入；DDL 直接执行 ``sql/schema.sql`` 全量
（MySQL 方言事实源直接受测），建独立测试库用完 DROP。
"""
from __future__ import annotations

import os
import pathlib
import time
from urllib.parse import urlsplit

import pytest

if not os.environ.get("UIP_TEST_MYSQL_URL"):
    pytest.skip("未配置 UIP_TEST_MYSQL_URL，跳过 MySQL 集成测试",
                allow_module_level=True)

SCHEMA_SQL = pathlib.Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


@pytest.fixture(scope="module")
def mysql():
    """建独立测试库（uip_itest_{时间戳}）→ 执行 schema.sql → 用完 DROP。"""
    try:
        import pymysql
    except ImportError:
        pytest.skip("pymysql 未安装（pip install pymysql 后重试）")
        return

    url = os.environ["UIP_TEST_MYSQL_URL"]
    parts = urlsplit(url)
    admin = pymysql.connect(
        host=parts.hostname or "127.0.0.1", port=parts.port or 3306,
        user=parts.username or "root", password=parts.password or "",
        charset="utf8mb4", autocommit=True)

    dbname = f"uip_itest_{int(time.time() * 1000)}"
    conn = None
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE DATABASE `{dbname}` DEFAULT CHARSET utf8mb4")
        conn = pymysql.connect(
            host=parts.hostname or "127.0.0.1", port=parts.port or 3306,
            user=parts.username or "root", password=parts.password or "",
            database=dbname, charset="utf8mb4", autocommit=True)
        # 执行全量 DDL：按分号切分语句（schema.sql 无存储过程/触发器，安全）
        sql_text = SCHEMA_SQL.read_text(encoding="utf-8")
        statements = [s.strip() for s in sql_text.split(";") if s.strip()]
        with conn.cursor() as cur:
            for stmt in statements:
                cleaned = "\n".join(
                    line for line in stmt.splitlines()
                    if not line.strip().startswith("--")).strip()
                if cleaned:
                    cur.execute(cleaned)
        yield conn
    finally:
        if conn is not None:
            conn.close()
        try:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS `{dbname}`")
        finally:
            admin.close()


def _insert_project(conn, name: str, code: str, platform: str = "WEB") -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO project (name, code, platform, engine_key) "
            "VALUES (%s, %s, %s, %s)", (name, code, platform, "playwright"))
        cur.execute("SELECT LAST_INSERT_ID()")
        return int(cur.fetchone()[0])


def test_enum_rejects_invalid_value(mysql):
    """ENUM 拒非法值 → DataError（SQLite 上永远测不到的行为，GAP-25 核心）。"""
    import pymysql

    with pytest.raises(pymysql.err.DataError):
        with mysql.cursor() as cur:
            cur.execute(
                "INSERT INTO project (name, code, platform, engine_key) "
                "VALUES (%s, %s, %s, %s)", ("坏端类型", "bad-enum", "X", "playwright"))


def test_bigint_autoincrement_pk(mysql):
    """BigInteger 主键自增：连插 2 行 → id 严格递增且为 int。"""
    first = _insert_project(mysql, "自增一", f"it-a-{time.time_ns()}")
    second = _insert_project(mysql, "自增二", f"it-b-{time.time_ns()}")
    assert isinstance(first, int) and isinstance(second, int)
    assert second > first


def test_element_softdelete_unique_key(mysql):
    """软删唯一键 deleted_seq 修正模式在真实 MySQL 上成立。"""
    import pymysql

    project_id = _insert_project(mysql, "软删项目", f"it-sd-{time.time_ns()}")

    def insert_element(name: str) -> int:
        with mysql.cursor() as cur:
            cur.execute(
                "INSERT INTO element (project_id, parent_id, element_name, node_type) "
                "VALUES (%s, 0, %s, 'ELEMENT')", (project_id, name))
            cur.execute("SELECT LAST_INSERT_ID()")
            return int(cur.fetchone()[0])

    first = insert_element("登录按钮")
    # ① 活记录同名第 2 条 → 唯一键冲突
    with pytest.raises(pymysql.err.IntegrityError):
        insert_element("登录按钮")
    # ② 软删（deleted_seq=id）后重插同名 → 成功
    with mysql.cursor() as cur:
        cur.execute(
            "UPDATE element SET is_deleted = 1, deleted_at = NOW(), deleted_seq = id "
            "WHERE id = %s", (first,))
    second = insert_element("登录按钮")
    assert second > first
