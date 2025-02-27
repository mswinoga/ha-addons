"""
Main execution module for Modbus-MQTT gateway.
Initializes and runs the gateway based on configuration.

This module is designed to work both for local testing and when used
by the Home Assistant addon through run.sh.
"""
import logging
import os
import signal
import sys
import time
from typing import Dict, List, Optional, Type, Any

from .config import get_config
from .gateway import Gateway
from .models import ModbusClassConfig, EntitySetConfig, TYPE_COIL, TYPE_REGISTER
from .entities import (
    BaseEntity,
    BinarySensorEntity,
    ButtonEntity,
    RelayEntity,
    SensorEntity,
    BlindEntity
)

# Configure logging based on environment variable or default to INFO
log_level_name = os.environ.get('LOGLEVEL', 'INFO')
log_level = getattr(logging, log_level_name.upper(), logging.INFO)

# Logger configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=log_level
)
logger = logging.getLogger('runner')


# Mapping of entity types to implementing classes
ENTITY_CLASSES = {
    "binary_sensor": BinarySensorEntity,
    "button": ButtonEntity,
    "relay": RelayEntity,
    "sensor": SensorEntity,
    "blind": BlindEntity,
}


def text_to_dict(txt: str) -> Dict[str, str]:
    """
    Converts text in "key1=val1,key2=val2" format to a dictionary.
    
    Args:
        txt: Text to convert
        
    Returns:
        Dictionary with key-value pairs
    """
    if not txt:
        return {}
        
    items = txt.split(",")
    result = {}
    
    for item in items:
        if not item:
            continue
            
        entry = item.split("=", 1)  # Split only on the first "=" character
        key = entry[0].strip()
        
        if not key:
            continue
            
        value = entry[1].strip() if len(entry) > 1 else ""
        result[key] = value
        
    return result


def create_modbus_class(entity_set: EntitySetConfig) -> ModbusClassConfig:
    """
    Creates Modbus class configuration from entity set configuration.
    
    Args:
        entity_set: Entity set configuration
        
    Returns:
        Modbus class configuration
    """
    return ModbusClassConfig(
        name=entity_set.set_id,
        data_type=entity_set.data_type,
        data_size=entity_set.data_size,
        read_offset=entity_set.read_offset,
        write_offset=entity_set.write_offset,
        read_only=entity_set.read_only,
        defaults=text_to_dict(entity_set.defaults)
    )


def get_entity_class(entity_type: str) -> Optional[Type[BaseEntity]]:
    """
    Gets entity class based on type.
    
    Args:
        entity_type: Entity type
        
    Returns:
        Entity class or None if type is unsupported
    """
    entity_class = ENTITY_CLASSES.get(entity_type)
    
    if not entity_class:
        logger.warning(f"Unsupported entity type: {entity_type}")
        
    return entity_class


def register_entity_sets(gateway: Gateway, config: Any) -> None:
    """
    Registers all entity sets in gateway.
    
    Args:
        gateway: Gateway instance
        config: Configuration containing entity sets
    """
    for entity_set in config.entity_sets:
        # Get entity class based on type
        entity_class = get_entity_class(entity_set.entity_type)
        if not entity_class:
            continue
            
        # Create Modbus class configuration
        modbus_class = create_modbus_class(entity_set)
        
        # Convert entity definitions to dictionaries
        entity_defs = [text_to_dict(item) for item in entity_set.entities]
        
        try:
            # Register entity set in gateway
            gateway.register_entity_set(
                modbus_class=modbus_class,
                entity_type=entity_class,
                items=entity_defs,
                item_count=entity_set.entity_count,
                poll_delay_ms=entity_set.poll_delay_ms
            )
            logger.info(f"Registered entity set: {entity_set.set_id}")
            
        except Exception as e:
            logger.error(f"Error registering entity set {entity_set.set_id}: {str(e)}")


def setup_signal_handlers(gateway: Gateway) -> None:
    """
    Sets up system signal handlers (SIGINT, SIGTERM).
    
    Args:
        gateway: Gateway instance to close on termination
    """
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, closing gateway...")
        gateway.close()
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # kill


def setup_test_environment() -> None:
    """
    Sets up environment variables for local testing if they're not already set.
    This allows running the gateway locally without needing to set all the
    environment variables that would normally be set by Home Assistant.
    """
    # Only set default values if environment variables are not already set
    if 'CONFIG_PATH' not in os.environ:
        test_config_path = os.path.join(os.path.dirname(__file__), 'test_config.json')
        os.environ['CONFIG_PATH'] = test_config_path
        logger.info(f"Using test configuration: {test_config_path}")
    
    # Set default MQTT credentials for local testing if not provided
    if 'MQTT_HOST' not in os.environ:
        os.environ['MQTT_HOST'] = 'localhost'
        logger.info("Using default MQTT host: localhost")
    
    if 'MQTT_USER' not in os.environ:
        os.environ['MQTT_USER'] = 'test'
        logger.info("Using default MQTT username: test")
    
    if 'MQTT_PASSWORD' not in os.environ:
        os.environ['MQTT_PASSWORD'] = 'test'
        logger.info("Using default MQTT password: test")


def main() -> None:
    """Main function running Modbus-MQTT gateway."""
    try:
        logger.info("Starting Modbus-MQTT gateway")
        
        # Set up environment for local testing if needed
        if os.environ.get('RUNNING_IN_HA', '').lower() != 'true':
            setup_test_environment()
        
        # Get configuration
        config = get_config()
        
        # Create gateway
        gateway = Gateway(
            modbus_host=config.modbus_host,
            modbus_port=config.modbus_port,
            mqtt_host=config.mqtt_host,
            mqtt_username=config.mqtt_user,
            mqtt_password=config.mqtt_password,
            mqtt_client_id=config.mqtt_client_name,
            mqtt_availability_topic=config.mqtt_availability_topic,
            device_info=config.device,
            discovery_prefix=config.discovery_prefix
        )
        
        # Configure signal handlers
        setup_signal_handlers(gateway)
        
        # Register entity sets
        register_entity_sets(gateway, config)
        
        # Run main loop
        logger.info("Gateway started, beginning polling cycle")
        while True:
            gateway.modbus_step()
            time.sleep(0.005)  # 5ms delay
            
    except KeyboardInterrupt:
        logger.info("Gateway operation interrupted (Ctrl+C)")
        if 'gateway' in locals():
            gateway.close()
            
    except Exception as e:
        logger.critical(f"Critical error: {str(e)}")
        if 'gateway' in locals():
            gateway.close()
        sys.exit(1)


if __name__ == "__main__":
    main()
