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


class L0_Header(BaseModel):
    sat_label: str
    dev_label: str
    frame_label: str
    field_label: str
    bitfield: str | None = None
    sat_id: int
    dev_id: int
    frame_type: int


class L0_Parameter(L0_Header):
    # last_user: str = ''
    # last_gs: str = ''

    # onboard_time: datetime = Field(default_factory=creation_time)

    # hex_data: str = ''
    # last_update: datetime = Field(default_factory=creation_time)
    # prev_hex_data: str = ''
    # prev_last_update: datetime = Field(default_factory=creation_time)

    status: L0_StatusEvent | None = None
    alarm_status: bool = False

    level: int = EventLevel.Normalized.value
    prev_level: int = EventLevel.Normalized.value

    emited_at: datetime | None = None

    def update_status(self, new_status: L0_StatusEvent,
                      relaxation_time: int) -> bool:
        if not self.status:
            self.status = new_status
            return True
        else:
            if self.status.priority < self.level:
                self.status = new_status
                return True
            elif self.status.priority == self.level and self.is_ready_to_emit(relaxation_time):
                return True
            return False

    def is_ready_to_emit(self, relaxation_time: int) -> bool:
        if self.emited_at:
            return (datetime.now(UTC) - self.emited_at).seconds > relaxation_time
        return True


class L0_History(L0_Header):
    alarm_history: list[L0_StatusEvent] = Field(default_factory=list)
    history: list[tuple[datetime, int]] = Field(default_factory=list)
