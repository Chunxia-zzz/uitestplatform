"""M3.5 端到端验收：URL 扫描 → 候选 → 确认导入 → 元素库落库。

用法：先起后端(8000) + fixture(8899)，然后
    python scripts/smoke_m35.py

判定标准见 docs/UI自动化平台M3.5详细设计.md §5.2（V1–V6）。
"""
from __future__ import annotations

import sys
import time

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
FIXTURE = "http://127.0.0.1:8899"

PROJECT_CODE = f"scan-demo-{int(time.time())}"

passed = 0
failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    if ok:
        passed += 1
        print(f"  [OK]   {name}" + (f"  ({detail})" if detail else ""))
    else:
        failed.append(name)
        print(f"  [FAIL] {name}" + (f"  ({detail})" if detail else ""))


def main() -> int:
    client = httpx.Client(timeout=120)

    # 建一个干净的扫描项目（不需要 target —— 扫描直接传 url）
    project = client.post(f"{BASE}/projects", json={
        "name": "扫描演示项目", "code": PROJECT_CODE,
        "platform": "WEB", "engine_key": "playwright"}).json()
    project_id = project["id"]

    before = client.get(f"{BASE}/projects/{project_id}/elements").json()["total"]
    print(f"\n扫描前元素数：{before}")

    # ───────────── V1 扫描（不落库）─────────────
    print("\nV1 扫描 todo.html")
    resp = client.post(f"{BASE}/projects/{project_id}/element-scan",
                       json={"url": f"{FIXTURE}/todo.html"})
    check("扫描返回 200", resp.status_code == 200, f"status={resp.status_code}")
    if resp.status_code != 200:
        print(resp.text[:800])
        return 1
    data = resp.json()

    check("有候选元素", data["stats"]["total"] > 0, f"total={data['stats']['total']}")
    check("候选带定位符", all(c["locators"] for c in data["candidates"]))
    check("候选带稳定性分级", all(c["strength"] in ("strong", "medium", "weak")
                                for c in data["candidates"]))

    add_btn = next((c for c in data["candidates"]
                    if c["name"] == "添加" and c["tag"] == "button"), None)
    check("「添加」按钮被识别且主定位为 testid=add",
          add_btn is not None
          and add_btn["locators"][0]["locator_type"] == "testid"
          and add_btn["locators"][0]["locator_value"] == "add",
          add_btn and add_btn["locators"][0] or "")

    # 扫描不落库
    after_scan = client.get(f"{BASE}/projects/{project_id}/elements").json()["total"]
    check("扫描后元素数不变（不落库）", after_scan == before,
          f"{before} → {after_scan}")

    # ───────────── V2 分级统计 ─────────────
    print("\nV2 稳定性分级")
    check("strong + medium + weak == total",
          data["stats"]["strong"] + data["stats"]["medium"] + data["stats"]["weak"]
          == data["stats"]["total"],
          str(data["stats"]))

    # ───────────── V3 只导入强/中，弱等级不导 ─────────────
    print("\nV3 导入确认的候选（只勾强/中）")
    chosen = [c for c in data["candidates"] if c["strength"] in ("strong", "medium")]
    import_body = {
        "candidates": [
            {"name": c["name"],
             "locators": [c["locators"][0]]}      # 只导主定位符
            for c in chosen
        ]
    }
    imp = client.post(f"{BASE}/projects/{project_id}/element-scan/import",
                      json=import_body)
    check("导入返回 200", imp.status_code == 200, f"status={imp.status_code}")
    imp_data = imp.json()
    check("导入数量 == 勾选数量", len(imp_data["created"]) == len(chosen),
          f"{len(imp_data['created'])} / {len(chosen)}")
    check("无失败项", imp_data["failed"] == [], str(imp_data["failed"]))

    # ───────────── V4 落库验证 ─────────────
    print("\nV4 元素库落库")
    after_import = client.get(f"{BASE}/projects/{project_id}/elements").json()
    check("元素数 == before + 导入数", after_import["total"] == before + len(chosen),
          f"{after_import['total']}")
    # 抽一个验证定位符
    first_created = imp_data["created"][0]
    locators = client.get(f"{BASE}/elements/{first_created['element_id']}/locators").json()
    loc_count = sum(len(g["items"]) for g in locators["groups"])
    check("导入的元素有定位符", loc_count == 1, f"locators={loc_count}")

    # ───────────── V5 幂等 / 冲突 ─────────────
    print("\nV5 重复导入同名元素 → 冲突")
    dup = client.post(f"{BASE}/projects/{project_id}/element-scan/import",
                      json={"candidates": [
                          {"name": chosen[0]["name"],
                           "locators": [{"locator_type": "testid", "locator_value": "x"}]}]})
    dup_data = dup.json()
    check("同名导入进 failed", dup_data["created"] == []
          and dup_data["failed"]
          and dup_data["failed"][0]["code"] == "ELEMENT_NAME_DUPLICATED",
          str(dup_data["failed"][:1]))

    # ───────────── V6 无目标 → 422 ─────────────
    print("\nV6 无目标项目扫描")
    no_target = client.post(f"{BASE}/projects", json={
        "name": "无目标项目", "code": f"{PROJECT_CODE}-no-target",
        "platform": "WEB", "engine_key": "playwright"}).json()
    empty = client.post(f"{BASE}/projects/{no_target['id']}/element-scan", json={})
    check("无 url 无 target → 422 SCAN_TARGET_REQUIRED",
          empty.status_code == 422
          and empty.json().get("error", {}).get("code") == "SCAN_TARGET_REQUIRED",
          f"status={empty.status_code}")

    # 也扫一下 login 页，验证多页面稳定性
    print("\nV6.5 扫描 login.html")
    login_scan = client.post(f"{BASE}/projects/{project_id}/element-scan",
                             json={"url": f"{FIXTURE}/login.html"}).json()
    check("login 页也扫到元素", login_scan["stats"]["total"] > 0,
          f"total={login_scan['stats']['total']}")

    # 清理
    print("\n清理")
    client.delete(f"{BASE}/projects/{no_target['id']}")
    client.delete(f"{BASE}/projects/{project_id}")

    print("\n" + "=" * 62)
    total = passed + len(failed)
    print(f"结果：{passed}/{total} 通过")
    for name in failed:
        print("  -", name)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
