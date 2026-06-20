import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from api.main import app
from db.crud import append_step

@pytest.mark.asyncio
async def test_tasks_api_flow(db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Test invalid prompt (short prompt, < 5 chars)
        response = await ac.post("/tasks", json={
            "prompt": "abc",
            "start_url": "http://example.com"
        })
        assert response.status_code == 422

        # 2. Test invalid start_url (not starting with http)
        response = await ac.post("/tasks", json={
            "prompt": "Valid Prompt Longer Than 5",
            "start_url": "ftp://example.com"
        })
        assert response.status_code == 422

        # 3. Test valid task creation
        response = await ac.post("/tasks", json={
            "prompt": "Verify Valid Task Creation",
            "start_url": "http://example.com"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["prompt"] == "Verify Valid Task Creation"
        assert data["start_url"] == "http://example.com"
        assert data["status"] == "queued"
        assert "id" in data
        assert data["step_count"] == 0

        task_id = data["id"]

        # 4. Test GET /tasks/{task_id}
        response = await ac.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        get_data = response.json()
        assert get_data["id"] == task_id
        assert get_data["prompt"] == "Verify Valid Task Creation"

        # 5. Test GET /tasks/{task_id} with non-existent UUID
        invalid_uuid = str(uuid.uuid4())
        response = await ac.get(f"/tasks/{invalid_uuid}")
        assert response.status_code == 404

        # 6. Test GET /tasks/{task_id}/steps
        response = await ac.get(f"/tasks/{task_id}/steps")
        assert response.status_code == 200
        steps_data = response.json()
        assert steps_data["task_id"] == task_id
        assert steps_data["steps"] == []

        # Add steps of different formats (dict and string JSON) to verify step formatting
        await append_step(db, uuid.UUID(task_id), {"action": "click", "params": {"x": 10}})
        await append_step(db, uuid.UUID(task_id), '{"action": "navigate", "params": {"url": "http://test"}, "reasoning": "Go to URL", "result": "Loaded"}')
        await db.commit()

        # Call GET /tasks/{task_id}/steps again to verify format
        response = await ac.get(f"/tasks/{task_id}/steps")
        assert response.status_code == 200
        steps_data = response.json()
        assert steps_data["task_id"] == task_id
        assert len(steps_data["steps"]) == 2
        
        # Verify first step formatting (keys: action, params, reasoning, result)
        assert steps_data["steps"][0] == {
            "action": "click",
            "params": {"x": 10},
            "reasoning": None,
            "result": None
        }
        
        # Verify second step formatting
        assert steps_data["steps"][1] == {
            "action": "navigate",
            "params": {"url": "http://test"},
            "reasoning": "Go to URL",
            "result": "Loaded"
        }

        # 7. Test GET /tasks/{task_id}/steps with non-existent UUID
        response = await ac.get(f"/tasks/{invalid_uuid}/steps")
        assert response.status_code == 404

        # 8. Test GET /tasks (list endpoint)
        response = await ac.get("/tasks")
        assert response.status_code == 200
        list_data = response.json()
        assert isinstance(list_data, list)
        assert len(list_data) > 0
        
        ids = [t["id"] for t in list_data]
        assert task_id in ids
