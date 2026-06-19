from typing import TypedDict, Any
from langgraph.graph import StateGraph, END
import logging

logger = logging.getLogger(__name__)

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

# PART B — Four stub node functions (we fill them in next steps):

async def observe_node(state): return {}
async def plan_node(state): return {}
async def execute_node(state): return {}
async def check_node(state):
    if state.get("done") or state.get("step_count",0)>=20: return {"done":True}
    if state.get("error"): return {"done":True,"success":False}
    return {"done":False}

# PART C — Router and graph wiring:

def should_continue(state):
    if state.get("done") or state.get("step_count",0)>=20: return "end"
    return "continue"

def compile_graph():
    graph = StateGraph(AgentState)
    graph.add_node("observe", observe_node)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("check", check_node)
    graph.set_entry_point("observe")
    graph.add_edge("observe","plan")
    graph.add_edge("plan","execute")
    graph.add_edge("execute","check")
    graph.add_conditional_edges("check", should_continue, {"continue":"observe","end":END})
    return graph.compile()
