"""Kiosk hardware events: ESP32 -> backend -> Flutter (Phase 7, Decision 34).

POST /hardware/events                   the ESP32 reports a button press or its audio status
GET  /kiosks/{kiosk_id}/events?after=N  the Flutter app picks up new events (polls about twice a second)

Use ?after=-1 to learn the current position without receiving old events (when the app starts).
"""

from fastapi import APIRouter, Depends, Query

from app.dependencies import get_hardware_service
from app.models.hardware_models import HardwareEventOut, HardwareEventRequest, HardwareEventsResponse
from app.services.hardware_service import HardwareEventService

router = APIRouter(tags=["hardware"])


@router.post("/hardware/events", status_code=201, response_model=HardwareEventOut)
def report_event(
    request: HardwareEventRequest,
    events: HardwareEventService = Depends(get_hardware_service),
) -> HardwareEventOut:
    event = events.add(request.kiosk_id, button=request.button, status=request.status)
    return HardwareEventOut(**event.__dict__)


@router.get("/kiosks/{kiosk_id}/events", response_model=HardwareEventsResponse)
def list_events(
    kiosk_id: str,
    after: int = Query(-1, ge=-1),
    events: HardwareEventService = Depends(get_hardware_service),
) -> HardwareEventsResponse:
    latest = events.latest_seq(kiosk_id)
    found = [] if after < 0 else events.after(kiosk_id, after)
    return HardwareEventsResponse(
        kiosk_id=kiosk_id,
        latest_seq=latest,
        events=[HardwareEventOut(**e.__dict__) for e in found],
    )
