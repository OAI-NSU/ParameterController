import asyncio
import os
from copy import copy
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from beanie import Document, init_beanie
from bytes_parser import BitField, BitFlag, Frame, Notification, Row
from dotenv import load_dotenv
from loguru import logger
from pydantic import Field
from pymongo import AsyncMongoClient
from sat_frames import frames_map_0x02

from parameter_controller.L0.config import get_qualifier, load_config, nested_dict
from parameter_controller.L0.models import (
    EventLevel,
    L0_History,
    L0_Parameter,
    L0_StatusEvent,
)


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
    level: EventLevel = EventLevel.Error if is_error else EventLevel.Warning
    return L0_StatusEvent(label=level.name, priority=level.value,
                          created_at=ts, min_val=min_val,
                          max_val=max_val, value=value)

class L0_ParameterDoc(L0_Parameter, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]


class L0_HistoryDoc(L0_History, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]


L0_PARAM_BEANIE = TypeVar("L0_PARAM_BEANIE", bound=L0_ParameterDoc)
L0_HISTORY_BEANIE = TypeVar("L0_HISTORY_BEANIE", bound=L0_HistoryDoc)


class L0_DB(Generic[L0_PARAM_BEANIE]):
    def __init__(self, model: type[L0_PARAM_BEANIE]):
        self.model: type[L0_PARAM_BEANIE] = model


class L0_HistoryDB(Generic[L0_HISTORY_BEANIE]):
    def __init__(self, model: type[L0_HISTORY_BEANIE]):
        self.model: type[L0_HISTORY_BEANIE] = model


class DB_ParamController:
    def __init__(self) -> None:
        load_dotenv()
        self.client = AsyncMongoClient(os.environ['DATABASE_URL'])
        self.db = self.client[os.environ['DB_NAME']]
        self.params = self.db['L0_ParameterDoc']
        self.history = self.db['L0_HistoryDoc']
        self.compare_onboard_time = False
        self.params_dict = nested_dict()
        self.relaxation_time = 1000

    async def init_db(self):
        await init_beanie(database=self.db,
                          document_models=[L0_ParameterDoc, L0_HistoryDoc])
        await self.load_config()

    async def load_config(self):
        for param in load_config(frames_map_0x02, self.params_dict):
            model = L0_ParameterDoc(**param)
            filter: dict = {
                'sat_id': model.sat_id,
                'dev_id': model.dev_id,
                'frame_type': model.frame_type,
                'field_label': model.field_label
            }
            if model.bitfield:
                filter['bitfield'] = model.bitfield

            if not await self.params.count_documents(filter):
                await L0_ParameterDoc.insert_one(model)


    async def on_received_data(self, hex_data: str, timestamp: datetime,
                               username: str, gs_label: str):
        bytes_data: bytes = bytes.fromhex(hex_data)
        sat_id, dev_id, flags, frame_type = get_qualifier(bytes_data)
        frame: Frame = frames_map_0x02[sat_id][dev_id][flags][frame_type]
        if flags == 1:
            logger.debug(f'Frame has incorrect flag: {hex_data}')
            return []
        frame.parse(hex_data)
        if not frame.rows[-1]._is_valid:
            logger.debug(f'Frame has invalid CRC: {hex_data}')
            return []  # CRC16 is not valid
        onboard_time: datetime = datetime.fromisoformat(frame.rows_dict['Время кадра']._repr_data)
        if self.compare_onboard_time:
            if onboard_time > timestamp and (onboard_time - timestamp).seconds > 5:
                logger.debug(f'Onboard and GS time delta: {(onboard_time - timestamp).seconds}')
                return []
            if onboard_time < timestamp and (timestamp - onboard_time).seconds > 5:
                logger.debug(f'Onboard and GS time delta: {(timestamp - onboard_time).seconds}')
                return []
        params = self.params_dict[sat_id][dev_id][frame_type]
        errors, warnings = frame.get_failed_params(params)
        filter: dict = {
            'sat_id': sat_id,
            'dev_id': dev_id,
            'frame_type': frame_type,
            'bitfield': None
        }
        notifications: list[Notification] = [*errors, *warnings]
        about_to_notify = []
        async for model, n in self.request_params(notifications, filter):
            if not model.bitfield:
                field = n.row
            else:
                field = n.row._bit_fields_kwarg[model.bitfield]
            new_status: L0_StatusEvent = create_status(timestamp, field)
            model.prev_level = model.level
            model.level = new_status.priority
            if model.update_status(new_status, self.relaxation_time):
                about_to_notify.append(model)
            await model.save()

    async def update_tracked_fields_history(self, ts: datetime, parsed_frame: Frame):
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

    async def request_params(self, notifications: list[Notification], filter: dict):
        for n in notifications:
            new_filter = copy(filter)
            new_filter['field_label'] = n.row.label
            if n.bitfield:
                for bit in n.bitfield:
                    new_filter['bitfield'] = bit.label
                    model_dict = await self.params.find_one(new_filter)
                    if model_dict:
                        yield L0_ParameterDoc.model_validate(model_dict), n
            else:
                model_dict = await self.params.find_one(new_filter)
                if model_dict:
                    yield L0_ParameterDoc.model_validate(model_dict), n

async def db_test():
    controller = DB_ParamController()
    await controller.init_db()
    await controller.load_config()

if __name__ == '__main__':
    asyncio.run(db_test())