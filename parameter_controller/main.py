from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from frames_parser import frames_map, get_frame
from pydantic import BaseModel, Field
from sat_frames import frames_map_0x02

frames_map[0x02].update(frames_map_0x02)


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

class AlarmCondition(BaseModel):
    label: str
    bitfield: str | None = None
    value: float | int | bool | None = None
    min_val: float | int | bool | None = None
    max_val: float | int | bool | None = None

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

    alarm_status: bool = False
    vault: SatVault = Field(default_factory=SatVault)
    prev_vault: SatVault = Field(default_factory=SatVault)
    subsystems: dict[int, SubsystemState] = Field(default_factory=dict)


def register_brk_parameters():
    from sat_frames.GRIFON.BRK.frames.tmi0 import tmi0

    # tmi0.subscribe([
    #     ''
    # ])

class ParamController:
    def __init__(self) -> None:
        self.state: dict[int, SatModel] = {}

    def on_received_data(self, model: TMI_Model):
        frame, qualifier = get_frame(bytes.fromhex(model.raw_data), frames_map)
        sat_id_val, sat_id_label = qualifier[1]
        dev_id_val, dev_id_label = qualifier[2]
        flag_val, _ = qualifier[3]
        frame_type_val, frame_type_label = qualifier[4]
        if flag_val == 1:
            return
        frame.parse(model.raw_data)
        sat: SatModel | None = self.state.get(sat_id_val)
        if not sat:
            sat = SatModel(label=sat_id_label, sat_id=sat_id_val)
            self.state[sat_id_val] = sat

        sat.last_user = model.username
        sat.last_gs = model.gs_label
        sat.last_session = model.timestamp

        subsystem = sat.subsystems.get(dev_id_val)
        if not subsystem:
            subsystem = SubsystemState(dev_id=dev_id_val, label=dev_id_label)
        subsystem.last_update = model.timestamp

        tmi = subsystem.tmi.get(frame_type_val)
        if not tmi:
            tmi = TMI_Status(frame_type=frame_type_val, name=frame_type_label)
        tmi.add_tmi(model.raw_data, model.timestamp)


        #         self.parse(model.raw_data)
        #         alarm_status = {}
        #         tmi: TMI_Status = subsystem.tmi.setdefault(frame_type, TMI_Status(frame_type=frame_type))
        #         subsystem.last_update = model.timestamp
        #         tmi.add_tmi(model.raw_data, model.timestamp, alarm_status)

if __name__ == '__main__':
    ...