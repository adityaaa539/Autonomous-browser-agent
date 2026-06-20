import pytest
import uuid
from db.crud import (
    create_task,
    get_task,
    list_tasks,
    update_task_status,
    update_task_result,
    update_task_error,
    append_step
)

@pytest.mark.asyncio
async def test_crud_flow(db):
    # 1. Create task
    task = await create_task(db, "Test prompt", "http://example.com")
    assert task.id is not None
    assert task.prompt == "Test prompt"
    assert task.start_url == "http://example.com"
    assert task.status == "queued"
    
    task_id = task.id
    
    # 2. Get task
    fetched = await get_task(db, task_id)
    assert fetched is not None
    assert fetched.id == task_id
    
    # 3. List tasks
    tasks = await list_tasks(db, limit=5)
    assert len(tasks) > 0
    assert task_id in [t.id for t in tasks]
    
    # 4. Update task status
    updated = await update_task_status(db, task_id, "running")
    assert updated is not None
    assert updated.status == "running"
    
    # 5. Append step
    step = {"step_index": 1, "action": "click"}
    await append_step(db, task_id, step)
    
    fetched = await get_task(db, task_id)
    assert fetched.steps_json == [step]
    
    # 6. Update task result
    updated = await update_task_result(db, task_id, {"final_data": "success"}, [{"step_index": 1, "action": "click"}], 1, "done")
    assert updated is not None
    assert updated.status == "done"
    assert updated.result_json == {"final_data": "success"}
    
    # 7. Update task error
    updated = await update_task_error(db, task_id, "Test error message")
    assert updated is not None
    assert updated.status == "failed"
    assert updated.error == "Test error message"
    
    # 8. Test missing task handling (should return None, log warning, not throw error)
    missing_id = uuid.uuid4()
    
    assert await get_task(db, missing_id) is None
    assert await update_task_status(db, missing_id, "running") is None
    assert await update_task_result(db, missing_id, {}, [], 0, "done") is None
    assert await update_task_error(db, missing_id, "error") is None
    assert await append_step(db, missing_id, {}) is None
    
    await db.commit()
