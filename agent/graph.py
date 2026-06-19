import json
import os
import asyncio
import logging
from typing import TypedDict, Any
from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from agent.browser import BrowserManager
from agent.prompts import PLANNER_SYSTEM_PROMPT, ACTION_SCHEMA

logger = logging.getLogger(__name__)

# Module-level browser context
_browser_context = None
def set_browser_context(b): global _browser_context; _browser_context = b
def get_browser_context():
    if _browser_context is None: raise RuntimeError("Browser context not set")
    return _browser_context

class AgentState(TypedDict):
    task: str
    start_url: str
    current_url: str
    screenshot_b64: str
    page_text: str
    interactive_elements: list
    steps: list
    pending_action: dict
    step_count: int
    done: bool
    success: bool
    result: str
    error: str

# Node implementations

async def observe_node(state: AgentState):
    logger.info("Observing current page state...")
    browser = get_browser_context()
    
    # If starting, navigate to start_url
    if not state.get("current_url") and state.get("start_url"):
        await browser.navigate(state["start_url"])
        
    current_url = await browser.get_current_url()
    screenshot_b64 = await browser.screenshot()
    page_text = await browser.get_page_text()
    interactive_elements = await browser.get_interactive_elements()
    
    return {
        "current_url": current_url,
        "screenshot_b64": screenshot_b64,
        "page_text": page_text,
        "interactive_elements": interactive_elements,
        "step_count": state.get("step_count", 0) + 1
    }

async def plan_node(state: AgentState):
    logger.info("Planning next action...")
    client = AsyncOpenAI()
    
    # Build text content representing current state
    user_data = {
        "task": state.get("task", ""),
        "current_url": state.get("current_url", ""),
        "interactive_elements": state.get("interactive_elements", []),
        "history": state.get("steps", [])
    }
    user_text = json.dumps(user_data, indent=2)
    
    # Call OpenAI API with image and text
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{state.get('screenshot_b64', '')}"
                        }
                    }
                ]
            }
        ],
        max_tokens=1000
    )
    
    raw_content = response.choices[0].message.content.strip()
    
    # Strip markdown code fences if present
    cleaned = raw_content
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    
    try:
        pending_action = json.loads(cleaned)
        if not isinstance(pending_action, dict):
            raise ValueError("Response is not a JSON object")
            
        # Fallback 1: if it has "is_completed": true or "final_answer"
        if pending_action.get("is_completed") is True or "final_answer" in pending_action:
            pending_action["action"] = "done"
            pending_action["params"] = {"result": pending_action.get("final_answer", "")}
            
        # Fallback 2: if it has "actions" list
        elif "action" not in pending_action and "actions" in pending_action:
            actions_list = pending_action["actions"]
            if actions_list and isinstance(actions_list, list):
                first_act = actions_list[0]
                pending_action["action"] = first_act.get("action")
                pending_action["params"] = {k: v for k, v in first_act.items() if k not in ("action", "thought")}
                if "reasoning" not in pending_action:
                    pending_action["reasoning"] = pending_action.get("thought", "") or first_act.get("thought", "")
        
        # Validate that action is now present
        if "action" not in pending_action:
            raise ValueError("Response JSON is missing 'action' field")
            
    except Exception as e:
        logger.error(f"Failed to parse planner response: {cleaned}. Error: {e}")
        pending_action = {
            "action": "fail",
            "params": {"reason": f"Invalid planner response: {e}. Raw response: {cleaned[:200]}"},
            "reasoning": "OpenAI did not return a valid JSON object matching the action schema."
        }
        
    steps = list(state.get("steps") or [])
    steps.append(cleaned)
    
    return {
        "pending_action": pending_action,
        "steps": steps
    }

async def execute_node(state: AgentState):
    logger.info("Executing pending action...")
    browser = get_browser_context()
    pending_action = state.get("pending_action") or {}
    action_type = pending_action.get("action")
    params = pending_action.get("params") or {}
    
    updates = {
        "step_count": state.get("step_count", 0) + 1
    }
    
    try:
        if action_type == "navigate":
            url = params.get("url")
            if not url:
                raise ValueError("Missing 'url' parameter for navigate action")
            await browser.navigate(url)
            
        elif action_type == "click":
            selector = params.get("selector")
            if not selector:
                raise ValueError("Missing 'selector' parameter for click action")
            await browser.click(selector)
            await asyncio.sleep(0.8)
            
        elif action_type in ("fill", "select"):
            selector = params.get("selector")
            text = params.get("text") or params.get("value")
            if not selector or text is None:
                raise ValueError("Missing 'selector' or 'text'/'value' parameter for fill/select action")
            
            is_select = False
            try:
                is_select = await browser.page.evaluate(
                    f"document.querySelector('{selector}').tagName.toLowerCase() === 'select'"
                )
            except Exception:
                pass
                
            if is_select:
                await browser.page.select_option(selector, label=text)
            else:
                await browser.fill(selector, text)
            
        elif action_type == "scroll":
            direction = params.get("direction", "down")
            pixels = params.get("pixels", 500)
            try:
                pixels = int(pixels)
            except Exception:
                pixels = 500
            await browser.scroll(direction, pixels)
            
        elif action_type == "extract":
            updates["done"] = True
            updates["success"] = True
            
            data = params.get("data")
            selector = params.get("selector")
            
            if data is not None:
                updates["result"] = data
            elif selector:
                try:
                    element_text = await browser.page.inner_text(selector)
                    updates["result"] = element_text.strip()
                except Exception as e:
                    updates["result"] = f"Failed to extract selector text: {e}"
            else:
                try:
                    updates["result"] = await browser.page.title()
                except Exception:
                    updates["result"] = ""
            
        elif action_type == "done":
            updates["done"] = True
            updates["success"] = True
            updates["result"] = params.get("result")
            
        elif action_type == "fail":
            updates["done"] = True
            updates["success"] = False
            updates["error"] = params.get("reason")
            
        else:
            raise ValueError(f"Unknown action: {action_type}")
            
    except Exception as e:
        logger.error(f"Error executing action: {e}")
        updates["done"] = True
        updates["success"] = False
        updates["error"] = str(e)
        
    return updates

async def check_node(state):
    if state.get("done") or state.get("step_count", 0) >= 20:
        return {"done": True}
    if state.get("error"):
        return {"done": True, "success": False}
    return {"done": False}

# PART C — Router and graph wiring:

def should_continue(state):
    if state.get("done") or state.get("step_count", 0) >= 20:
        return "end"
    return "continue"

def compile_graph():
    graph = StateGraph(AgentState)
    graph.add_node("observe", observe_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("check", check_node)
    graph.set_entry_point("observe")
    graph.add_edge("observe", "plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "check")
    graph.add_conditional_edges("check", should_continue, {"continue": "observe", "end": END})
    return graph.compile()
