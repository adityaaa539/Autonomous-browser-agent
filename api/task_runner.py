import uuid
import logging
import asyncio
from db.database import AsyncSessionLocal
from db.crud import update_task_status, update_task_result, update_task_error
from agent.runner import run_agent

logger = logging.getLogger("api.task_runner")

async def run_agent_task(task_id: uuid.UUID, prompt: str, start_url: str):
    logger.info(f"Task {task_id}: Starting run_agent_task in background.")
    db = AsyncSessionLocal()
    try:
        # Update status to running
        await update_task_status(db, task_id, "running")
        await db.commit()

        try:
            # Call the agent
            res = await run_agent(prompt, start_url, task_id=task_id, db=db)
            status = "done" if res["success"] else "failed"
            
            # Update task result
            await update_task_result(
                db,
                task_id,
                result_json={"result": res["result"]} if res["result"] is not None else None,
                steps_json=res["steps"],
                step_count=res["step_count"],
                status=status
            )
            
            # If the run failed, update error message
            if not res["success"] and res.get("error"):
                await update_task_error(db, task_id, res["error"])
                
            await db.commit()
            logger.info(f"Task {task_id}: Finished agent execution with status '{status}'.")
            
        except Exception as agent_err:
            logger.exception(f"Task {task_id}: Agent exception occurred.")
            await update_task_error(db, task_id, str(agent_err))
            await db.commit()
            
    except Exception as db_err:
        logger.exception(f"Task {task_id}: Database exception occurred during run_agent_task setup.")
        
    finally:
        await db.close()

def schedule_agent_task(task_id: uuid.UUID, prompt: str, start_url: str) -> asyncio.Task:
    logger.info(f"Scheduling background task {task_id}")
    task = asyncio.create_task(run_agent_task(task_id, prompt, start_url))
    return task
