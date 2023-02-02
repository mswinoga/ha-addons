import logging
import json
import os

logger = logging.getLogger('config')
logger.setLevel(logging.DEBUG)

CONFIG_PATH = os.environ["CONFIG_PATH"]
with open(CONFIG_PATH) as json_file:
    CONFIG = json.load(json_file)

logger.debug("reading configuration from {}: {}".format(CONFIG_PATH, CONFIG))

MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]


#MQTT_SERVER_HOST = "192.168.210.7"
MQTT_AVAILABILITY_TOPIC = "plc/availability"
MQTT_CLIENT_NAME = "modbus-gateway"

#MQTT_USERNAME = "mosquitto-modbus-gw"
#MQTT_PASSWORD = "YVz4Bcqen2sZaL"

DISCOVERY_PREFIX = CONFIG.get("discovery_prefix", "homeassistant")

MODBUS_SERVER_HOST = CONFIG.get("modbus_host", "192.168.40.10")
MODBUS_SERVER_PORT = int(CONFIG.get("modbus_port", 502))

ENTITY_SETS = CONFIG.get("entity_sets", [])

DEVICE = CONFIG.get("device")
