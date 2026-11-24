from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def creation_time() -> datetime:
    return datetime.now().astimezone(UTC)


class EventLevel(Enum):
    Normalized = 0
    Info = 1
    Warning = 2
    Error = 3


class L0_StatusEvent(BaseModel):
    label: str
    priority: int
    created_at: datetime
    processed_at: datetime | None = None
    processed_by_user: str | None = None
    user_comment: str = ''
    value: float | int | bool
    min_val: float | int | bool | None = None
    max_val: float | int | bool | None = None


class L0_Parameter(BaseModel):
    sat_label: str
    dev_label: str
    frame_label: str
    field_label: str
    bitfield: str | None = None

    sat_id: int
    dev_id: int
    frame_type: int

    last_user: str = ''
    last_gs: str = ''

    onboard_time: datetime = Field(default_factory=creation_time)

    hex_data: str = ''
    last_update: datetime = Field(default_factory=creation_time)
    prev_hex_data: str = ''
    prev_last_update: datetime = Field(default_factory=creation_time)

    alarm: L0_StatusEvent | None = None
    alarm_status: bool = False

    level: int = EventLevel.Normalized.value
    prev_level: int = EventLevel.Normalized.value

    relaxation_time: int = 1000
    emited_at: datetime | None = None

    status: L0_StatusEvent | None = None


class L0_History(BaseModel):
    sat_label: str
    dev_label: str
    frame_label: str
    field_label: str
    bitfield: str | None = None

    sat_id: int
    dev_id: int
    frame_type: int

    alarm_history: list[L0_StatusEvent] = Field(default_factory=list)
    history: list[tuple[datetime, int]] = Field(default_factory=list)