from uuid import UUID, uuid4

from beanie import Document
from pydantic import Field

from parameter_controller.L0.models import History, Parameter, PendingEvent, TMI_State


class ParameterDoc(Parameter, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]


class HistoryDoc(History, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]


class PendingDoc(PendingEvent, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]


class TMI_StateDoc(TMI_State, Document):
    id: UUID = Field(default_factory=uuid4, alias='_id')  # pyright: ignore[reportIncompatibleVariableOverride]