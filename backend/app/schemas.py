from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IdeaCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)

    @field_validator("content")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v


class IdeaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    environment: str
    cloud: str
    version: str
    database: str
