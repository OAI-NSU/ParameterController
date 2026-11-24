import asyncio
import os
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from beanie import Document, init_beanie
from bytes_parser import Frame, Row
from dotenv import load_dotenv
from loguru import logger
from pydantic import Field
from pymongo import AsyncMongoClient
from sat_frames import frames_map_0x02

from parameter_controller.L0.config import get_qualifier, load_config, nested_dict
from parameter_controller.L0.models import L0_History, L0_Parameter


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

    async def init_db(self):
        await init_beanie(database=self.db,
                          document_models=[L0_ParameterDoc, L0_HistoryDoc])
        await self.load_config()

    async def load_config(self):
        for param in load_config(L0_ParameterDoc, frames_map_0x02, self.params_dict):
            filter: dict = {
                'sat_id': param.sat_id,
                'dev_id': param.dev_id,
                'frame_type': param.frame_type,
                'field_label': param.field_label
            }
            if param.bitfield:
                filter['bitfield'] = param.bitfield

            if not await self.params.count_documents(filter):
                await L0_ParameterDoc.insert_one(param)


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
        field_label = params
        filter: dict = {
            'sat_id': sat_id,
            'dev_id': dev_id,
            'frame_type': frame_type,
        }
        async for model in self.params.find(filter):
            model.last_user = username
            model.last_gs = gs_label
            model.last_session = timestamp
            model.raw


        about_to_notify: list[L0_TrackedField] = tmi.add_tmi(hex_data, timestamp, frame)
        tmi.update_tracked_fields_history(timestamp, frame)
        qualifier: int = int.from_bytes(bytes_data[2:6], 'little')
        for field in about_to_notify:
            if field.status and field.status.priority == 3:
                sat.alarms.pending.setdefault(qualifier, field.status)
        return about_to_notify



async def db_test():
    controller = DB_ParamController()
    await controller.init_db()
    await controller.load_config()

if __name__ == '__main__':
    asyncio.run(db_test())