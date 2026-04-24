from dataclasses import dataclass
from typing import Optional
from core.models import SensorReading, ConfigCommand

@dataclass(frozen=True)
class AppEvent:
    """Base class for all application events."""
    pass

@dataclass(frozen=True)
class RegisterUserEvent(AppEvent):
    passkey: str

@dataclass(frozen=True)
class AddSensorEvent(AppEvent):
    passkey: str
    sensor_id: str
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class RemoveSensorEvent(AppEvent):
    passkey: str
    sensor_id: str
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class DataRequestEvent(AppEvent):
    passkey: str
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class ConfigCommandEvent(AppEvent):
    config: ConfigCommand

@dataclass(frozen=True)
class SensorReadingEvent(AppEvent):
    reading: SensorReading
