from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum

from bytes_parser import BitField, BitFlag, Notification, Row
from pydantic import BaseModel, Field


def creation_time() -> datetime:
    return datetime.now().astimezone(UTC)


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
    # value: int
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
    qualifier: Qualifier
    name: str
    hex_data: str = ''
    last_update: datetime = Field(default_factory=creation_time)
    prev_hex_data: str = ''
    prev_last_update: datetime = Field(default_factory=creation_time)
    tracking_fields: dict[str, AlarmCondition | dict[str, AlarmCondition]] = Field(default_factory=dict)

    def add_tmi(self, data: str, ts: datetime, notifications: list[Notification]) -> list[AlarmCondition]:
        self.prev_hex_data = self.hex_data
        self.prev_last_update = deepcopy(self.last_update)
        self.hex_data = data
        self.last_update = ts

        about_to_notify: list[AlarmCondition] = []
        for notification in notifications:
            field = self.tracking_fields[notification.row.label]
            if isinstance(field, AlarmCondition):
                if field.update_data(ts, notification.row):
                    about_to_notify.append(field)
            else:
                for bit in notification.bitfield:
                    bitfield_alarm: AlarmCondition = field[bit.label]
                    if bitfield_alarm.update_data(ts, bit):
                        about_to_notify.append(bitfield_alarm)
        return about_to_notify

    def get_tracking_labels(self) -> list[str | tuple[str, tuple[str, ...]]]:
        labels: list[str | tuple[str, tuple[str, ...]]] = []
        for key, val in self.tracking_fields.items():
            if isinstance(val, AlarmCondition):
                labels.append(val.label)
            else:
                labels.append((key, tuple([(v.bitfield) for v in val.values() if v.bitfield])))
        return labels


class SatVault(BaseModel):
    data: dict = Field(default_factory=dict)
    last_edit: datetime = Field(default_factory=creation_time)
    gs_name: str = ''
    username: str = ''


class SubsystemState(BaseModel):
    dev_id: int
    sat_id: int
    label: str
    tmi: dict[int, TMI_Status] = Field(default_factory=dict)
    last_update: datetime = Field(default_factory=creation_time)

    vault: SatVault = Field(default_factory=SatVault)
    prev_vault: SatVault = Field(default_factory=SatVault)

    def init_tmi(self, frames_map: dict, frame_type: int, params: list[str | tuple[str, list[str]]]):
        if not params:
            return
        tmi_name = frames_map[self.sat_id][self.dev_id][0][frame_type].frame_type
        q = Qualifier(sat_id=self.sat_id, dev_id=self.dev_id, frame_type=frame_type)
        tmi = TMI_Status(name=tmi_name, qualifier=q)
        for param in params:
            if isinstance(param, str):
                tmi.tracking_fields[param] = AlarmCondition(label=param, qualifier=q)
            else:
                tmi.tracking_fields[param[0]] = {
                    p: AlarmCondition(label=param[0], bitfield=p, qualifier=q)
                    for p in param[1]
                }
        self.tmi[frame_type] = tmi

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

    def init_dev_id_from_config(self, sat_id: int, dev_id: int | tuple[int, ...],
                                dev_id_dict: dict[int, list[str | tuple[str, list[str]]]],
                                frames_map: dict):
            if isinstance(dev_id, tuple):
                for d_id in dev_id:
                    dev_id_label: str = frames_map[sat_id][d_id]['label']
                    subsystem = SubsystemState(sat_id=sat_id, dev_id=d_id, label=dev_id_label)
                    self.subsystems[d_id] = subsystem
                    for frame_type, params in dev_id_dict.items():
                        subsystem.init_tmi(frames_map, frame_type, params)
            else:
                dev_id_label: str = frames_map[sat_id][dev_id]['label']
                subsystem = SubsystemState(sat_id=sat_id, dev_id=dev_id, label=dev_id_label)
                self.subsystems[dev_id] = subsystem
                for frame_type, params in dev_id_dict.items():
                    subsystem.init_tmi(frames_map, frame_type, params)
