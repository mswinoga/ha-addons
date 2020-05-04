from pymodbus.client.sync import ModbusTcpClient, ModbusUdpClient
from pymodbus.bit_read_message import *
from pymodbus.bit_write_message import *
from pymodbus.register_read_message import *
from pymodbus.register_write_message import *

import paho.mqtt.client as mqtt

from functools import partial
import logging
import threading
import queue
import time

import config
import entity

logger = logging.getLogger('gateway')
logger.setLevel(logging.DEBUG)

# MODBUS
modbus_udp_client = ModbusUdpClient(config.MODBUS_SERVER_HOST)
modbus_tcp_client = ModbusTcpClient(config.MODBUS_SERVER_HOST)

# MQTT
mqtt_client = mqtt.Client(config.MQTT_CLIENT_NAME)
mqtt_client.username_pw_set(username=config.MQTT_USER, password=config.MQTT_PASSWORD)

# last will
mqtt_client.will_set(config.MQTT_AVAILABILITY_TOPIC, "offline", retain=True)

# connect, loop_start will handle reconnections
mqtt_client.connect(config.MQTT_HOST)
mqtt_client.loop_start()

def modbus_execute(request):
    if not modbus_tcp_client.is_socket_open():
        modbus_tcp_client.connect()

    ret = modbus_tcp_client.execute(request)
    if ret.isError():
        ret = modbus_tcp_client.execute(request) # retry

    return ret

def modbus_write_coils(address, data):
    logger.debug("modbus_write_coils({}, {})".format(address, data))

    if isinstance(data, list):
        request = WriteMultipleCoilsRequest(address, data)
    else:
        request = WriteSingleCoilRequest(address, data)
    modbus_execute(request)

def modbus_write_registers(address, data):
    logger.debug("modbus_write_registers({}, {})".format(address, data))

    if isinstance(data, list):
        request = WriteMultipleRegistersRequest(address, data)
    else:
        request = WriteSingleRegisterRequest(address, data)
    modbus_execute(request)

class Gateway(entity.GatewayInterface):
    
    def __init__(self):
        super(Gateway, self).__init__()

        # state init
        self.processors = []

        # mqtt init
        logger.debug("gateway sending availability message")
        mqtt_client.publish(config.MQTT_AVAILABILITY_TOPIC, "online")

    # GatewayInterface
    def mqtt_publish(self, topic, payload, retain=False):
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
            if data_type == entity.ModbusClass.COIL:
                values = modbus_udp_client.read_coils(start_address, data_count).bits
            elif data_type == entity.ModbusClass.REGISTER:
                values = modbus_udp_client.read_holding_registers(start_address, data_count).registers
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

    def register_entity_set(self, modbus_class: entity.ModbusClass, entity_type, item_count, time_wait=0):
        entities = [entity_type(self, modbus_class, idx) for idx in range(0, item_count)]
        self.processors.append( (0, partial(self.__process_entities, entities, time_wait)) )

    def modbus_step(self):
        self.processors = [(step(ts), step) for ts, step in self.processors]
