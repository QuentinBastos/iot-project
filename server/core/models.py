from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass(frozen=True)
class SensorReading:
    """Legacy : une ligne = une valeur d'un capteur.

    Conservee uniquement pour la decodage des trames CSV "<ctrl>,<sensor>,<value>"
    transmises par des outils externes. En interne, tout est converti en
    ``SensorSnapshot`` avant stockage.
    """
    controller_id: str
    sensor_id: str
    value: float
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class SensorSnapshot:
    """Un instantane multi-capteurs d'un micro:bit.

    Chaque champ capteur est optionnel : une source (ex: legacy CSV) peut ne
    transporter qu'une seule valeur, on stocke alors une ligne ou un seul champ
    est renseigne et les autres sont NULL en base.
    """
    controller_id: str
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    luminosity: Optional[float] = None
    pressure: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class ConfigCommand:
    controller_id: str
    display_order: str

@dataclass(frozen=True)
class User:
    passkey_hash: str
    created_at: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class UserSensor:
    passkey_hash: str
    sensor_id: str
