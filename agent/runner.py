import json
import logging
from agent.browser import BrowserManager
from agent.graph import compile_graph, set_browser_context
from db.crud import append_step

logger = logging.getLogger(__name__)

async def run_agent(task: str, start_url: str, task_id=None, db=None) -> dict:
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
        
        final_state = initial_state
        written_steps_count = 0
        
        # Call graph.astream(initial_state, stream_mode="values")
        async for event in graph.astream(initial_state, stream_mode="values"):
            final_state = event
            steps = event.get("steps") or []
            if db and task_id and len(steps) > written_steps_count:
                latest = steps[-1]
                if isinstance(latest, str):
                    try:
                        latest = json.loads(latest)
                    except Exception:
                        latest = {"raw": latest}
                await append_step(db, task_id, latest)
                await db.commit()
                written_steps_count = len(steps)
        
        # Return {success, result, error, steps, step_count}
        return {
            "success": final_state.get("success", False),
            "result": final_state.get("result", ""),
            "error": final_state.get("error", ""),
            "steps": final_state.get("steps", []),
            "step_count": final_state.get("step_count", 0)
        }
