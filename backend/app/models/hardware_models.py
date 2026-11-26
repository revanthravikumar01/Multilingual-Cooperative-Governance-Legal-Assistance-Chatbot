"""Request and response bodies for kiosk hardware events (Phase 7)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

# The six physical buttons (handover, "Physical Buttons"). Do not change without discussing it first.
Button = Literal["language", "confirm", "back", "repeat", "mic", "accessibility"]
# What the ESP32's microphone/speaker is doing, so the app can show it.
DeviceStatus = Literal["recording", "processing", "speaking", "idle"]


class HardwareEventRequest(BaseModel):
    kiosk_id: str = Field(min_length=1, max_length=64)
    button: Button | None = None
    status: DeviceStatus | None = None

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.button is None) == (self.status is None):
            raise ValueError("Send either 'button' or 'status'.")
        return self


class HardwareEventOut(BaseModel):
    seq: int
    button: Button | None = None
    status: DeviceStatus | None = None
    created_at: datetime


class HardwareEventsResponse(BaseModel):
    kiosk_id: str
    latest_seq: int  # poll again with ?after=<latest_seq>
    events: list[HardwareEventOut]
