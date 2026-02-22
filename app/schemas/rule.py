import datetime as dt

from pydantic import BaseModel, Field, field_validator

from app.models.enums import RuleMatchType


class RuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=255)
    match_type: RuleMatchType = RuleMatchType.CONTAINS
    category_id: int
    priority: int = 0
    is_active: bool = True

    @field_validator("pattern")
    @classmethod
    def normalize_pattern(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Pattern cannot be empty")
        return normalized


class RuleUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=255)
    match_type: RuleMatchType | None = None
    category_id: int | None = None
    priority: int | None = None
    is_active: bool | None = None

    @field_validator("pattern")
    @classmethod
    def normalize_pattern(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("Pattern cannot be empty")
        return normalized


class RuleRead(BaseModel):
    id: int
    pattern: str
    match_type: RuleMatchType
    category_id: int
    category_name: str
    category_type: str
    priority: int
    is_active: bool
    created_at: dt.datetime


class RuleApplyResponse(BaseModel):
    processed: int
    updated: int
    skipped_locked: int
