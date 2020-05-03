from pymodbus.client.sync import ModbusTcpClient, ModbusUdpClient
import paho.mqtt.client as mqtt

from functools import partial
import logging
import threading
import queue
import time

import const
import entity

logger = logging.getLogger('gateway')
logger.setLevel(logging.DEBUG)

# MODBUS
modbus_udp_client = ModbusUdpClient(const.MODBUS_SERVER_HOST)
modbus_tcp_client = ModbusTcpClient(const.MODBUS_SERVER_HOST)

# MQTT
mqtt_client = mqtt.Client(const.MQTT_CLIENT_NAME)
mqtt_client.is_connected = False
mqtt_client.username_pw_set(username=const.MQTT_USERNAME, password=const.MQTT_PASSWORD)

# last will
mqtt_client.will_set(const.MQTT_AVAILABILITY_TOPIC, "offline", retain=True)

# connect, loop_start will handle reconnections
mqtt_client.connect(const.MQTT_SERVER_HOST)
mqtt_client.loop_start()


class Gateway(entity.GatewayInterface):
    
    def __init__(self):
        super(Gateway, self).__init__()

        # state init
        self.processors = []

        # mqtt init
        logger.debug("gateway sending availability message")
        mqtt_client.publish(const.MQTT_AVAILABILITY_TOPIC, "online")

    # GatewayInterface
    def mqtt_publish(self, topic, payload, retain=False):
        logger.debug("mqtt publish on {}: {}".format(topic, payload))
        mqtt_client.publish(topic, payload, retain=retain)

    def mqtt_subscribe(self, topic, callback):
        logger.debug("mqtt subscribe on {}".format(topic))
        mqtt_client.message_callback_add(topic, lambda client, userdata, msg: callback(msg))
        mqtt_client.subscribe(topic)

    def modbus_write_coils(self, address, data):
        logger.debug("modbus_write_coils({}, {})".format(address, data))
        if isinstance(data, list):
            modbus_tcp_client.write_coils(address, data, len(data))
        else:
            modbus_tcp_client.write_coil(address, data)

    def modbus_write_registers(self, address, data):
        logger.debug("modbus_write_registers({}, {})".format(address, data))
        if isinstance(data, list):
            modbus_tcp_client.write_registers(address, data)
        else:
            modbus_tcp_client.write_register(address, data)

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
            data_unit     = modbus_class.unit
            data_width    = modbus_class.width
            start_address = modbus_class.read_offset
            data_count    = data_width*len(entities)

            # get the values via modbus 
            if data_unit == 1:
                values = modbus_udp_client.read_coils(start_address, data_count).bits
            elif data_unit == 16:
                values = modbus_udp_client.read_holding_registers(start_address, data_count).registers
            else:
                raise Exception("data unit not supported: {}".format(data_unit))
            
            # process entities
            idx = 0
            for e in entities:
                new_idx = idx+data_width
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