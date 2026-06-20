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


@pytest.mark.asyncio
async def test_run_agent_streaming_db_updates(db):
    import json
    from unittest.mock import AsyncMock, patch
    from agent.runner import run_agent
    from db.crud import create_task, get_task
    from db.database import AsyncSessionLocal
    
    # 1. Create a task in the database
    task_row = await create_task(db, "Test Streaming DB Updates", "http://localhost:8899/test_page.html")
    await db.commit()
    
    # 2. Mock AsyncOpenAI chat completions inside agent.graph to perform a 2-step flow
    mock_response_1 = AsyncMock()
    mock_response_1.choices = [
        AsyncMock(message=AsyncMock(content=json.dumps({
            "action": "fill",
            "params": {"selector": "#name", "text": "StreamUser"},
            "reasoning": "First step reasoning",
            "result": "Success"
        })))
    ]
    
    mock_response_2 = AsyncMock()
    mock_response_2.choices = [
        AsyncMock(message=AsyncMock(content=json.dumps({
            "action": "done",
            "params": {"result": "Done string"},
            "reasoning": "Second step reasoning",
            "result": "Finished"
        })))
    ]
    
    # Patch AsyncOpenAI inside agent.graph
    with patch("agent.graph.AsyncOpenAI") as mock_openai_class:
        mock_client = AsyncMock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            mock_response_1,
            mock_response_2
        ])
        
        res = await run_agent(task_row.prompt, task_row.start_url, task_id=task_row.id, db=db)
        
        assert res["success"] is True
        
        async with AsyncSessionLocal() as session:
            updated_task = await get_task(session, task_row.id)
            assert updated_task is not None
            assert updated_task.steps_json is not None
            assert len(updated_task.steps_json) >= 2
            
            step1 = updated_task.steps_json[0]
            if isinstance(step1, str):
                step1 = json.loads(step1)
            assert step1["action"] == "fill"
            assert step1["params"]["selector"] == "#name"

