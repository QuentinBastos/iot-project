from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List

@dataclass(frozen=True)
class SensorReading:
    controller_id: str
    sensor_id: str
    value: float
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
