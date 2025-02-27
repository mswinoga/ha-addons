"""
Sensor entity implementation for Modbus-MQTT gateway.
Handles register data (numeric values).
"""
import logging
from typing import Any, Dict, List, Optional, Union

from ..interfaces import GatewayInterface, ModbusData
from ..models import TYPE_REGISTER
from .base_entity import BaseEntity

logger = logging.getLogger('entity.sensor')


class SensorEntity(BaseEntity):
    """
    Sensor entity.
    Handles processing numeric data from Modbus registers.
    """
    
    def initialize(self) -> None:
        """
        Initializes sensor entity.
        Validates configuration and sets up MQTT subscriptions for writable entities.
        """
        super().initialize()
        
        if not self.entity_name:
            return
            
        # Validate configuration
        if self.modbus_class.data_type != TYPE_REGISTER:
            raise ValueError(f"SensorEntity only supports register data format, received: {self.modbus_class.data_type}")
            
        if self.modbus_class.data_size > 2:
            raise ValueError(f"SensorEntity supports maximum 2 registers, received: {self.modbus_class.data_size}")
        
        # If entity is not read-only, set up subscription for writing
        if not self.modbus_class.read_only:
            self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)
    
    def on_mqtt_set(self, msg: Any) -> None:
        """
        Handles MQTT message with value to write.
        
        Args:
            msg: MQTT message with value
        """
        payload = msg.payload.decode('utf-8')
        
        try:
            # Convert payload to integer
            value = int(payload)
            
            # Encode value to Modbus registers format
            if self.modbus_class.data_size == 1:
                encoded = [value]
            else:
                # Write 32-bit value as two 16-bit registers
                encoded = [value & 0xFFFF, (value >> 16) & 0xFFFF]
                
            # Write to Modbus device
            logger.info(f"Writing value {value} to register {self.modbus_write_address}")
            self.gateway.modbus_write_registers(self.modbus_write_address, encoded)
            
        except ValueError as e:
            logger.warning(f"Invalid value for SensorEntity: {payload} - {e}")
        except Exception as e:
            logger.error(f"Error writing to SensorEntity: {e}")
    
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> Optional[int]:
        """
        Processes register data from Modbus and updates entity state.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus (list of register values)
            
        Returns:
            Previous entity state
        """
        old_val = self.state
        
        # Decode value from Modbus registers
        if self.modbus_class.data_size == 1:
            # Single 16-bit register
            value = data[0]
        else:
            # Two registers forming 32-bit value
            value = (data[1] << 16) + data[0]
        
        # If value has changed, publish new value
        if value != self.state:
            self.gateway.mqtt_publish(
                self.mqtt_topic(self.TOPIC_STATE),
                value
            )
            logger.debug(f"Sensor {self.entity_name}: value changed from {old_val} to {value}")
            self.state = value
        
        return old_val
    
    @property
    def class_component(self) -> str:
        """Home Assistant component for sensor."""
        return "sensor"
    
    def discovery_payload(self) -> Dict[str, Any]:
        """
        Generates payload for MQTT discovery specific to sensor.
        
        Returns:
            Dictionary with configuration data for MQTT discovery
        """
        payload = super().discovery_payload()
        
        # Add sensor-specific attributes if available
        # e.g. unit_of_measurement, device_class, etc.
        entity_def = self.entity_def.to_dict()
        for attr in ["unit_of_measurement", "device_class", "value_template", "state_class"]:
            if attr in entity_def:
                payload[attr] = entity_def[attr]
        
        return payload