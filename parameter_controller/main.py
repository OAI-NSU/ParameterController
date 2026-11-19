from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

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



class ParamController:
    def __init__(self) -> None:
        self.state: dict[int, SatModel] = {}
        self.parse: Callable | None = None

    def received_data(self, model: TMI_Model):
        if not self.parse:
            return
        sat_id: int = model.sat_id & 0x3FFF
        sat: SatModel | None = self.state.get(sat_id)
        if sat:
            sat.last_user = model.username
            sat.last_gs = model.gs_label
            sat.last_session = model.timestamp
            sat.sat_id = sat_id
            dev_id = (model.loc_id & 0xF000) >> 8
            frame_type = model.loc_id & 0x0F
            subsystem = sat.subsystems.get(dev_id)
            if subsystem:
                self.parse(model.raw_data)
                alarm_status = {}
                tmi: TMI_Status = subsystem.tmi.setdefault(frame_type, TMI_Status(frame_type=frame_type))
                subsystem.last_update = model.timestamp
                tmi.add_tmi(model.raw_data, model.timestamp, alarm_status)

if __name__ == '__main__':
    ...