"""演示数据：一个可立刻跑通的 Web 项目（配合 fixtures/web/login.html）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExecutionTarget, Project, TestCase, TestStep
from app.services import element_service, locator_service

DEMO_CODE = "demo-web"
FIXTURE_BASE = "http://127.0.0.1:8899"


async def seed_demo(db: AsyncSession) -> dict:
    exists = (await db.execute(select(Project).where(Project.code == DEMO_CODE))
              ).scalar_one_or_none()
    if exists:
        return {"status": "exists", "project_id": exists.id}

    target = ExecutionTarget(
        project_id=0, name="本地 fixture (8899)", platform="WEB", engine_key="playwright",
        base_url=FIXTURE_BASE, options={"viewport": {"width": 1280, "height": 800}},
        enabled=True,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    project = Project(name="Demo Web 中台", code=DEMO_CODE, platform="WEB",
                      engine_key="playwright", target_id=target.id,
                      description="配合 backend/fixtures/web 的演示项目")
    db.add(project)
    await db.commit()
    await db.refresh(project)
    target.project_id = project.id
    await db.commit()

    folder = await element_service.create(
        db, project_id=project.id, parent_id=0, element_name="登录模块",
        node_type="FOLDER", memo="登录流程相关的元素")
    page_dir = await element_service.create(
        db, project_id=project.id, parent_id=folder.id, element_name="登录页",
        node_type="FOLDER")

    username = await element_service.create(
        db, project_id=project.id, parent_id=page_dir.id, element_name="用户名输入框",
        memo="testid=username")
    password = await element_service.create(
        db, project_id=project.id, parent_id=page_dir.id, element_name="密码输入框",
        memo="testid=password")
    submit = await element_service.create(
        db, project_id=project.id, parent_id=page_dir.id, element_name="登录按钮",
        memo="提交用户名密码；成功后显示欢迎语")
    welcome = await element_service.create(
        db, project_id=project.id, parent_id=page_dir.id, element_name="欢迎语",
        memo="登录成功后出现")

    await locator_service.create(db, element_id=username.id, platform="WEB",
                                 engine_key="playwright", locator_type="testid",
                                 locator_value="username")
    await locator_service.create(db, element_id=password.id, platform="WEB",
                                 engine_key="playwright", locator_type="testid",
                                 locator_value="password")
    # 首条故意写错，用来现场演示回退链（V3）：执行时 fallback_index 应为 1
    await locator_service.create(db, element_id=submit.id, platform="WEB",
                                 engine_key="playwright", locator_type="testid",
                                 locator_value="submit-not-exist", priority=10)
    await locator_service.create(db, element_id=submit.id, platform="WEB",
                                 engine_key="playwright", locator_type="css",
                                 locator_value="#submit", priority=20)
    await locator_service.create(db, element_id=welcome.id, platform="WEB",
                                 engine_key="playwright", locator_type="testid",
                                 locator_value="welcome")

    case = TestCase(project_id=project.id, title="登录成功（含定位符回退）",
                    description="第 4 步 click 应回退到第 2 条定位符")
    db.add(case)
    await db.commit()
    await db.refresh(case)

    steps = [
        (1, "navigate", None, {"url": "/login.html"}),
        (2, "input", username.id, {"text": "jerry"}),
        (3, "input", password.id, {"text": "s3cret"}),
        (4, "click", submit.id, {}),
        (5, "wait_element", welcome.id, {"state": "visible"}),
        (6, "get_text", welcome.id, {"output_var": "welcome_text"}),
        (7, "assert_contains", None, {"actual": "${welcome_text}", "expected": "欢迎"}),
    ]
    for seq, action_key, element_id, params in steps:
        db.add(TestStep(case_id=case.id, seq=seq, action_key=action_key,
                        element_id=element_id, params=params))
    await db.commit()

    # M3.3：用例集（执行单元）—— 默认只手动运行
    from app.services import suite_service
    suite = await suite_service.create(
        db, project_id=project.id, name="冒烟回归",
        description="登录主链路；演示用，默认手动运行")
    await suite_service.add_cases(db, suite.id, [case.id])

    return {
        "status": "created", "project_id": project.id, "target_id": target.id,
        "case_id": case.id, "suite_id": suite.id,
        "elements": 6, "locators": 5, "steps": len(steps),
    }
