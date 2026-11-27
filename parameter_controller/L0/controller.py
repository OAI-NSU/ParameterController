import asyncio
import os
from copy import copy
from datetime import datetime

from beanie import init_beanie
from bytes_parser import Frame, Notification, Row, BitFlag, BitField
from dotenv import load_dotenv
from loguru import logger
from pymongo import AsyncMongoClient
from sat_frames import frames_map_0x02

from parameter_controller.L0.config import get_qualifier, load_config, nested_dict
from parameter_controller.L0.db_documents import HistoryDoc, ParameterDoc, TMI_StateDoc
from parameter_controller.L0.models import EventLevel


class DB_ParamController:
    def __init__(self) -> None:
        load_dotenv()
        self.client = AsyncMongoClient(os.environ['DATABASE_URL'])
        self.db = self.client['L0']
        self.params = self.db['ParameterDoc']
        self.history = self.db['HistoryDoc']
        self.pending = self.db['PendingDoc']
        self.tmi = self.db['TMI_StateDoc']
        self.compare_onboard_time = False
        self.params_dict = nested_dict()
        self.relaxation_time = 1000

    async def init_db(self):
        await init_beanie(database=self.db,
                          document_models=[ParameterDoc, HistoryDoc])
        await self.load_config()

    async def load_config(self):
        for param in load_config(frames_map_0x02, self.params_dict):
            model = ParameterDoc(**param)
            filter: dict = {
                'sat_id': model.sat_id,
                'dev_id': model.dev_id,
                'frame_type': model.frame_type,
                'field_label': model.field_label
            }
            if model.bitfield:
                filter['bitfield'] = model.bitfield

            if not await self.params.count_documents(filter):
                await ParameterDoc.insert_one(model)


    async def on_received_data(self, hex_data: str, timestamp: datetime):
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
        filter: dict = {
            'sat_id': sat_id,
            'dev_id': dev_id,
            'frame_type': frame_type,
        }
        model_dict = await self.tmi.find_one(filter)
        if model_dict:
            model = TMI_StateDoc.model_validate(model_dict)
            model.hex_data = hex_data
            model.last_update = timestamp
            await model.save()

        params = self.params_dict[sat_id][dev_id][frame_type]
        errors, warnings = frame.get_failed_params(params)
        notifications: list[Notification] = [*errors, *warnings]
        about_to_notify: list[ParameterDoc] = []
        await self.pending.find(filter).to_list()

        async for model, n in self.request_params(notifications, filter):
            if not model.bitfield:
                field = n.row
            else:
                field = n.row._bit_fields_kwarg[model.bitfield]
            model.prev_level = model.level
            model.level = get_level(field)
            if model.level > model.prev_level:

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
                        yield ParameterDoc.model_validate(model_dict), n
            else:
                model_dict = await self.params.find_one(new_filter)
                if model_dict:
                    yield ParameterDoc.model_validate(model_dict), n

def get_level(field: Row | BitFlag | BitField) -> int:
    if isinstance(field, Row):
        if not field._is_valid:
            return EventLevel.Error.value
        if field._is_warn:
            return EventLevel.Warning.value
        return EventLevel.Normalized.value
    if not field.is_valid:
        return EventLevel.Error.value
    return EventLevel.Normalized.value

async def db_test():
    controller = DB_ParamController()
    await controller.init_db()
    await controller.load_config()

if __name__ == '__main__':
    asyncio.run(db_test())