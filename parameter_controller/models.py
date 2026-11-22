from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from bytes_parser import BitField, BitFlag, Row
from pydantic import BaseModel, Field


def creation_time() -> datetime:
    return datetime.now().astimezone(UTC)



class TMI_Model(BaseModel):
    timestamp: datetime
    session_id: UUID | None = None
    username: str
    sat_ip: str
    rx_gs_ip: str = ''
    gs_label: str = ''
    gs_ip: str
    loc_id: int
    is_repeated: bool = False
    raw_data: str
    sat_az: float
    sat_el: float
    rot_az: float
    rot_el: float
    rot_time_offset: int = 0
    lat: float = 0
    lon: float = 0
    alt: float = 0
    distance_km: float = 0
    tx_power: float = 0
    is_beacon: bool = False
    sat_rssi: float = 0
    sat_snr: float = 0
    rssi: float
    mode: Literal['LoRa', 'FSK']
    sf: int = 10
    bw: int | float = 250
    cr: int = 1
    freq: int
    dopler: float
    snr: int
    fei: float
    sat_id: int

class EventLevel(Enum):
    Error = 0
    Warning = 1
    Info = 2

class StatusEvent(BaseModel):
    label: str
    priority: int
    relaxation_time: int
    timestamp: datetime
    last_timestamp: datetime
    last_emited: datetime
    amount_before_processed: int = 1
    processed_timestamp: datetime | None = None
    value: float | int | bool
    min_val: float | int | bool | None = None
    max_val: float | int | bool | None = None


class EventsLog(BaseModel):
    pending: list[StatusEvent]
    processed: list[StatusEvent]

class Qualifier(BaseModel):
    value: int
    sat_id: int
    dev_id: int
    frame_type: int

class AlarmCondition(BaseModel):
    label: str
    bitfield: str | None = None
    qualifier: Qualifier
    status: StatusEvent | None = None

    def update_data(self, ts: datetime, field: Row | BitField | BitFlag) -> bool:
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
        if not (is_error or is_warning):
            return False
        level: EventLevel = EventLevel.Error if is_error else EventLevel.Warning
        now = datetime.now(UTC)
        if not self.status:
            self.status = StatusEvent(
                label=level.name,
                priority=level.value,
                relaxation_time=1000,
                timestamp=ts,
                last_timestamp=ts,
                min_val=min_val,
                max_val=max_val,
                value=value,
                last_emited=now
            )
            return True
        else:
            if self.status.priority > level.value:
                self.status = StatusEvent(
                    label=level.name,
                    priority=level.value,
                    relaxation_time=1000,
                    timestamp=ts,
                    last_timestamp=ts,
                    min_val=min_val,
                    max_val=max_val,
                    value=value,
                    last_emited=now
                )
                return True
            elif self.status.priority == level.value:
                self.status.value = value
                self.status.amount_before_processed += 1
                self.status.last_timestamp = ts
                if (now - self.status.last_emited).seconds > self.status.relaxation_time:
                    self.status.last_emited = now
                    return True
            return False

class TMI_Status(BaseModel):
    frame_type: int
    name: str
    hex_data: str = ''
    alarm_condition: list[AlarmCondition] = Field(default_factory=list)
    alarm: dict[str, AlarmCondition] = Field(default_factory=dict)
    last_update: datetime = Field(default_factory=creation_time)

    prev_hex_data: str = ''
    prev_alarm: dict[str, AlarmCondition] = Field(default_factory=dict)
    prev_last_update: datetime = Field(default_factory=creation_time)

    def add_tmi(self, data: str, timestamp: datetime,
                alarm_status: dict[str, AlarmCondition]):
        self.prev_hex_data = self.hex_data
        self.prev_last_update = deepcopy(self.last_update)
        self.prev_alarm = deepcopy(self.alarm)
        self.hex_data = data
        self.alarm = alarm_status
        self.last_update = timestamp

class SatVault(BaseModel):
    data: dict = Field(default_factory=dict)
    last_edit: datetime = Field(default_factory=creation_time)
    gs_name: str = ''
    username: str = ''

class SubsystemState(BaseModel):
    dev_id: int
    label: str
    tmi: dict[int, TMI_Status] = Field(default_factory=dict)
    last_update: datetime = Field(default_factory=creation_time)

    vault: SatVault = Field(default_factory=SatVault)
    prev_vault: SatVault = Field(default_factory=SatVault)

class SatModel(BaseModel):
    label: str
    sat_id: int
    last_session: datetime = Field(default_factory=creation_time)
    last_user: str = ''
    last_gs: str = ''
    onboard_time: datetime = Field(default_factory=creation_time)

    alarm_status: bool = False
    vault: SatVault = Field(default_factory=SatVault)
    prev_vault: SatVault = Field(default_factory=SatVault)
    subsystems: dict[int, SubsystemState] = Field(default_factory=dict)
