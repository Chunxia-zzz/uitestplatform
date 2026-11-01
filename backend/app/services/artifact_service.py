"""产物访问（M3.2 GAP-34）。

两个职责：
1. 按执行列出产物（报告 / 页面要能看到"这次跑了哪些截图"）；
2. 按 id 取文件 —— **必须做两层校验**：
   * 归属：``artifact.execution_id`` 必须等于 URL 里的 execution_id（否则换个 id 就能读别人产物）；
   * 目录：``realpath(path)`` 必须落在 ``settings.artifacts_dir`` 内（防目录穿越与配置漂移）。

只做"读"，不提供删除：产物是执行证据，清理属于运维动作，不做进 API。
"""
from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ArtifactNotFound, ArtifactPathForbidden
from app.models import Artifact


def _allowed_root() -> str:
    return os.path.realpath(settings.artifacts_dir)


def resolve_path(artifact: Artifact) -> str:
    """把 DB 里的路径解析成可读绝对路径，并校验它在允许目录内。"""
    target = os.path.realpath(artifact.path)
    root = _allowed_root()
    if target != root and not target.startswith(root + os.sep):
        raise ArtifactPathForbidden(
            "产物路径不在 artifacts 目录内，拒绝访问",
            {"artifact_id": artifact.id},
        )
    if not os.path.isfile(target):
        raise ArtifactNotFound("产物文件已不存在（可能被清理）",
                               {"artifact_id": artifact.id})
    return target


async def list_for_execution(db: AsyncSession, execution_id: int) -> list[Artifact]:
    return list((await db.execute(
        select(Artifact).where(Artifact.execution_id == execution_id)
        .order_by(Artifact.id))).scalars().all())


async def get_or_404(db: AsyncSession, execution_id: int,
                     artifact_id: int) -> Artifact:
    artifact = (await db.execute(
        select(Artifact).where(Artifact.id == artifact_id,
                               Artifact.execution_id == execution_id))).scalar_one_or_none()
    if artifact is None:
        raise ArtifactNotFound(f"产物 {artifact_id} 不存在或不属于执行 {execution_id}",
                               {"artifact_id": artifact_id, "execution_id": execution_id})
    return artifact


def to_dict(artifact: Artifact, execution_id: int) -> dict:
    return {
        "id": artifact.id,
        "execution_id": artifact.execution_id,
        "step_result_id": artifact.step_result_id,
        "kind": artifact.kind,
        "storage": artifact.storage,
        "size_bytes": artifact.size_bytes,
        "created_at": artifact.created_at.isoformat(timespec="seconds")
        if artifact.created_at else None,
        "url": f"/api/v1/executions/{execution_id}/artifacts/{artifact.id}",
    }
