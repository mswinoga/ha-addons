"""
Interfaces for Modbus-MQTT gateway components.
Defines abstract classes and protocols for different parts of the system.
"""
from abc import ABC, abstractmethod
from typing import Any, Callable, List, Optional, TypeVar, Union

# Data types for type annotations
T = TypeVar('T')
ModbusData = Union[List[bool], List[int]]
MQTTMessage = Any  # MQTT message type


class ModbusClientInterface(ABC):
    """Interface for Modbus client handling requests to Modbus devices."""
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establishes connection with Modbus server.
        
        Returns:
            True if connection was established, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Checks if client is connected to Modbus server.
        
        Returns:
            True if client is connected, False otherwise
        """
        pass
    
    @abstractmethod
    def read_coils(self, address: int, count: int) -> List[bool]:
        """
        Reads coils from Modbus device.
        
        Args:
            address: Starting address
            count: Number of coils to read
            
        Returns:
            List of coil values
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass
    
    @abstractmethod
    def read_holding_registers(self, address: int, count: int) -> List[int]:
        """
        Reads holding registers from Modbus device.
        
        Args:
            address: Starting address
            count: Number of registers to read
            
        Returns:
            List of register values
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass
    
    @abstractmethod
    def write_coil(self, address: int, value: bool) -> None:
        """
        Writes single coil to Modbus device.
        
        Args:
            address: Coil address
            value: Value to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass
    
    @abstractmethod
    def write_coils(self, address: int, values: List[bool]) -> None:
        """
        Writes multiple coils to Modbus device.
        
        Args:
            address: Starting address
            values: List of values to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass
    
    @abstractmethod
    def write_register(self, address: int, value: int) -> None:
        """
        Writes single register to Modbus device.
        
        Args:
            address: Register address
            value: Value to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass
    
    @abstractmethod
    def write_registers(self, address: int, values: List[int]) -> None:
        """
        Writes multiple registers to Modbus device.
        
        Args:
            address: Starting address
            values: List of values to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        pass


class MQTTClientInterface(ABC):
    """Interface for MQTT client handling communication with MQTT broker."""
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establishes connection with MQTT broker.
        
        Returns:
            True if connection was established, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Checks if client is connected to MQTT broker.
        
        Returns:
            True if client is connected, False otherwise
        """
        pass
    
    @abstractmethod
    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """
        Publishes message to specified MQTT topic.
        
        Args:
            topic: MQTT topic
            payload: Message content
            retain: Whether message should be retained by broker
            
        Raises:
            MQTTError: When publishing error occurs
        """
        pass
    
    @abstractmethod
    def subscribe(self, topic: str, callback: Callable[[MQTTMessage], None]) -> None:
        """
        Subscribes to MQTT topic.
        
        Args:
            topic: MQTT topic to subscribe to
            callback: Function called when message is received
            
        Raises:
            MQTTError: When subscription error occurs
        """
        pass


class GatewayInterface(ABC):
    """Interface for Modbus-MQTT gateway handling communication between systems."""
    
    @abstractmethod
    def mqtt_publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """
        Publishes MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Message content
            retain: Whether message should be retained
        """
        pass
    
    @abstractmethod
    def mqtt_subscribe(self, topic: str, callback: Callable[[MQTTMessage], None]) -> None:
        """
        Subscribes to MQTT topic.
        
        Args:
            topic: MQTT topic
            callback: Function to call when message is received
        """
        pass
    
    @abstractmethod
    def modbus_write_coils(self, address: int, data: Union[bool, List[bool]]) -> None:
        """
        Writes coils via Modbus.
        
        Args:
            address: Starting address
            data: Value or list of values to write
        """
        pass
    
    @abstractmethod
    def modbus_write_registers(self, address: int, data: Union[int, List[int]]) -> None:
        """
        Writes registers via Modbus.
        
        Args:
            address: Starting address
            data: Value or list of values to write
        """
        pass
    
    @abstractmethod
    def register_entity_set(self, modbus_class: Any, entity_type: Any, 
                          items: List[dict], item_count: int, 
                          poll_delay_ms: int = 0) -> None:
        """
        Registers entity set for handling.
        
        Args:
            modbus_class: Modbus class
            entity_type: Entity type
            items: List of entity definitions
            item_count: Number of entities
            poll_delay_ms: Polling delay in milliseconds
        """
        pass
    
    @abstractmethod
    def modbus_step(self) -> None:
        """Performs one step of Modbus polling cycle."""
        pass


class EntityInterface(ABC):
    """Interface for entities representing data points in the system."""
    
    @abstractmethod
    def reset(self) -> None:
        """Resets entity state to default values."""
        pass
    
    @abstractmethod
    def initialize(self) -> None:
        """Initializes entity, sets up initial parameters."""
        pass
    
    @abstractmethod
    def on_modbus_data(self, timestamp: int, data: ModbusData) -> None:
        """
        Processes data received from Modbus.
        
        Args:
            timestamp: Timestamp of data reception in ms
            data: Data from Modbus
        """
        pass
    
    @abstractmethod
    def process_modbus_data(self, timestamp: int, data: ModbusData) -> Any:
        """
        Processes Modbus data and updates entity state.
        
        Args:
            timestamp: Timestamp of data reception in ms
            data: Data from Modbus
            
        Returns:
            Previous entity state or other value depending on implementation
        """
        pass