from dataclasses import dataclass

from app.ports.appointments_gateway import AppointmentItem


@dataclass(frozen=True, slots=True)
class AppointmentSelection:
    appointments: tuple[AppointmentItem, ...]
