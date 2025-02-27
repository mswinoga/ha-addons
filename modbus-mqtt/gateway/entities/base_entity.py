"""
Base entity implementation for Modbus-MQTT gateway.
"""
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from ..interfaces import EntityInterface, GatewayInterface, ModbusData
from ..models import ModbusClassConfig, EntityDefinition

logger = logging.getLogger('entity')


class BaseEntity(EntityInterface):
    """
    Base class for all entities in the system.
    Implements common functionality for all entities.
    """
    # Constants for MQTT topics
    TOPIC_BASE = "plc/{e.modbus_class.name}/{e.discovery_uid}"
    TOPIC_STATE = "state"
    TOPIC_SET = "set"
    
    def __init__(
        self,
        gateway: GatewayInterface,
        entity_def: Dict[str, str],
        modbus_class: ModbusClassConfig,
        modbus_idx: int,
        discovery_prefix: str = "homeassistant",
        availability_topic: str = "plc/availability"
    ):
        """
        Initializes a new entity.
        
        Args:
            gateway: Gateway interface
            entity_def: Entity definition
            modbus_class: Modbus class configuration
            modbus_idx: Index in Modbus block
            discovery_prefix: Prefix for discovery topics (default "homeassistant")
            availability_topic: Availability topic (default "plc/availability")
        """
        # Do not process undefined entities
        if not entity_def or not entity_def.get("name"):
            self.entity_name = None
            self.discovery_uid = None
            return
            
        # Initialize basic attributes
        self.gateway = gateway
        self.entity_def = EntityDefinition.from_dict(entity_def)
        self.modbus_class = modbus_class
        self.modbus_idx = modbus_idx
        self.discovery_prefix = discovery_prefix
        self.availability_topic = availability_topic
        
        # Process name and entity identifier
        self.entity_name = self.entity_def.name
        self.discovery_uid = self.entity_def.discovery_uid
        
        # HA component
        self.component = self.entity_def.component or modbus_class.defaults.get("component") or self.class_component
        
        # Modbus addresses
        self.modbus_read_address = self.modbus_idx + self.modbus_class.read_offset
        self.modbus_write_address = (self.modbus_idx * self.modbus_class.data_size) + self.modbus_class.write_offset
        
        # MQTT topics
        self.mqtt_topic_base = self.TOPIC_BASE.format(e=self)
        self.discovery_topic = f"{self.discovery_prefix}/{self.component}/plc/{self.discovery_uid}/config" if self.component else None
        
        # Entity state
        self.reset()
        
        # Initialize entity
        if self.entity_name:
            self.initialize()
    
    def reset(self) -> None:
        """Resets entity state to default values."""
        self.state = None
    
    def initialize(self) -> None:
        """
        Initializes entity in the system.
        Publishes discovery information to MQTT if configured.
        """
        if not self.entity_name:
            return
            
        # Check configuration validity
        data_type = self.modbus_class.data_type
        if data_type not in ["register", "coil"]:
            raise ValueError(f"Unsupported data type: {data_type}")
            
        # Send discovery information to MQTT
        if self.discovery_topic:
            payload = {}
            # Add default values from Modbus class
            payload.update(self.modbus_class.defaults)
            # Add entity definition
            payload.update(self.entity_def.to_dict())
            # Add discovery information
            payload.update(self.discovery_payload())
            
            # Publish discovery only for valid entities
            self.gateway.mqtt_publish(
                topic=self.discovery_topic,
                payload=json.dumps({k: v for k, v in payload.items() if v is not None}),
                retain=True
            )
    
    @property
    def class_component(self) -> Optional[str]:
        """
        Default Home Assistant component implemented by this entity class.
        Should be overridden by subclasses.
        """
        return None
    
    def discovery_payload(self) -> Dict[str, Any]:
        """
        Generates basic payload for MQTT discovery.
        
        Returns:
            Dictionary with configuration data for MQTT discovery
        """
        return {
            "~": self.mqtt_topic_base,
            "name": self.entity_name,
            "unique_id": self.discovery_uid,
            "availability_topic": self.availability_topic,
            "command_topic": f"~/{self.TOPIC_SET}",
            "state_topic": f"~/{self.TOPIC_STATE}",
        }
    
    def mqtt_topic(self, *args: str) -> str:
        """
        Generates full MQTT topic for entity.
        
        Args:
            *args: Topic segments to add
            
        Returns:
            Full MQTT topic
        """
        topic = "/".join([self.mqtt_topic_base] + list(args))
        logger.debug(f"MQTT topic: {topic}")
        return topic
    
    def on_modbus_data(self, timestamp: int, data: ModbusData) -> None:
        """
        Processes data from Modbus.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus
        """
        # Skip entities without names
        if not self.entity_name:
            return
            
        # Check data validity
        if len(data) != self.modbus_class.data_size:
            raise ValueError(f"Invalid data length: {len(data)}, expected: {self.modbus_class.data_size}")
            
        # Process data
        self.process_modbus_data(timestamp, data)
    
    @abstractmethod
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> Any:
        """
        Processes data from Modbus and updates entity state.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus
            
        Returns:
            Previous entity state or other value depending on implementation
        """
        pass