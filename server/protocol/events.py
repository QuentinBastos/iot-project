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
class AddControllerEvent(AppEvent):
    passkey: str
    controller_id: str
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class RemoveControllerEvent(AppEvent):
    """Supprime le lien passkey<->controller ET toutes ses donnees stockees."""
    passkey: str
    controller_id: str
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class ListControllersEvent(AppEvent):
    passkey: str

@dataclass(frozen=True)
class DataRequestEvent(AppEvent):
    passkey: str
    controller_id: Optional[str] = None
    timestamp: Optional[int] = None

@dataclass(frozen=True)
class ConfigCommandEvent(AppEvent):
    config: ConfigCommand

@dataclass(frozen=True)
class SensorReadingEvent(AppEvent):
    reading: SensorReading
