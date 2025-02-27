"""
Configuration module for the Modbus-MQTT gateway.
Handles loading configuration from JSON file and environment variables.
"""
import json
import logging
import os
from typing import Dict, List, Optional, Any

from .models import (
    GatewayConfig,
    DeviceInfo,
    EntitySetConfig,
    ModbusClassConfig,
    EntityDefinition
)

# Logger configuration
logger = logging.getLogger('config')
logger.setLevel(logging.INFO)


def text_to_dict(txt: str) -> Dict[str, str]:
    """
    Converts text from comma-separated attribute format 
    (e.g., "key1=val1,key2=val2") to a dictionary.
    
    Args:
        txt: Text to convert
        
    Returns:
        Dictionary with converted key-value pairs
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


def load_config() -> GatewayConfig:
    """
    Loads configuration from JSON file and environment variables.
    
    Returns:
        Configured GatewayConfig object
    
    Raises:
        FileNotFoundError: When the configuration file does not exist
        KeyError: When required environment variables are missing
    """
    # Check required environment variables
    required_env_vars = ["CONFIG_PATH", "MQTT_HOST", "MQTT_USER", "MQTT_PASSWORD"]
    missing_vars = [var for var in required_env_vars if var not in os.environ]
    
    if missing_vars:
        raise KeyError(f"Missing required environment variables: {', '.join(missing_vars)}")
    
    config_path = os.environ["CONFIG_PATH"]
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file does not exist: {config_path}")
    
    # Load configuration from JSON file
    with open(config_path, "r") as json_file:
        try:
            config_data = json.load(json_file)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON file {config_path}: {e}")
            raise
    
    logger.info(f"Loaded configuration from {config_path}")
    
    # Create configuration object
    config = GatewayConfig.from_dict(config_data)
    
    # Override MQTT settings from environment variables
    config.mqtt_host = os.environ["MQTT_HOST"]
    config.mqtt_user = os.environ["MQTT_USER"]
    config.mqtt_password = os.environ["MQTT_PASSWORD"]
    
    return config


# Configuration instance - will be loaded on demand
CONFIG = None

# Function to get or load configuration
def get_config():
    """
    Gets or loads configuration.
    
    Returns:
        Configured GatewayConfig object
    
    Raises:
        Exception: When configuration cannot be loaded
    """
    global CONFIG
    if CONFIG is None:
        try:
            CONFIG = load_config()
        except Exception as e:
            logger.critical(f"Cannot load configuration: {e}")
            raise
    return CONFIG

# Export constants for backward compatibility - these will be loaded on demand
def get_discovery_prefix():
    return get_config().discovery_prefix

def get_mqtt_availability_topic():
    return get_config().mqtt_availability_topic

def get_mqtt_client_name():
    return get_config().mqtt_client_name

def get_mqtt_host():
    return get_config().mqtt_host

def get_mqtt_user():
    return get_config().mqtt_user

def get_mqtt_password():
    return get_config().mqtt_password

def get_modbus_server_host():
    return get_config().modbus_host

def get_modbus_server_port():
    return get_config().modbus_port

def get_device():
    return get_config().device

def get_entity_sets():
    return get_config().entity_sets

# For backward compatibility
DISCOVERY_PREFIX = property(get_discovery_prefix)
MQTT_AVAILABILITY_TOPIC = property(get_mqtt_availability_topic)
MQTT_CLIENT_NAME = property(get_mqtt_client_name)
MQTT_HOST = property(get_mqtt_host)
MQTT_USER = property(get_mqtt_user)
MQTT_PASSWORD = property(get_mqtt_password)
MODBUS_SERVER_HOST = property(get_modbus_server_host)
MODBUS_SERVER_PORT = property(get_modbus_server_port)
DEVICE = property(get_device)
ENTITY_SETS = property(get_entity_sets)
