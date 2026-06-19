import json
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph as CompiledGraph

from agent.browser import BrowserManager, BrowserError
from agent.prompts import PLANNER_SYSTEM_PROMPT

logger = logging.getLogger("agent.graph")

class AgentState(TypedDict):
    task: str
    start_url: str
    current_url: str
    screenshot_b64: str
    page_text: str
    interactive_elements: List[Dict[str, Any]]
    steps: List[str]
    step_count: int
    done: bool
    success: bool
    result: str
    error: Optional[str]

async def observe_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    logger.debug("Running observe_node...")
    bm: BrowserManager = config.get("configurable", {}).get("browser_manager")
    if not bm:
        raise ValueError("browser_manager must be provided in config['configurable']")
    
    try:
        # If we just started, navigate to the start_url
        if not state.get("current_url") and state.get("start_url"):
            await bm.navigate(state["start_url"])
            
        screenshot = await bm.screenshot()
        elements = await bm.get_interactive_elements()
        text = await bm.get_page_text()
        current_url = bm.page.url
        
        return {
            "current_url": current_url,
            "screenshot_b64": screenshot,
            "page_text": text,
            "interactive_elements": elements,
            "step_count": state.get("step_count", 0) + 1
        }
    except Exception as e:
        logger.error(f"Error in observe_node: {e}")
        return {
            "error": f"Observation failed: {e}",
            "step_count": state.get("step_count", 0) + 1
        }

async def plan_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    logger.debug("Running plan_node...")
    if state.get("error"):
        return {}  # Bypass if we already hit an error
        
    bm: BrowserManager = config.get("configurable", {}).get("browser_manager")
    if not bm:
        raise ValueError("browser_manager must be provided in config['configurable']")
        
    try:
        # Build prompt variables for OpenAI call
        user_payload = {
            "task": state["task"],
            "page_text_summary": state["page_text"][:2000],
            "interactive_elements": state["interactive_elements"],
            "history": state.get("steps", [])
        }
        user_message_str = json.dumps(user_payload, indent=2)
        
        response = await bm.openai_client.chat.completions.create(
            model=bm.openai_client.default_model if hasattr(bm.openai_client, "default_model") else "nex-agi/nex-n2-pro:free",
            max_tokens=1000,
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message_str},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{state['screenshot_b64']}"
                            }
                        }
                    ]
                }
            ]
        )
        
        plan_text = response.choices[0].message.content.strip()
        logger.debug(f"Planner raw response: {plan_text}")
        
        # Clean up any potential markdown formatting
        cleaned_response = plan_text
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()
        
        plan_data = json.loads(cleaned_response)
        
        steps = list(state.get("steps", []))
        # Append the JSON plan directly to the steps list to be consumed by execute_node
        steps.append(f"Planned: {json.dumps(plan_data)}")
        
        return {
            "steps": steps,
            "done": plan_data.get("is_completed", False),
            "result": plan_data.get("final_answer", "")
        }
        
    except Exception as e:
        logger.error(f"Error in plan_node: {e}")
        return {
            "error": f"Planning failed: {e}"
        }

async def execute_node(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    logger.debug("Running execute_node...")
    if state.get("error"):
        return {}  # Bypass if error exists
        
    bm: BrowserManager = config.get("configurable", {}).get("browser_manager")
    if not bm:
        raise ValueError("browser_manager must be provided in config['configurable']")
        
    steps = list(state.get("steps", []))
    if not steps:
        return {"error": "No actions planned."}
        
    last_step = steps[-1]
    if not last_step.startswith("Planned: "):
        return {"error": f"Invalid format in action plan: {last_step}"}
        
    plan_json = last_step[len("Planned: "):]
    try:
        plan_data = json.loads(plan_json)
        actions = plan_data.get("actions", [])
        thought = plan_data.get("thought", "")
        
        executed_descriptions = []
        success = True
        error_msg = None
        
        for act in actions:
            action_type = act.get("action")
            selector = act.get("selector")
            text = act.get("text")
            url = act.get("url")
            direction = act.get("direction")
            pixels = act.get("pixels", 500)
            timeout = act.get("timeout", 5000)
            
            description = f"Action '{action_type}'"
            try:
                if action_type == "navigate":
                    description += f" to {url}"
                    await bm.navigate(url)
                elif action_type == "click":
                    description += f" on {selector}"
                    await bm.click(selector, timeout=timeout)
                elif action_type == "fill":
                    description += f" on {selector} with '{text}'"
                    await bm.fill(selector, text, timeout=timeout)
                elif action_type == "scroll":
                    description += f" {direction} by {pixels}px"
                    await bm.scroll(direction, pixels)
                elif action_type == "wait":
                    description += f" for {selector}"
                    visible = await bm.wait_for_selector(selector, timeout=timeout)
                    if not visible:
                        raise BrowserError(f"Element {selector} did not appear in {timeout}ms")
                else:
                    raise ValueError(f"Unknown action: {action_type}")
                    
                executed_descriptions.append(f"{description} (Success)")
            except Exception as e:
                logger.error(f"Error performing action: {e}")
                executed_descriptions.append(f"{description} (Failed: {e})")
                success = False
                error_msg = str(e)
                break
                
        # Update steps with execution confirmation
        steps[-1] = f"Thought: {thought} | Executed: {', '.join(executed_descriptions)}"
        
        return {
            "steps": steps,
            "success": success,
            "error": error_msg
        }
        
    except Exception as e:
        logger.error(f"Error in execute_node: {e}")
        steps[-1] = f"Failed to execute plan: {e}"
        return {
            "steps": steps,
            "success": False,
            "error": f"Execution failed: {e}"
        }

async def check_node(state: AgentState) -> Dict[str, Any]:
    logger.debug("Running check_node...")
    done = state.get("done", False)
    success = state.get("success", True)
    step_count = state.get("step_count", 0)
    error = state.get("error")
    
    if error is not None:
        done = True
        success = False
    elif step_count >= 10:
        done = True
        success = False
        error = "Maximum step limit of 10 reached"
        
    return {
        "done": done,
        "success": success,
        "error": error
    }

def should_continue(state: AgentState) -> str:
    if state.get("done", False):
        return "end"
    return "observe"

def compile_graph() -> CompiledGraph:
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("observe", observe_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("execute", execute_node)
    workflow.add_node("check", check_node)
    
    # Set entrypoint
    workflow.set_entry_point("observe")
    
    # Wire transitions
    workflow.add_edge("observe", "plan")
    workflow.add_edge("plan", "execute")
    workflow.add_edge("execute", "check")
    
    # Add conditional route from check
    workflow.add_conditional_edges(
        "check",
        should_continue,
        {
            "end": END,
            "observe": "observe"
        }
    )
    
    return workflow.compile()
