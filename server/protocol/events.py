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
    """Demande d'historique aggrege pour un micro:bit particulier.

    Retourne un resume min/max/moyenne par jour sur les ``days`` derniers
    jours (defaut 7, clampe 1..365 par le repository).
    """
    passkey: str
    controller_id: str
    days: int = 7
