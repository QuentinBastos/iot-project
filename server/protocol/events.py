from dataclasses import dataclass
from typing import Optional
from core.models import SensorReading, SensorSnapshot, ConfigCommand

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
    """Une seule valeur (trame CSV legacy '<ctrl>,<sensor>,<value>').

    Le service la convertit en snapshot a un seul champ avant stockage.
    """
    reading: SensorReading


@dataclass(frozen=True)
class SensorSnapshotEvent(AppEvent):
    """Un instantane complet (pipe payload ou JSON multi-capteurs)."""
    snapshot: SensorSnapshot


@dataclass(frozen=True)
class HistoryRequestEvent(AppEvent):
    """Demande d'historique pour un micro:bit particulier.

    ``limit`` borne le nombre de snapshots retournes (defaut 50, max 500).
    """
    passkey: str
    controller_id: str
    limit: int = 50
