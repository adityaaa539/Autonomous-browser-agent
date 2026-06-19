import os
import pytest
import base64
from agent.browser import (
    BrowserManager,
    BrowserError,
    ElementNotFoundError,
    NavigationTimeoutError,
)

# Force headless mode for pytest runs
os.environ["HEADLESS"] = "true"

TEST_URL = "http://localhost:8899/test_page.html"

@pytest.mark.asyncio
async def test_navigate():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        assert TEST_URL in bm.page.url

@pytest.mark.asyncio
async def test_get_page_text():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        text = await bm.get_page_text()
        assert "Test Page for Browser Agent" in text
        assert "Alice Smith" in text
        assert "Submit Form" in text

@pytest.mark.asyncio
async def test_fill_and_click():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        
        # Fill input fields
        await bm.fill("#name", "Antigravity")
        await bm.fill("#email", "antigravity@ai.com")
        await bm.page.select_option("#role", "Developer")
        
        # Click the submit button
        await bm.click("#submit-btn")
        
        # Verify javascript form submission message is visible
        result_text = await bm.page.inner_text("#result")
        assert "Form submitted! Name: Antigravity" in result_text

@pytest.mark.asyncio
async def test_get_interactive_elements():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        elements = await bm.get_interactive_elements()
        
        tags = [el["tag"] for el in elements]
        
        assert "input" in tags
        assert "button" in tags
        assert "a" in tags
        assert "select" in tags

@pytest.mark.asyncio
async def test_screenshot():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        screenshot_b64 = await bm.screenshot()
        assert len(screenshot_b64) > 0
        
        # Verify base64 PNG header
        decoded = base64.b64decode(screenshot_b64)
        assert decoded.startswith(b"\x89PNG")

@pytest.mark.asyncio
async def test_element_not_found_raises():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        
        # Expect ElementNotFoundError when click fails
        with pytest.raises(ElementNotFoundError) as exc_info:
            await bm.click("#missing-button", timeout=500)
        assert "missing-button" in str(exc_info.value)
        
        # Expect ElementNotFoundError when fill fails
        with pytest.raises(ElementNotFoundError) as exc_info:
            await bm.fill("#missing-input", "text", timeout=500)
        assert "missing-input" in str(exc_info.value)

@pytest.mark.asyncio
async def test_scroll():
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        
        # Force a scrollable height on the body
        await bm.page.evaluate("document.body.style.height = '2000px'")
        
        # Scroll down
        await bm.scroll("down", 200)
        scroll_y = await bm.page.evaluate("window.scrollY")
        assert scroll_y == 200
        
        # Scroll up
        await bm.scroll("up", 100)
        scroll_y = await bm.page.evaluate("window.scrollY")
        assert scroll_y == 100


@pytest.mark.asyncio
async def test_analyze_page_with_vision():
    from unittest.mock import AsyncMock
    async with BrowserManager() as bm:
        await bm.navigate(TEST_URL)
        
        # Mock OpenAI chat completions create
        mock_response = AsyncMock()
        mock_response.choices = [
            AsyncMock(message=AsyncMock(content="Mocked vision analysis response"))
        ]
        bm.openai_client.chat.completions.create = AsyncMock(return_value=mock_response)
        
        # Run vision analysis
        result = await bm.analyze_page_with_vision("Click the submit button")
        
        # Verify mocked result and interaction
        assert result == "Mocked vision analysis response"
        bm.openai_client.chat.completions.create.assert_called_once()
        
        # Verify parameters passed to OpenAI client
        args, kwargs = bm.openai_client.chat.completions.create.call_args
        assert kwargs["model"] == "nex-agi/nex-n2-pro:free"
        assert kwargs["max_tokens"] == 1000
        messages = kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        
        user_content = messages[1]["content"]
        assert len(user_content) == 2
        assert user_content[0]["type"] == "text"
        assert user_content[1]["type"] == "image_url"


@pytest.mark.asyncio
async def test_graph_execution():
    import json
    from agent.graph import compile_graph
    from unittest.mock import AsyncMock
    
    graph = compile_graph()
    
    async with BrowserManager() as bm:
        # Mock OpenAI planner responses for a 3-step form submission flow
        mock_response_1 = AsyncMock()
        mock_response_1.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({
                "thought": "Let's populate the name and email.",
                "actions": [
                    {"action": "fill", "selector": "#name", "text": "TestUser", "timeout": 1000},
                    {"action": "fill", "selector": "#email", "text": "test@user.com", "timeout": 1000}
                ],
                "is_completed": False
            })))
        ]
        
        mock_response_2 = AsyncMock()
        mock_response_2.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({
                "thought": "Now let's submit the form.",
                "actions": [
                    {"action": "click", "selector": "#submit-btn", "timeout": 1000}
                ],
                "is_completed": False
            })))
        ]
        
        mock_response_3 = AsyncMock()
        mock_response_3.choices = [
            AsyncMock(message=AsyncMock(content=json.dumps({
                "thought": "Task is completed, result is visible.",
                "actions": [],
                "is_completed": True,
                "final_answer": "Form successfully submitted for TestUser"
            })))
        ]
        
        bm.openai_client.chat.completions.create = AsyncMock(side_effect=[
            mock_response_1,
            mock_response_2,
            mock_response_3
        ])
        
        initial_state = {
            "task": "Submit the form with name TestUser and email test@user.com",
            "start_url": TEST_URL,
            "current_url": "",
            "screenshot_b64": "",
            "page_text": "",
            "interactive_elements": [],
            "steps": [],
            "step_count": 0,
            "done": False,
            "success": True,
            "result": "",
            "error": None
        }
        
        config = {"configurable": {"browser_manager": bm}}
        final_state = await graph.ainvoke(initial_state, config=config)
        
        # Verify graph final state
        assert final_state["done"] is True
        assert final_state["success"] is True
        assert final_state["result"] == "Form successfully submitted for TestUser"
        assert final_state["step_count"] == 3
        assert len(final_state["steps"]) == 3
        assert "Executed: Action 'fill'" in final_state["steps"][0]
        assert "Executed: Action 'click'" in final_state["steps"][1]
        
        # Verify that browser execution actually took place
        result_text = await bm.page.inner_text("#result")
        assert "Form submitted! Name: TestUser" in result_text


