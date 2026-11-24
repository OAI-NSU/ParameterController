import asyncio
import os
from datetime import datetime
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from beanie import Document, init_beanie
from dotenv import load_dotenv
from pydantic import Field
from pymongo import AsyncMongoClient
from sat_frames import frames_map_0x02

from parameter_controller.controller import ParamController
from parameter_controller.L0.config import L0_MAP_CONFIG
from parameter_controller.models import L0_TrackedField, SatModel


class SatModelDoc(SatModel, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]

SAT_MODEL_BEANIE = TypeVar("SAT_MODEL_BEANIE", bound=SatModelDoc)

class SatModelDB(Generic[SAT_MODEL_BEANIE]):
    def __init__(self, model: type[SAT_MODEL_BEANIE]):
        self.model: type[SAT_MODEL_BEANIE] = model


class DB_ParamController(ParamController):
    async def received_data(self, hex_data: str, timestamp: datetime,
                            username: str, gs_label: str) -> list[L0_TrackedField]:
        about_to_notify = super().on_received_data(hex_data, timestamp, username, gs_label)
        return about_to_notify

async def db_test():
    load_dotenv()
    client = AsyncMongoClient(os.environ['DATABASE_URL'])
    db = client[os.environ['DB_NAME']]
    await init_beanie(database=db,
                      document_models=[SatModelDoc])
    controller: ParamController = await create_db_param_controller(db)
    # controller.on_received_data()

async def create_db_param_controller(db) -> ParamController:
    controller = ParamController()
    sat_model_collection = db['SatModelDoc']
    amount: int = await sat_model_collection.count_documents({})
    if not amount:
        controller.load_config(L0_MAP_CONFIG, frames_map_0x02)
        for sat_state in controller.state.values():
            await SatModelDoc.insert(SatModelDoc.model_validate(sat_state.model_dump()))
    else:
        async for doc in sat_model_collection.find():
            model: SatModel = SatModel.model_validate(doc)
            controller.state[model.sat_id] = model
    return controller
if __name__ == '__main__':
    asyncio.run(db_test())