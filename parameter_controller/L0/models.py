from datetime import UTC, datetime
from enum import Enum

from bytes_parser import BitField, BitFlag, Row
from pydantic import BaseModel, Field


def creation_time() -> datetime:
    return datetime.now().astimezone(UTC)


class EventLevel(Enum):
    Normalized = 0
    Info = 1
    Warning = 2
    Error = 3


class PendingEvent(BaseModel):
    created_at: datetime
    value: float | int | bool
    min_val: float | int | bool | None = None
    max_val: float | int | bool | None = None


class ProcessedEvent(PendingEvent):
    processed_at: datetime | None = None
    processed_by_user: str | None = None
    user_comment: str = ''


class Qualifier(BaseModel):
    sat_id: int
    dev_id: int
    frame_type: int
    sat_label: str
    dev_label: str
    frame_label: str


class ParamHeader(Qualifier):
    field_label: str
    bitfield: str | None = None


class Parameter(ParamHeader):
    level: int = EventLevel.Normalized.value
    prev_level: int = EventLevel.Normalized.value

    emited_at: datetime | None = None
    emited_level: int = EventLevel.Normalized.value

    def is_ready_to_emit(self, relaxation_time: int) -> bool:
        if self.emited_at:
            return (datetime.now(UTC) - self.emited_at).seconds > relaxation_time
        return True


class History(ParamHeader):
    alarm_history: list[ProcessedEvent] = Field(default_factory=list)
    history: list[tuple[datetime, int]] = Field(default_factory=list)


class TMI_State(Qualifier):
    hex_data: str = ''
    last_update: datetime = Field(default_factory=creation_time)


def create_status(ts: datetime, field: Row | BitField | BitFlag):
    min_val: int | float | None = None
    max_val: int | float | None = None
    if isinstance(field, Row):
        value: int | float = field._parsed_val
        is_error: bool = not field._is_valid
        is_warning: bool = field._is_warn
        if is_error:
            min_val = field.min_value
            max_val = field.max_value
        elif is_warning:
            min_val = field.warn_min_value
            max_val = field.warn_max_value
    else:
        value = field._value
        is_error = not field.is_valid
        is_warning = False
        if isinstance(field, BitField) and is_error:
            min_val = field.min_value
            max_val = field.max_value
    return ProcessedEvent(created_at=ts, min_val=min_val,
                          max_val=max_val, value=value)