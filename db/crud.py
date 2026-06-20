import uuid
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models import Task

logger = logging.getLogger("db.crud")

async def create_task(db: AsyncSession, prompt: str, start_url: str) -> Task:
    task = Task(
        prompt=prompt,
        start_url=start_url,
        status="queued"
    )
    db.add(task)
    await db.flush()
    return task

async def get_task(db: AsyncSession, task_id: uuid.UUID) -> Task | None:
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalars().first()
    if not task:
        logger.warning(f"Task with ID {task_id} not found.")
        return None
    return task

async def list_tasks(db: AsyncSession, limit: int = 20) -> list[Task]:
    result = await db.execute(
        select(Task).order_by(Task.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())

async def update_task_status(db: AsyncSession, task_id: uuid.UUID, status: str) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        logger.warning(f"Task with ID {task_id} not found. Cannot update status.")
        return None
    task.status = status
    await db.flush()
    return task

async def update_task_result(
    db: AsyncSession,
    task_id: uuid.UUID,
    result_json: dict | None,
    steps_json: list | None,
    step_count: int,
    status: str
) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        logger.warning(f"Task with ID {task_id} not found. Cannot update result.")
        return None
    task.result_json = result_json
    task.steps_json = steps_json
    task.status = status
    await db.flush()
    return task

async def update_task_error(db: AsyncSession, task_id: uuid.UUID, error: str | None) -> Task | None:
    task = await get_task(db, task_id)
    if not task:
        logger.warning(f"Task with ID {task_id} not found. Cannot update error.")
        return None
    task.error = error
    task.status = "failed"
    await db.flush()
    return task

async def append_step(db: AsyncSession, task_id: uuid.UUID, step: dict) -> None:
    task = await get_task(db, task_id)
    if not task:
        logger.warning(f"Task with ID {task_id} not found. Cannot append step.")
        return None
    steps = task.steps_json or []
    new_steps = list(steps)
    new_steps.append(step)
    task.steps_json = new_steps
    await db.flush()
