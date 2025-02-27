"""
Models - data classes used in the Modbus-MQTT gateway system
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any
import re
import json
from unidecode import unidecode


# Modbus data types
TYPE_REGISTER = "register"
TYPE_COIL = "coil"


@dataclass
class DeviceInfo:
    """Device information"""
    identifiers: str
    name: str
    model: str
    manufacturer: str

    def to_dict(self) -> Dict[str, str]:
        """Converts to dictionary for HA discovery"""
        return {
            "identifiers": [self.identifiers],
            "name": self.name,
            "model": self.model,
            "manufacturer": self.manufacturer
        }


@dataclass
class ModbusClassConfig:
    """Modbus class configuration"""
    name: str
    data_type: str = TYPE_COIL
    data_size: int = 1
    read_offset: int = 0
    write_offset: int = 0
    read_only: bool = True
    defaults: Dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return (f"ModbusClassConfig(name={self.name}, data_type={self.data_type}, "
                f"data_size={self.data_size}, read_offset={self.read_offset}, "
                f"write_offset={self.write_offset}, read_only={self.read_only}, "
                f"defaults={self.defaults})")


@dataclass
class EntityDefinition:
    """HA entity definition"""
    name: Optional[str] = None
    component: Optional[str] = None
    device_class: Optional[str] = None
    payload_on: Optional[str] = None
    payload_off: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'EntityDefinition':
        """Creates an instance from a dictionary"""
        return cls(
            name=data.get("name"),
            component=data.get("component"),
            device_class=data.get("device_class"),
            payload_on=data.get("payload_on"),
            payload_off=data.get("payload_off")
        )
    
    def to_dict(self) -> Dict[str, str]:
        """Converts to a dictionary for discovery"""
        return {k: v for k, v in self.__dict__.items() if v is not None}
    
    @property
    def is_valid(self) -> bool:
        """Checks if the entity has a name"""
        return self.name is not None and self.name != ""
    
    @property
    def discovery_uid(self) -> Optional[str]:
        """Generates a unique identifier for HA discovery"""
        if not self.name:
            return None
        uid = unidecode(self.name.lower())
        return re.sub(r"\s+", "_", uid)


@dataclass
class EntitySetConfig:
    """Entity set configuration"""
    set_id: str
    entity_type: str
    entity_count: int
    entities: List[Dict[str, str]]
    data_type: str
    defaults: str = ""
    data_size: int = 1
    read_only: bool = True
    read_offset: int = 0
    write_offset: int = 0
    poll_delay_ms: int = 250

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EntitySetConfig':
        """Creates an instance from a configuration dictionary"""
        return cls(
            set_id=data.get("set_id", ""),
            entity_type=data.get("entity_type", ""),
            entity_count=data.get("entity_count", 0),
            entities=data.get("entities", []),
            data_type=data.get("data_type", TYPE_COIL),
            defaults=data.get("defaults", ""),
            data_size=data.get("data_size", 1),
            read_only=data.get("read_only", True),
            read_offset=data.get("read_offset", 0),
            write_offset=data.get("write_offset", 0),
            poll_delay_ms=data.get("poll_delay_ms", 250)
        )


@dataclass
class GatewayConfig:
    """Main gateway configuration"""
    modbus_host: str
    modbus_port: int
    device: DeviceInfo
    entity_sets: List[EntitySetConfig]
    discovery_prefix: str = "homeassistant"
    mqtt_availability_topic: str = "plc/availability"
    mqtt_client_name: str = "modbus-gateway"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GatewayConfig':
        """Creates an instance from a configuration dictionary"""
        device_info = DeviceInfo(**data.get("device", {}))
        entity_sets = [
            EntitySetConfig.from_dict(entity_set)
            for entity_set in data.get("entity_sets", [])
        ]
        
        return cls(
            modbus_host=data.get("modbus_host", "localhost"),
            modbus_port=data.get("modbus_port", 502),
            device=device_info,
            entity_sets=entity_sets,
            discovery_prefix=data.get("discovery_prefix", "homeassistant"),
            mqtt_availability_topic=data.get("mqtt_availability_topic", "plc/availability"),
            mqtt_client_name=data.get("mqtt_client_name", "modbus-gateway")
        )