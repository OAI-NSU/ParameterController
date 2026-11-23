from copy import deepcopy
from datetime import UTC, datetime
from enum import Enum

from bytes_parser import BitField, BitFlag, Frame, Notification, Row
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
    amount_before_processed: int = 1
    processed_at: datetime | None = None
    processed_by_user: str | None = None
    user_comment: str = ''
    value: float | int | bool
    min_val: float | int | bool | None = None
    max_val: float | int | bool | None = None


class Qualifier(BaseModel):
    sat_id: int
    dev_id: int
    frame_type: int


class L0_TrackedField(BaseModel):
    label: str
    bitfield: str | None = None
    qualifier: Qualifier

    level: int = EventLevel.Normalized.value
    prev_level: int = EventLevel.Normalized.value

    relaxation_time: int = 1000
    emited_at: datetime | None = None

    status: L0_StatusEvent | None = None
    history: list[tuple[datetime, int]] = Field(default_factory=list)

    def get_ready_events(self, ts: datetime, field: Row | BitField | BitFlag) -> bool:
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
        new_status = L0_StatusEvent(label=level.name, priority=level.value,
                                    created_at=ts, min_val=min_val,
                                    max_val=max_val, value=value)
        if not self.status:
            self.status = new_status
            return True
        else:
            if self.status.priority < level.value:
                self.status = new_status
                return True
            elif self.status.priority == level.value and self.is_ready_to_emit():
                return True
            return False

    def is_ready_to_emit(self) -> bool:
        if self.emited_at:
            return (datetime.now(UTC) - self.emited_at).seconds > self.relaxation_time
        return True


class TMI_Status(BaseModel):
    qualifier: Qualifier
    name: str
    hex_data: str = ''
    last_update: datetime = Field(default_factory=creation_time)
    prev_hex_data: str = ''
    prev_last_update: datetime = Field(default_factory=creation_time)
    L0_tracking_fields: dict[str, L0_TrackedField | dict[str, L0_TrackedField]] = Field(default_factory=dict)

    def add_tmi(self, data: str, ts: datetime,
                notifications: list[Notification]) -> list[L0_StatusEvent]:
        self.prev_hex_data = self.hex_data
        self.prev_last_update = deepcopy(self.last_update)
        self.hex_data = data
        self.last_update = ts

        about_to_notify: list[L0_StatusEvent] = []
        for notification in notifications:
            field = self.L0_tracking_fields[notification.row.label]
            if isinstance(field, L0_TrackedField):
                event: None | L0_StatusEvent = field.get_ready_events(ts, notification.row)
                if event:
                    field.emited_at = ts
                    about_to_notify.append(event)
            else:
                for bit in notification.bitfield:
                    bitfield_alarm: L0_TrackedField = field[bit.label]
                    event = bitfield_alarm.get_ready_events(ts, bit)
                    if event:
                        bitfield_alarm.emited_at = ts
                        about_to_notify.append(event)
        return about_to_notify

    def check_tracked_fields(self, ts: datetime, parsed_frame: Frame):
        for label, field in self.L0_tracking_fields.items():
            if isinstance(field, dict):
                for bit_label, bitfield in field.items():
                    bitfield.prev_level = bitfield.level
                    bit = parsed_frame.rows_dict[label]._bit_fields_kwarg[bit_label]
                    if not bit.is_valid:
                        bitfield.level = 3
                    else:
                        bitfield.level = 0
            else:
                field.prev_level = field.level
                row: Row = parsed_frame.rows_dict[label]
                if not row._is_valid:
                    field.level = 3
                elif row._is_warn:
                    field.level = 2
                else:
                    field.level = 0
                if field.prev_level != field.level:
                    field.history.append((ts, field.level))


    def get_tracking_labels(self) -> list[str | tuple[str, tuple[str, ...]]]:
        labels: list[str | tuple[str, tuple[str, ...]]] = []
        for key, val in self.L0_tracking_fields.items():
            if isinstance(val, L0_TrackedField):
                labels.append(val.label)
            else:
                labels.append((key, tuple([(v.bitfield) for v in val.values()
                                           if v.bitfield])))
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

    def init_tmi(self, frames_map: dict, frame_type: int,
                 params: list[str | tuple[str, list[str]]]) -> None:
        if not params:
            return
        tmi_name = frames_map[self.sat_id][self.dev_id][0][frame_type].frame_type
        q = Qualifier(sat_id=self.sat_id, dev_id=self.dev_id, frame_type=frame_type)
        tmi = TMI_Status(name=tmi_name, qualifier=q)
        for param in params:
            if isinstance(param, str):
                tmi.L0_tracking_fields[param] = L0_TrackedField(label=param, qualifier=q)
            else:
                tmi.L0_tracking_fields[param[0]] = {
                    p: L0_TrackedField(label=param[0], bitfield=p, qualifier=q)
                    for p in param[1]
                }
        self.tmi[frame_type] = tmi


class L0_Alarms(BaseModel):
    pending: list[L0_StatusEvent] = Field(default_factory=list)
    processed: list[L0_StatusEvent] = Field(default_factory=list)


class SatModel(BaseModel):
    label: str
    sat_id: int
    last_session: datetime = Field(default_factory=creation_time)
    last_user: str = ''
    last_gs: str = ''

    onboard_time: datetime = Field(default_factory=creation_time)
    subsystems: dict[int, SubsystemState] = Field(default_factory=dict)

    alarms: L0_Alarms = L0_Alarms()
    alarm_status: bool = False

    vault: SatVault = Field(default_factory=SatVault)
    prev_vault: SatVault = Field(default_factory=SatVault)

    def init_dev_id_from_config(self, sat_id: int, dev_id: int | tuple[int, ...],
                                dev_id_dict: dict[int, list[str | tuple[str, list[str]]]],
                                frames_map: dict):
            if isinstance(dev_id, tuple):
                for d_id in dev_id:
                    dev_id_label: str = frames_map[sat_id][d_id]['label']
                    subsystem = SubsystemState(sat_id=sat_id, dev_id=d_id,
                                               label=dev_id_label)
                    self.subsystems[d_id] = subsystem
                    for frame_type, params in dev_id_dict.items():
                        subsystem.init_tmi(frames_map, frame_type, params)
            else:
                dev_id_label: str = frames_map[sat_id][dev_id]['label']
                subsystem = SubsystemState(sat_id=sat_id, dev_id=dev_id,
                                           label=dev_id_label)
                self.subsystems[dev_id] = subsystem
                for frame_type, params in dev_id_dict.items():
                    subsystem.init_tmi(frames_map, frame_type, params)
