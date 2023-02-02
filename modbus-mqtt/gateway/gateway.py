from pymodbus.client.sync import ModbusTcpClient, ModbusUdpClient
from pymodbus.bit_write_message import *
from pymodbus.register_write_message import *
from pymodbus.exceptions import ModbusException
from pymodbus.constants import Defaults

import paho.mqtt.client as mqtt

from functools import partial
import logging
import time

import config
import entity

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('gateway')
logger.setLevel(logging.INFO)

# MODBUS
Defaults.RetryOnEmpty = True
Defaults.Timeout = 0.2
Defaults.Retries = 5
Defaults.Reconnects = 5

modbus_udp_client = ModbusUdpClient(config.MODBUS_SERVER_HOST, timeout=3)
modbus_tcp_client = ModbusTcpClient(config.MODBUS_SERVER_HOST)

# MQTT
mqtt_client = mqtt.Client(config.MQTT_CLIENT_NAME)
mqtt_client.username_pw_set(username=config.MQTT_USER, password=config.MQTT_PASSWORD)

# last will
mqtt_client.will_set(config.MQTT_AVAILABILITY_TOPIC, "offline", retain=True)

# connect, loop_start will handle reconnections
mqtt_client.connect(config.MQTT_HOST)
mqtt_client.loop_start()

def on_mqtt_connect(client, data, flags, rc):
    logger.info("mqtt_client connected")
    mqtt_client.publish(config.MQTT_AVAILABILITY_TOPIC, "online")

mqtt_client.on_connect = on_mqtt_connect

def modbus_execute(request):
    if not modbus_tcp_client.is_socket_open():
        modbus_tcp_client.connect()

    try:
        ret = modbus_tcp_client.execute(request)
        if ret.isError():
            raise ret
    except:
        try:
            ret = modbus_tcp_client.execute(request) # retry
            if ret.isError():
                raise ret
        except e:
            logging.error(e)
            ret = None

    return ret

def modbus_write_coils(address, data):
    logger.info("modbus_write_coils({}, {})".format(address, data))

    if isinstance(data, list):
        request = WriteMultipleCoilsRequest(address, data)
    else:
        request = WriteSingleCoilRequest(address, data)
    modbus_execute(request)

def modbus_write_registers(address, data):
    logger.info("modbus_write_registers({}, {})".format(address, data))

    if isinstance(data, list):
        request = WriteMultipleRegistersRequest(address, data)
    else:
        request = WriteSingleRegisterRequest(address, data)
    modbus_execute(request)

class ModbusNotAvailableException(Exception):
    pass

class Gateway(entity.GatewayInterface):
    
    def __init__(self, device_info):
        super(Gateway, self).__init__()

        self.device_info = device_info
        # state init
        self.entity_sets = []
        self.processors = []
        self.modbus_available = False

        # mqtt init
        logger.info("gateway sending availability message")

    def gateway_available(self):
        self.mqtt_publish(config.MQTT_AVAILABILITY_TOPIC, "online")

    def gateway_unavailable(self):
        # push the unavailability message
        self.mqtt_publish(config.MQTT_AVAILABILITY_TOPIC, "offline")

        # reset all entities
        [ e.reset() for eset in self.entity_sets for e in eset ]

    # GatewayInterface
    def mqtt_publish(self, topic, payload, retain=True):
        logger.debug("mqtt publish on {}: {}".format(topic, payload))
        mqtt_client.publish(topic, payload, retain=retain)

    def mqtt_subscribe(self, topic, callback):
        logger.debug("mqtt subscribe on {}".format(topic))
        mqtt_client.message_callback_add(topic, lambda client, userdata, msg: callback(msg))
        mqtt_client.subscribe(topic)

    def modbus_write_coils(self, address, data):
        return modbus_write_coils(address, data)

    def modbus_write_registers(self, address, data):
        return modbus_write_registers(address, data)

    # internal methods
    def __process_entities(self, entities, time_wait, previous_timestamp):
        if len(entities) == 0:
            logger.debug("No entities to process in __process_entities")
            return

        # get actual timestamp
        current_timestamp = time.time_ns() // 1000000 # get current time in ms

        if current_timestamp - previous_timestamp > time_wait:
            # get start address and how many bits need to be read
            modbus_class:entity.ModbusClass = entities[0].modbus_class
            data_type     = modbus_class.data_type
            data_size    = modbus_class.data_size
            start_address = modbus_class.read_offset
            data_count    = data_size*len(entities)

            # get the values via modbus 
            if data_type == entity.TYPE_COIL:
                result = modbus_udp_client.read_coils(start_address, data_count)
                if result.isError():
                    raise result
                values = result.bits
            elif data_type == entity.TYPE_REGISTER:
                result = modbus_udp_client.read_holding_registers(start_address, data_count)
                if result.isError():
                    raise result
                values = result.registers
            else:
                raise Exception("data type not supported: {}".format(data_type))

            # process entities
            idx = 0
            for e in entities:
                new_idx = idx+data_size
                e.on_modbus_data(current_timestamp, values[idx:new_idx])
                idx = new_idx

            return current_timestamp
        else:
            return previous_timestamp

    def register_entity_set(self, modbus_class: entity.ModbusClass, entity_type, items, item_count, poll_delay_ms=0):
        logger.info("registering modbus_class={}, entity_type={}, item_count={}".format(modbus_class, entity_type, item_count))
        if len(items) != item_count:
            raise Exception("number of names in item_names does not match item_count")

        item_names = list(map(lambda i: i["name"] if i is not None and "name" in i else None, items))
        not_empty_names = [name for name in item_names if name]
        if len(set(not_empty_names)) != len(not_empty_names):
            raise Exception("names must be unique within a set_id")


        entities = [entity_type(self, items[idx], modbus_class, idx) for idx in range(0, item_count)]
        self.entity_sets.append(entities)
        self.processors.append( (0, partial(self.__process_entities, entities, poll_delay_ms)) )

    def modbus_step(self):
        try:
            if self.modbus_available == False:
                response = modbus_udp_client.read_coils(0, 1)
                if response.isError():
                    raise ModbusNotAvailableException()

                # modbus server is back
                self.gateway_available()
                self.modbus_available = True
                logger.info("modbus back online, gateway operational")

            self.processors = [(step(ts), step) for ts, step in self.processors]
        except ModbusException as e:
            logger.error("modbus not available, reconnecting in 500ms")
            logger.error(e)
            if self.modbus_available == True:
                self.gateway_unavailable()
                self.modbus_available = False
            time.sleep(.5)
                

