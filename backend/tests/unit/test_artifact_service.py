"""产物访问（M3.2 / GAP-34）：归属校验与目录越界必须被拒。"""
from __future__ import annotations

import os

import pytest

from app.core.config import settings
from app.core.errors import ArtifactNotFound, ArtifactPathForbidden
from app.models import Artifact
from app.services import artifact_service


@pytest.fixture
def artifacts_dir(tmp_path, monkeypatch):
    target = tmp_path / "artifacts"
    target.mkdir()
    monkeypatch.setattr(settings, "artifacts_dir", str(target))
    return target


async def _artifact(db, path: str, execution_id: int = 1) -> Artifact:
    row = Artifact(execution_id=execution_id, step_result_id=1,
                   kind="SCREENSHOT", storage="LOCAL", path=path, size_bytes=3)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_resolve_path_inside_dir(db, artifacts_dir):
    file = artifacts_dir / "shot.png"
    file.write_bytes(b"png")
    row = await _artifact(db, str(file))
    assert artifact_service.resolve_path(row) == os.path.realpath(file)


@pytest.mark.asyncio
async def test_resolve_path_rejects_outside_dir(db, artifacts_dir, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    row = await _artifact(db, str(outside))
    with pytest.raises(ArtifactPathForbidden):
        artifact_service.resolve_path(row)


@pytest.mark.asyncio
async def test_resolve_path_rejects_traversal(db, artifacts_dir):
    """``..`` 穿越必须被 realpath 归一化后挡住。"""
    row = await _artifact(db, str(artifacts_dir / ".." / "etc" / "passwd"))
    with pytest.raises(ArtifactPathForbidden):
        artifact_service.resolve_path(row)


@pytest.mark.asyncio
async def test_missing_file_reports_not_found(db, artifacts_dir):
    row = await _artifact(db, str(artifacts_dir / "gone.png"))
    with pytest.raises(ArtifactNotFound):
        artifact_service.resolve_path(row)


@pytest.mark.asyncio
async def test_get_or_404_checks_ownership(db, artifacts_dir):
    file = artifacts_dir / "shot.png"
    file.write_bytes(b"png")
    row = await _artifact(db, str(file), execution_id=1)

    found = await artifact_service.get_or_404(db, 1, row.id)
    assert found.id == row.id

    # 换个 execution_id 就查不到 —— 否则知道 artifact id 就能读别人产物
    with pytest.raises(ArtifactNotFound):
        await artifact_service.get_or_404(db, 2, row.id)


@pytest.mark.asyncio
async def test_list_for_execution_filters(db, artifacts_dir):
    file = artifacts_dir / "a.png"
    file.write_bytes(b"png")
    await _artifact(db, str(file), execution_id=1)
    await _artifact(db, str(file), execution_id=2)

    rows = await artifact_service.list_for_execution(db, 1)
    assert len(rows) == 1
    assert rows[0].execution_id == 1


@pytest.mark.asyncio
async def test_to_dict_contains_download_url(db, artifacts_dir):
    file = artifacts_dir / "a.png"
    file.write_bytes(b"png")
    row = await _artifact(db, str(file), execution_id=7)
    payload = artifact_service.to_dict(row, 7)
    assert payload["url"] == f"/api/v1/executions/7/artifacts/{row.id}"
    assert "path" not in payload          # 不把服务器路径暴露给前端
