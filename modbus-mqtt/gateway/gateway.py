"""
Main implementation of Modbus-MQTT gateway.
Handles communication between Modbus and MQTT and manages entities.
"""
import logging
import time
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

from .interfaces import GatewayInterface, ModbusClientInterface, MQTTClientInterface
from .models import DeviceInfo, EntityDefinition, ModbusClassConfig, TYPE_COIL, TYPE_REGISTER
from .modbus_client import ModbusClient, ModbusError
from .mqtt_client import MQTTClient

# Default implementation must be imported by name to avoid circular import issues
from .entities.base_entity import BaseEntity

logger = logging.getLogger('gateway')


class Gateway(GatewayInterface):
    """
    Main gateway class for Modbus-MQTT integration.
    Integrates Modbus and MQTT clients and manages entities.
    """
    
    def __init__(
        self,
        modbus_host: str,
        modbus_port: int,
        mqtt_host: str,
        mqtt_port: int = 1883,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        mqtt_client_id: str = "modbus-gateway",
        mqtt_availability_topic: str = "plc/availability",
        device_info: Optional[DeviceInfo] = None,
        discovery_prefix: str = "homeassistant"
    ):
        """
        Initializes Modbus-MQTT gateway.
        
        Args:
            modbus_host: Modbus host address
            modbus_port: Modbus port
            mqtt_host: MQTT host address
            mqtt_port: MQTT port (default 1883)
            mqtt_username: MQTT username (optional)
            mqtt_password: MQTT password (optional)
            mqtt_client_id: MQTT client identifier (default "modbus-gateway")
            mqtt_availability_topic: Availability topic (default "plc/availability")
            device_info: Device information (optional)
            discovery_prefix: HA discovery prefix (default "homeassistant")
        """
        # Initialize basic parameters
        self.modbus_host = modbus_host
        self.modbus_port = modbus_port
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_username = mqtt_username
        self.mqtt_password = mqtt_password
        self.mqtt_client_id = mqtt_client_id
        self.mqtt_availability_topic = mqtt_availability_topic
        self.device_info = device_info
        self.discovery_prefix = discovery_prefix
        
        # Initialize state
        self.entity_sets: List[List[BaseEntity]] = []
        self.entity_processors: List[Tuple[int, Callable[[int], int]]] = []
        self.modbus_available = False
        
        # Initialize clients
        self.modbus_client = ModbusClient(
            host=modbus_host,
            port=modbus_port,
            timeout=1.0,
            retries=3
        )
        
        self.mqtt_client = MQTTClient(
            client_id=mqtt_client_id,
            host=mqtt_host,
            port=mqtt_port,
            username=mqtt_username,
            password=mqtt_password,
            availability_topic=mqtt_availability_topic
        )
        
        # Connect clients
        self._connect_clients()
        
        logger.info(f"Initialized Modbus-MQTT gateway for {modbus_host}:{modbus_port} -> {mqtt_host}:{mqtt_port}")
    
    def _connect_clients(self) -> None:
        """Connects Modbus and MQTT clients."""
        # Connect to MQTT
        if not self.mqtt_client.is_connected():
            self.mqtt_client.connect()
        
        # Connect to Modbus
        if not self.modbus_client.is_connected():
            self.modbus_client.connect()
    
    def gateway_available(self) -> None:
        """Sets gateway as available and publishes online status."""
        logger.info("Gateway is available")
        self.mqtt_publish(self.mqtt_availability_topic, "online", retain=True)
        self.modbus_available = True
    
    def gateway_unavailable(self) -> None:
        """Sets gateway as unavailable and publishes offline status."""
        logger.info("Gateway is unavailable")
        self.mqtt_publish(self.mqtt_availability_topic, "offline", retain=True)
        
        # Reset all entities
        for entity_set in self.entity_sets:
            for entity in entity_set:
                entity.reset()
                
        self.modbus_available = False
    
    def mqtt_publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """
        Publishes MQTT message.
        
        Args:
            topic: MQTT topic
            payload: Message content
            retain: Whether message should be retained
        """
        try:
            self.mqtt_client.publish(topic, payload, retain=retain)
        except Exception as e:
            logger.error(f"Error publishing MQTT message: {str(e)}")
    
    def mqtt_subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """
        Subscribes to MQTT topic.
        
        Args:
            topic: MQTT topic
            callback: Function to call when message is received
        """
        try:
            self.mqtt_client.subscribe(topic, callback)
        except Exception as e:
            logger.error(f"Error subscribing to MQTT topic: {str(e)}")
    
    def modbus_write_coils(self, address: int, data: Union[bool, List[bool]]) -> None:
        """
        Writes coils via Modbus.
        
        Args:
            address: Starting address
            data: Value or list of values to write
        """
        try:
            if isinstance(data, list):
                logger.info(f"Writing multiple coils: address={address}, values={data}")
                self.modbus_client.write_coils(address, data)
            else:
                logger.info(f"Writing coil: address={address}, value={data}")
                self.modbus_client.write_coil(address, data)
                
        except Exception as e:
            logger.error(f"Error writing coils: {str(e)}")
    
    def modbus_write_registers(self, address: int, data: Union[int, List[int]]) -> None:
        """
        Writes registers via Modbus.
        
        Args:
            address: Starting address
            data: Value or list of values to write
        """
        try:
            if isinstance(data, list):
                logger.info(f"Writing multiple registers: address={address}, values={data}")
                self.modbus_client.write_registers(address, data)
            else:
                logger.info(f"Writing register: address={address}, value={data}")
                self.modbus_client.write_register(address, data)
                
        except Exception as e:
            logger.error(f"Error writing registers: {str(e)}")
    
    def register_entity_set(
        self, 
        modbus_class: ModbusClassConfig, 
        entity_type: Type[BaseEntity], 
        items: List[Dict[str, str]], 
        item_count: int, 
        poll_delay_ms: int = 0
    ) -> None:
        """
        Registers entity set for handling.
        
        Args:
            modbus_class: Modbus class configuration
            entity_type: Entity type to create
            items: List of entity definitions
            item_count: Number of entities in set
            poll_delay_ms: Polling delay in milliseconds
        """
        logger.info(
            f"Registering entity set: {modbus_class.name}, "
            f"type={entity_type.__name__}, count={item_count}, "
            f"delay={poll_delay_ms}ms"
        )
        
        # Validate configuration
        if len(items) != item_count:
            raise ValueError(f"Number of entity definitions ({len(items)}) does not match item_count ({item_count})")
        
        # Check for duplicate names in set
        item_names = [item.get("name") for item in items if item and "name" in item]
        not_empty_names = [name for name in item_names if name]
        seen = set()
        duplicates = [x for x in not_empty_names if x in seen or seen.add(x)]
        if duplicates:
            raise ValueError(f"Entity names must be unique within set {modbus_class.name}, duplicates: {duplicates}")
        
        # Create entities
        entities = [
            entity_type(
                gateway=self, 
                entity_def=items[idx],
                modbus_class=modbus_class,
                modbus_idx=idx,
                discovery_prefix=self.discovery_prefix,
                availability_topic=self.mqtt_availability_topic
            ) 
            for idx in range(item_count)
        ]
        
        # Add to entity sets
        self.entity_sets.append(entities)
        
        # Create processor for entity set
        self.entity_processors.append(
            (0, partial(self._process_entities, entities, poll_delay_ms))
        )
    
    def _process_entities(
        self, 
        entities: List[BaseEntity], 
        time_wait: int, 
        previous_timestamp: int
    ) -> int:
        """
        Processes entity set.
        
        Args:
            entities: List of entities to process
            time_wait: Delay between polls in ms
            previous_timestamp: Previous timestamp in ms
            
        Returns:
            Current timestamp in ms
        """
        if not entities:
            logger.debug("No entities to process")
            return previous_timestamp
        
        # Get current timestamp in ms
        current_timestamp = int(time.time() * 1000)
        
        # Check if required wait time has passed
        if current_timestamp - previous_timestamp <= time_wait:
            return previous_timestamp
        
        try:
            # Get first entity to determine read parameters
            first_entity = entities[0]
            modbus_class = first_entity.modbus_class
            
            # Get read parameters
            data_type = modbus_class.data_type
            data_size = modbus_class.data_size
            start_address = modbus_class.read_offset
            data_count = data_size * len(entities)
            
            # Read values from Modbus
            if data_type == TYPE_COIL:
                values = self.modbus_client.read_coils(start_address, data_count)
            elif data_type == TYPE_REGISTER:
                values = self.modbus_client.read_holding_registers(start_address, data_count)
            else:
                raise ValueError(f"Unsupported data type: {data_type}")
            
            # Process entities
            idx = 0
            for entity in entities:
                new_idx = idx + data_size
                entity.on_modbus_data(current_timestamp, values[idx:new_idx])
                idx = new_idx
            
            return current_timestamp
            
        except Exception as e:
            logger.error(f"Error processing entities: {str(e)}")
            # In case of error, return previous timestamp
            # to avoid blocking other entity sets
            return previous_timestamp
    
    def modbus_step(self) -> None:
        """
        Performs one step of Modbus polling cycle.
        Checks device availability and processes all entity sets.
        """
        try:
            # Check Modbus device availability
            if not self.modbus_available:
                # Try to read a single coil to check availability
                self.modbus_client.read_coils(0, 1)
                
                # If we got here, device is available
                self.gateway_available()
            
            # Process all entity sets
            self.entity_processors = [
                (step(timestamp), step) 
                for timestamp, step in self.entity_processors
            ]
            
        except ModbusError as e:
            # Modbus device is not available
            if self.modbus_available:
                logger.error(f"Modbus device is not available: {str(e)}")
                self.gateway_unavailable()
            
            # Wait before next attempt
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Unexpected error in modbus_step: {str(e)}")
            # Exceptions other than ModbusError should not change availability state
            time.sleep(0.1)
    
    def close(self) -> None:
        """Closes Modbus and MQTT client connections."""
        try:
            # Set gateway as unavailable
            self.gateway_unavailable()
            
            # Close clients
            self.modbus_client.close()
            self.mqtt_client.close()
            
            logger.info("Closed Modbus-MQTT gateway")
            
        except Exception as e:
            logger.error(f"Error closing gateway: {str(e)}")
