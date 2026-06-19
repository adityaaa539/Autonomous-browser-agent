import logging
from agent.browser import BrowserManager
from agent.graph import compile_graph, set_browser_context

logger = logging.getLogger(__name__)

async def run_agent(task: str, start_url: str) -> dict:
    logger.info(f"Starting agent run for task: '{task}' at URL: '{start_url}'")
    
    # Create compile_graph()
    graph = compile_graph()
    
    # Setup initial AgentState with all 13 fields
    initial_state = {
        "task": task,
        "start_url": start_url,
        "current_url": "",
        "screenshot_b64": "",
        "page_text": "",
        "interactive_elements": [],
        "steps": [],
        "pending_action": {},
        "step_count": 0,
        "done": False,
        "success": True,
        "result": "",
        "error": ""
    }
    
    # Use async with BrowserManager() as browser
    async with BrowserManager() as browser:
        # Call set_browser_context(browser)
        set_browser_context(browser)
        
        # Navigate to start_url
        await browser.navigate(start_url)
        
        # Call graph.ainvoke(initial_state)
        final_state = await graph.ainvoke(initial_state)
        
        # Return {success, result, error, steps, step_count}
        return {
            "success": final_state.get("success", False),
            "result": final_state.get("result", ""),
            "error": final_state.get("error", ""),
            "steps": final_state.get("steps", []),
            "step_count": final_state.get("step_count", 0)
        }
