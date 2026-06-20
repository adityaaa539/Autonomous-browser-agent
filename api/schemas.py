import uuid
from datetime import datetime
from pydantic import BaseModel, Field, validator, root_validator

class TaskCreate(BaseModel):
    prompt: str = Field(..., min_length=5)
    start_url: str

    @validator("start_url")
    def validate_start_url(cls, v):
        if not v.startswith("http"):
            raise ValueError("start_url must start with http")
        return v

class TaskResponse(BaseModel):
    id: uuid.UUID
    prompt: str
    start_url: str
    status: str
    result_json: dict | None = None
    error: str | None = None
    step_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        from_attributes = True

    @root_validator(pre=True)
    def compute_step_count(cls, values):
        if not isinstance(values, dict):
            # ORM object
            data = {}
            for field in ["id", "prompt", "start_url", "status", "result_json", "error", "created_at", "updated_at"]:
                data[field] = getattr(values, field, None)
            steps = getattr(values, "steps_json", None)
            data["step_count"] = len(steps) if steps else 0
            return data
        else:
            # Dict
            steps = values.get("steps_json")
            values["step_count"] = len(steps) if steps else 0
            return values
