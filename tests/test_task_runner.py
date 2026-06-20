import pytest
import asyncio
import uuid
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from api.main import app
from db.database import AsyncSessionLocal
from db.crud import get_task, create_task
from api.task_runner import run_agent_task, schedule_agent_task

@pytest.mark.asyncio
async def test_task_runner_success_flow(db):
    # Create a task in "queued" status
    task = await create_task(db, "Test Success Task Runner", "http://example.com")
    await db.commit()
    
    mock_run_agent = AsyncMock(return_value={
        "success": True,
        "result": "Agent successfully processed the page",
        "error": "",
        "steps": [{"step_index": 1, "action": "navigate"}],
        "step_count": 1
    })
    
    with patch("api.task_runner.run_agent", mock_run_agent):
        # Run the agent task
        await run_agent_task(task.id, task.prompt, task.start_url)
        
        # Verify the database state
        # Create a new session to get the latest DB updates
        async with AsyncSessionLocal() as session:
            updated_task = await get_task(session, task.id)
            assert updated_task.status == "done"
            assert updated_task.result_json == {"result": "Agent successfully processed the page"}
            assert updated_task.steps_json == [{"step_index": 1, "action": "navigate"}]
            assert updated_task.error is None

@pytest.mark.asyncio
async def test_task_runner_failure_flow(db):
    task = await create_task(db, "Test Failure Task Runner", "http://example.com")
    await db.commit()
    
    mock_run_agent = AsyncMock(return_value={
        "success": False,
        "result": "",
        "error": "Failed to locate form elements",
        "steps": [{"step_index": 1, "action": "fail"}],
        "step_count": 1
    })
    
    with patch("api.task_runner.run_agent", mock_run_agent):
        await run_agent_task(task.id, task.prompt, task.start_url)
        
        async with AsyncSessionLocal() as session:
            updated_task = await get_task(session, task.id)
            assert updated_task.status == "failed"
            assert updated_task.error == "Failed to locate form elements"

@pytest.mark.asyncio
async def test_task_runner_exception_flow(db):
    task = await create_task(db, "Test Exception Task Runner", "http://example.com")
    await db.commit()
    
    mock_run_agent = AsyncMock(side_effect=Exception("Playwright connection lost"))
    
    with patch("api.task_runner.run_agent", mock_run_agent):
        await run_agent_task(task.id, task.prompt, task.start_url)
        
        async with AsyncSessionLocal() as session:
            updated_task = await get_task(session, task.id)
            assert updated_task.status == "failed"
            assert "Playwright connection lost" in updated_task.error

@pytest.mark.asyncio
async def test_schedule_agent_task(db):
    task = await create_task(db, "Test Schedule Runner", "http://example.com")
    await db.commit()
    
    mock_run_agent_task = AsyncMock()
    
    with patch("api.task_runner.run_agent_task", mock_run_agent_task):
        async_task = schedule_agent_task(task.id, task.prompt, task.start_url)
        assert isinstance(async_task, asyncio.Task)
        
        # Await the task wrapper to let mock call execute
        await async_task
        mock_run_agent_task.assert_called_once_with(task.id, task.prompt, task.start_url)

@pytest.mark.asyncio
async def test_api_post_schedules_background_task(db):
    mock_run_agent = AsyncMock(return_value={
        "success": True,
        "result": "Completed",
        "error": "",
        "steps": [],
        "step_count": 0
    })
    
    with patch("api.task_runner.run_agent", mock_run_agent):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # Send POST /tasks request
            response = await ac.post("/tasks", json={
                "prompt": "Run background task test",
                "start_url": "http://example.com"
            })
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "queued"
            task_id = data["id"]
            
            # Wait for background task to complete
            # Using sleep to allow asyncio scheduler to run the background task
            for _ in range(20):
                await asyncio.sleep(0.1)
                async with AsyncSessionLocal() as session:
                    t = await get_task(session, task_id)
                    if t and t.status in ("done", "failed"):
                        break
            
            # Verify database was updated by the background task
            async with AsyncSessionLocal() as session:
                t = await get_task(session, task_id)
                assert t.status == "done"
