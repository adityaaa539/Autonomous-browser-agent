import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Task
from api.schemas import TaskCreate, TaskResponse

router = APIRouter()

@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(task_in: TaskCreate, db: AsyncSession = Depends(get_db)):
    task = Task(
        prompt=task_in.prompt,
        start_url=task_in.start_url,
        status="queued"
    )
    db.add(task)
    await db.flush()
    return task

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@router.get("/{task_id}/steps")
async def get_task_steps(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Task.steps_json).where(Task.id == task_id))
    steps_json = result.scalar_one_or_none()
    
    # Check if task actually exists in the database
    exists_result = await db.execute(select(Task.id).where(Task.id == task_id))
    if not exists_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")
        
    return {"task_id": task_id, "steps": steps_json or []}
