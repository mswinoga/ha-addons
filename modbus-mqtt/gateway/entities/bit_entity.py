"""
Bit entity implementations for Modbus-MQTT gateway.
Contains entities operating on single bits (Modbus coils).
"""
import logging
from typing import Any, Dict, List, Optional, Union

from ..interfaces import GatewayInterface, ModbusData
from .base_entity import BaseEntity

logger = logging.getLogger('entity.bit')


class BitEntity(BaseEntity):
    """
    Base class for bit entities.
    Handles processing data in bit/coil format.
    """
    
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> bool:
        """
        Processes bit data from Modbus and updates entity state.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus (list of bit values)
            
        Returns:
            Previous entity state
        """
        # Store current value
        old_val = self.state
        new_val = bool(data[0])
        
        # If state has changed, publish new value
        if new_val != self.state:
            # Retain MQTT messages for outputs (with write operation supported)
            retain = self.modbus_class.read_only
            value = "ON" if new_val else "OFF"
            
            self.gateway.mqtt_publish(
                self.mqtt_topic(self.TOPIC_STATE),
                value,
                retain=retain
            )
            self.state = new_val
            
            logger.debug(f"Entity {self.entity_name}: state changed from {old_val} to {new_val}")
        
        # Return previous value
        return old_val


class BinarySensorEntity(BitEntity):
    """
    Binary sensor entity.
    Represents a sensor with two states (e.g., motion sensor, contact sensor).
    """
    
    @property
    def class_component(self) -> str:
        """Home Assistant component for binary sensor."""
        return "binary_sensor"


class ButtonEntity(BitEntity):
    """
    Button entity.
    Handles click and hold button events.
    """
    # Constants for button event detection
    CLICK_PAUSE_MAX = 250  # Maximum pause time between clicks (ms)
    LONG_PRESS_MIN = 400   # Minimum time for long press (ms)
    
    def reset(self) -> None:
        """Resets button entity state."""
        super().reset()
        
        # Additional state parameters for button
        self.click_count = 0
        self.hold = False
        self.timestamp = 0
    
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> bool:
        """
        Processes button data from Modbus.
        Detects click and long-press events.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus
            
        Returns:
            Previous entity state
        """
        # Process basic bit data
        old_val = super().process_modbus_data(timestamp, data)
        
        # Button event detection implementation
        # Based on frequent calls to process_modbus_data
        if old_val != self.state:
            # State change
            if self.state is True:  # Button press
                self.click_count += 1
            elif self.state is False:  # Button release
                if self.hold is True:
                    # Release after long press
                    self.gateway.mqtt_publish(
                        self.mqtt_topic("long"),
                        "RELEASE"
                    )
                    self.hold = False
                    self.click_count = 0
            
            # Update timestamp for event detection
            self.timestamp = timestamp
            
        elif self.state is True and self.hold is False:
            # Possible long press
            delta = timestamp - self.timestamp
            if delta > self.LONG_PRESS_MIN:
                # Long press detected
                self.gateway.mqtt_publish(
                    self.mqtt_topic('long'),
                    self.click_count
                )
                self.hold = True
                logger.debug(f"Button {self.entity_name}: long press, click count: {self.click_count}")
                
        elif self.state is False and self.click_count > 0:
            # Possible end of click sequence
            delta = timestamp - self.timestamp
            if delta > self.CLICK_PAUSE_MAX:
                # Click sequence detected
                self.gateway.mqtt_publish(
                    self.mqtt_topic("click"),
                    self.click_count
                )
                logger.debug(f"Button {self.entity_name}: detected {self.click_count} clicks")
                self.click_count = 0
        
        return old_val


class RelayEntity(BitEntity):
    """
    Relay entity.
    Handles relay control (on/off/toggle).
    """
    
    def initialize(self) -> None:
        """Initializes relay entity and subscribes to MQTT topics."""
        super().initialize()
        
        if not self.entity_name:
            return
            
        # Subscribe to topic to receive control commands
        self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)
    
    def on_mqtt_set(self, msg: Any) -> None:
        """
        Handles MQTT message with control command.
        
        Args:
            msg: MQTT message with command
        """
        payload = msg.payload.decode('utf-8')
        upper_payload = str(payload).upper()
        value = None
        
        # Command interpretation
        if upper_payload in ("ON", "1"):
            value = True
        elif upper_payload in ("OFF", "0"):
            value = False
        elif upper_payload == "TOGGLE":
            value = not self.state
        
        # Command execution
        if value is not None:
            logger.info(f"{msg.topic}: {msg.payload} --> modbus({self.modbus_write_address}) = {value}")
            self.gateway.modbus_write_coils(self.modbus_write_address, value)
        else:
            logger.warning(f"{msg.topic}: unrecognized command {msg.payload}")
    
    @property
    def class_component(self) -> str:
        """Home Assistant component for relay."""
        return "switch"