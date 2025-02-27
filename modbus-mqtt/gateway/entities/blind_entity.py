"""
Blind entity implementation for Modbus-MQTT gateway.
Handles control of blinds/covers.
"""
import json
import logging
from typing import Any, Dict, List, Optional, Union

from ..interfaces import GatewayInterface, ModbusData
from ..models import TYPE_REGISTER
from .base_entity import BaseEntity

logger = logging.getLogger('entity.blind')


class BlindEntity(BaseEntity):
    """
    Blind/cover entity.
    Handles control of blinds with positioning functions.
    """
    # Blind states
    STATE_OPENING = "opening"
    STATE_CLOSING = "closing"
    STATE_OPEN = "open"
    STATE_CLOSED = "closed"
    STATE_STOPPED = "stopped"
    
    # Commands
    CMD_OPEN = "OPEN"
    CMD_CLOSE = "CLOSE"
    CMD_STOP = "STOP"
    
    # Status flags
    FLAG_COMMAND = 0x80  # Bit 7 - command flag (1 = command, 0 = stop)
    
    def reset(self) -> None:
        """Resets blind entity state to default values."""
        super().reset()
        
        # Blind state parameters
        self.position = None  # Current position (0-100%)
        self.target = 0       # Target position
        self.time_up = None   # Time to raise
        self.time_down = None # Time to lower
        self.state = self.STATE_STOPPED  # Blind state
    
    def initialize(self) -> None:
        """
        Initializes blind entity.
        Validates configuration and sets up MQTT subscriptions.
        """
        super().initialize()
        
        if not self.entity_name:
            return
            
        # Validate configuration
        if self.modbus_class.data_type != TYPE_REGISTER:
            raise ValueError(f"BlindEntity only supports register data format, received: {self.modbus_class.data_type}")
            
        if self.modbus_class.data_size != 2:
            raise ValueError(f"BlindEntity requires exactly 2 registers, received: {self.modbus_class.data_size}")
        
        # Subscribe to MQTT topics
        self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)
        self.gateway.mqtt_subscribe(self.mqtt_topic("config"), self.on_mqtt_config)
    
    def on_mqtt_set(self, msg: Any) -> None:
        """
        Handles MQTT message with blind command.
        
        Args:
            msg: MQTT message with command
        """
        try:
            payload = msg.payload.decode('utf-8')
            
            # Parse command value
            if payload.isdigit() or (payload.startswith('-') and payload[1:].isdigit()):
                # Numeric command (position)
                value = int(payload)
                # Limit range to 0-100%
                value = max(0, min(100, value))
                # Set command flag (bit 7)
                value = value | self.FLAG_COMMAND
                
            elif payload.upper() == self.CMD_OPEN:
                # Open command (position 100%)
                value = 100 | self.FLAG_COMMAND
                
            elif payload.upper() == self.CMD_CLOSE:
                # Close command (position 0%)
                value = 0 | self.FLAG_COMMAND
                
            elif payload.upper() == self.CMD_STOP:
                # Stop command (clear command flag)
                value = 0 & ~self.FLAG_COMMAND
                
            else:
                logger.warning(f"Unsupported command for blind: {payload}")
                return
            
            # Send command to Modbus device
            logger.info(f"Sending command to blind {self.entity_name}: {value}")
            self.gateway.modbus_write_registers(self.modbus_write_address, value)
            
        except Exception as e:
            logger.error(f"Error processing blind command: {str(e)}")
    
    def on_mqtt_config(self, msg: Any) -> None:
        """
        Handles MQTT message with blind configuration.
        Allows configuration of raising/lowering times.
        
        Args:
            msg: MQTT message with configuration
        """
        try:
            payload = msg.payload.decode('utf-8')
            config = json.loads(payload)
            
            # Get configuration values
            time_up = config.get("time_up")
            time_down = config.get("time_down")
            
            if time_up is not None or time_down is not None:
                # Prepare configuration value for times
                if time_up is not None and time_down is not None:
                    # Both times are provided
                    time_config = (time_up << 8) + time_down
                elif time_up is not None:
                    # Only raising time is provided
                    if self.time_down is None:
                        logger.warning("Cannot configure only raising time - missing lowering time")
                        return
                    time_config = (time_up << 8) + self.time_down
                else:
                    # Only lowering time is provided
                    if self.time_up is None:
                        logger.warning("Cannot configure only lowering time - missing raising time")
                        return
                    time_config = (self.time_up << 8) + time_down
                
                # Write configuration to Modbus device
                logger.info(f"Writing time configuration for blind {self.entity_name}: up={time_up}, down={time_down}")
                self.gateway.modbus_write_registers(self.modbus_write_address + 1, time_config)
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON format in blind configuration: {msg.payload}")
        except Exception as e:
            logger.error(f"Error configuring blind: {str(e)}")
    
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> None:
        """
        Processes blind data from Modbus and updates entity state.
        
        Args:
            timestamp: Timestamp in milliseconds
            data: Data read from Modbus (list of register values)
        """
        def publish_state(topic: str, value: Any) -> None:
            """Helper function to publish entity state."""
            self.gateway.mqtt_publish(self.mqtt_topic(topic), value)
        
        # Decode data from Modbus registers
        # Register 0: position and command flag
        if data[0] & self.FLAG_COMMAND == 0:  # Bit 7 = 0 -> stop
            new_target = None
        else:
            new_target = data[0] & 0x7F  # Target position (0-100%)
        
        # Current position is the upper byte of first register
        new_position = (data[0] & 0xFF00) >> 8
        
        # Register 1: raising/lowering times
        new_time_up = (data[1] & 0xFF00) >> 8
        new_time_down = data[1] & 0x00FF
        
        # Check if state update is needed
        state_check_needed = False
        
        # Update position if changed
        if self.position != new_position:
            publish_state('position', new_position)
            state_check_needed = True
            logger.debug(f"Blind {self.entity_name}: position changed from {self.position} to {new_position}")
            self.position = new_position
        
        # Update target if changed
        if self.target != new_target:
            publish_state("target", new_target)
            state_check_needed = True
            logger.debug(f"Blind {self.entity_name}: target changed from {self.target} to {new_target}")
            self.target = new_target
        
        # Update raising time if changed
        if self.time_up != new_time_up:
            publish_state("time_up", new_time_up)
            logger.debug(f"Blind {self.entity_name}: raising time changed to {new_time_up}")
            self.time_up = new_time_up
        
        # Update lowering time if changed
        if self.time_down != new_time_down:
            publish_state("time_down", new_time_down)
            logger.debug(f"Blind {self.entity_name}: lowering time changed to {new_time_down}")
            self.time_down = new_time_down
        
        # If state update is needed and we know the position
        if state_check_needed and self.position is not None:
            new_state = self.state
            
            # Determine new state based on position and target
            if self.target is None:
                # No target = stopped
                if self.state != self.STATE_STOPPED:
                    new_state = self.STATE_STOPPED
            elif self.position < self.target:
                # Position less than target = opening
                if self.state != self.STATE_OPENING:
                    new_state = self.STATE_OPENING
            elif self.position > self.target:
                # Position greater than target = closing
                if self.state != self.STATE_CLOSING:
                    new_state = self.STATE_CLOSING
            elif self.position == self.target and self.position == 0:
                # Position = target = 0 = closed
                if self.state != self.STATE_CLOSED:
                    new_state = self.STATE_CLOSED
            elif self.position == self.target and self.position == 100:
                # Position = target = 100 = open
                if self.state != self.STATE_OPEN:
                    new_state = self.STATE_OPEN
            elif self.position == self.target:
                # Position = target (not 0/100) = stopped
                new_state = self.STATE_STOPPED
            
            # If state has changed, publish it
            if self.state != new_state:
                self.state = new_state
                publish_state('state', self.state)
                logger.info(f"Blind {self.entity_name}: state changed to {self.state}")
    
    def discovery_payload(self) -> Dict[str, Any]:
        """
        Generates payload for MQTT discovery specific to blind.
        
        Returns:
            Dictionary with configuration data for MQTT discovery
        """
        payload = super().discovery_payload()
        
        # Add blind-specific attributes
        payload.update({
            "set_position_topic": f"~/{self.TOPIC_SET}",
            "position_topic": "~/position",
            "position_open": 100,
            "position_closed": 0,
        })
        
        return payload
    
    @property
    def class_component(self) -> str:
        """Home Assistant component for blind."""
        return "cover"