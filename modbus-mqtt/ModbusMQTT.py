from pymodbus.client.sync import ModbusTcpClient, ModbusUdpClient
import paho.mqtt.client as mqtt

from timeit import timeit
from datetime import datetime
import threading
import queue
import json
import time
import re


CLICK_PAUSE_MAX = 250
LONG_PRESS_MIN = 400


MQTT_SERVER_HOST = "htpc.swinoga.pl"
MQTT_SERVER_HOST = "192.168.210.7"
MQTT_CLIENT_NAME = "modbus-gateway"

DISCOVERY_PREFIX = "homeassistant"

MODBUS_SERVER_HOST = "plc"
MODBUS_SERVER_HOST = "192.168.210.22"
MODBUS_SERVER_PORT = 502

MQTT_AVAILABILITY_TOPIC = "plc/availability"

# initialization / global methods


# modbus related

def modbus_read_coils(address, number):
    return modbus_client.read_coils(address, number).bits

def modbus_write_single_coil(address, val):
    return modbus_client.write_coil(address, val)

def mqtt_on_connect(client, userdata, flags, rc):
    if rc==0 and client.is_connected == False:
        # birth message
        mqtt_client.publish(MQTT_AVAILABILITY_TOPIC, "online", retain=True)

        # set flag
        client.is_connected = True

def mqtt_on_disconnect(client, userdata, rc):
    client.is_connected = False

# initialize mqtt client
modbus_client = ModbusUdpClient(MODBUS_SERVER_HOST)
mqtt_client = mqtt.Client(MQTT_CLIENT_NAME)
mqtt_client.is_connected = False
mqtt_client.on_connect = mqtt_on_connect
mqtt_client.on_disconnect = mqtt_on_disconnect
mqtt_client.username_pw_set(username="mosquitto-modbus-gw", password="YVz4Bcqen2sZaL")

# last will
mqtt_client.will_set(MQTT_AVAILABILITY_TOPIC, "offline", retain=True)

# connect
mqtt_client.connect(MQTT_SERVER_HOST)
mqtt_client.loop_start()


# mqtt related

while not mqtt_client.is_connected:
    print("connecting to MQTT broker")
    time.sleep(1)

def mqtt_publish(topic, val, retain=False, will=False):
    if will:
        mqtt_client.will_set(topic, val, retain=retain)
    else:
        mqtt_client.publish(topic, val, retain=retain)


# Event queue (modbus/mqtt outbound)

class EventQueue(object):

    queue = queue.SimpleQueue()
    _worker = None

    @staticmethod
    def publish(event):
        EventQueue.queue.put(event)

    @staticmethod
    def worker():
        while True:
            # get next event to publish
            event = EventQueue.queue.get()
            if event is None:
                break
            elif isinstance(event, MQTTEvent):
                topic = event.topic
                value = event.payload
                retain = event.retain
                will = event.will
                mqtt_publish(topic, value, retain=retain, will=will)
            elif isinstance(event, WriteModbusBitEvent):
                modbus_write_single_coil(event.address, event.value)

            # mark the event as done
            # EventQueue.queue.task_done()

    @staticmethod
    def start():
        EventQueue._worker = threading.Thread(target=EventQueue.worker)
        EventQueue._worker.start()


EventQueue.start()


# events that will write to modbus 
class ModbusEvent(object):

    def __init__(self, address, value):
        self.address = address
        self.value = value


# events that will publish in mqtt
class WriteModbusBitEvent(ModbusEvent):

    def __init__(self, address, value):
        super(WriteModbusBitEvent, self).__init__(address, value)


class MQTTEvent():

    def __init__(self, topic=None, payload=None, retain=False, will=False):
        self.topic = topic
        self.payload = payload
        self.retain = retain
        self.will = will

class PublishEvent(MQTTEvent):

    def __init__(self, event_type, entity_address, payload, retain=False, will=False):
        super(PublishEvent, self).__init__(
            topic = "{}/{}".format(entity_address, event_type),
            payload = payload,
            retain = retain,
            will = will
        )
        self.event_type = event_type
        self.entity_address = entity_address

class PublishStateEvent(PublishEvent):

    def __init__(self, entity_address, state, retain=False):
        super(PublishStateEvent, self).__init__("status", entity_address, state, retain=retain)


class HoldEvent(PublishEvent):

    def __init__(self, entity_address, click_count):
        super(HoldEvent, self).__init__("long", entity_address, click_count)

class HoldReleaseEvent(PublishEvent):

    def __init__(self, entity_address):
        super(HoldReleaseEvent, self).__init__("long", entity_address, "RELEASE")

class ClickEvent(PublishEvent):

    def __init__(self, entity_address, click_count):
        super(ClickEvent, self).__init__("click", entity_address, click_count)


# Modbus entities managed by this gateway

class Entity(object):

    def __init__(self, mqtt_address, modbus_address):
        # set outbound addresses (inbound are updated via the on_* callbacks)
        self.mqtt_address = mqtt_address
        self.modbus_address = modbus_address

        # initialize state
        self.state = None

    def discovery(self):
        config = self.discovery_config()
        component = self.discovery_type()
        uid = self.discovery_uid()
        if config is not None and component is not None and uid is not None:
            EventQueue.publish(MQTTEvent(
                topic = "{}/{}/plc/{}/config".format(DISCOVERY_PREFIX, component, uid),
                payload = config,
                retain = True))

    def discovery_type(self):
        pass

    def discovery_uid(self):
        pass 

    def discovery_config(self):
        pass

    def birth_msg(self):
        pass


class BitEntity(Entity):

    def __init__(self, mqtt_address, modbus_address):
        super(BitEntity, self).__init__(mqtt_address, modbus_address)

    def on_modbus_update(self, timestamp, new_val):
        # store current value
        old_val = self.state

        if self.state != new_val:
            # retain mqtt messages for outputs (having modbus_address)
            retain = True if self.modbus_address else False
            value = "ON" if new_val else "OFF"
            EventQueue.publish(PublishStateEvent(self.mqtt_address, value, retain))
            self.state = new_val

        # pass the old value to method caller
        return old_val

    def on_mqtt_msg(self, event, msg):
        value = self._mqtt_to_modbus(msg)
        if value is None:
            print("{}: <-[MQTT] {} ({}): unrecognized command {}".format(
                datetime.now(),
                self.mqtt_address,
                event,
                msg.payload,
                value))
        else:
            EventQueue.publish(WriteModbusBitEvent(self.modbus_address, value))
            print("{}: <-[MQTT] {} ({}): {} --> modbus({}) = {}".format(
                datetime.now(),
                self.mqtt_address,
                event,
                msg.payload,
                self.modbus_address,
                value))

    def _mqtt_to_modbus(self, msg):
        val = msg.payload.decode('utf-8')
        upper_val = str(val).upper()
        if upper_val == "ON" or upper_val == "1":
            return True
        elif upper_val == "OFF" or upper_val == "0":
            return False
        elif upper_val == "TOGGLE":
            return not self.state
        else:
            return None

class LightRelayEntity(BitEntity):

    def __init__(self, mqtt_address, modbus_address):
        super(LightRelayEntity, self).__init__(mqtt_address, modbus_address)

    def discovery_type(self):
        return "light"
    
    def discovery_uid(self):
        return "plc_{}_{}".format(self.discovery_type(), self.modbus_address)

    def discovery_config(self):
        return json.dumps({
                "~": self.mqtt_address,
                "name": "Light {}".format(self.modbus_address),
                "unique_id": self.discovery_uid(),
                "availability_topic": MQTT_AVAILABILITY_TOPIC,
                "command_topic": "~/set",
                "state_topic": "~/status"
            })


class ButtonEntity(BitEntity):

    def __init__(self, mqtt_address, modbus_address):
        super(ButtonEntity, self).__init__(mqtt_address, modbus_address)
        self.click_count = 0
        self.hold = False
        self.timestamp = 0

    def on_modbus_update(self, timestamp, new_val):
        old_val = super(ButtonEntity, self).on_modbus_update(timestamp, new_val)
        #old_val = self.state
        
        # the following implementation is based on the fact,
        # that 'on_modbus_update' is called frequently
        if old_val != new_val:

            if new_val == True:
                self.click_count = self.click_count+1
            elif new_val == False:
                if self.hold == True:
                    EventQueue.publish(HoldReleaseEvent(self.mqtt_address))
                    self.hold = False
                    self.click_count = 0

            self.timestamp = timestamp
        elif new_val == True and self.hold == False:
            # possible click timeout (hold)
            delta = timestamp - self.timestamp
            if delta > LONG_PRESS_MIN:
                EventQueue.publish(HoldEvent(self.mqtt_address, self.click_count))
                self.hold = True

        elif new_val == False and self.click_count > 0:
            # possible pause timeout (click)
            delta = timestamp - self.timestamp
            if delta > CLICK_PAUSE_MAX:
                EventQueue.publish(ClickEvent(self.mqtt_address, self.click_count))
                self.click_count = 0

        self.state = new_val
        return old_val


class WordBasedEntity(Entity):

    def __init__(self, mqtt_address, modbus_address):
        super(BitEntity, self).__init__(mqtt_address, modbus_address)

    def on_modbus_update(self, timestamp, new_val):
        # store current value
        old_val = self.state

        if self.state != new_val:
            # retain mqtt messages for outputs (having modbus_address)
            retain = True if self.modbus_address else False
            value = "ON" if new_val else "OFF"
            EventQueue.publish(PublishStateEvent(self.mqtt_address, value, retain))
            self.state = new_val

        # pass the old value to method caller
        return old_val

    def on_mqtt_msg(self, event, msg):
        value = self._mqtt_to_modbus(msg)
        if value is None:
            print("{}: <-[MQTT] {} ({}): unrecognized command {}".format(
                datetime.now(),
                self.mqtt_address,
                event,
                msg.payload,
                value))
        else:
            EventQueue.publish(WriteModbusBitEvent(self.modbus_address, value))
            print("{}: <-[MQTT] {} ({}): {} --> modbus({}) = {}".format(
                datetime.now(),
                self.mqtt_address,
                event,
                msg.payload,
                self.modbus_address,
                value))

    def _mqtt_to_modbus(self, msg):
        val = msg.payload.decode('utf-8')
        upper_val = str(val).upper()
        if upper_val == "ON" or upper_val == "1":
            return True
        elif upper_val == "OFF" or upper_val == "0":
            return False
        elif upper_val == "TOGGLE":
            return not self.state
        else:
            return None


class Gateway(object):

    def __init__(self, topic_sub_pattern=None, topic_idx_pattern=None, get_address_offset=0, set_address_offset=9, mqtt_retain=False, item_count=1):
        self.topic_sub_pattern = topic_sub_pattern
        self.topic_idx_pattern = topic_idx_pattern
        self.get_address_offset = get_address_offset
        self.set_address_offset = set_address_offset
        self.mqtt_retain = mqtt_retain
        self.item_count = item_count
        self.state = None

    def initialize(self):
        if self.topic_sub_pattern:
            mqtt_client.message_callback_add(self.topic_sub_pattern, self._on_mqtt_message)
            mqtt_client.subscribe(self.topic_sub_pattern)

    def mqtt_topic_split(self, msg):
        m = re.match(self.topic_idx_pattern, msg.topic)
        try:
            mod = int(m.group(1))-1
            idx = int(m.group(2))-1
            event = m.group(3)
            return mod*8+idx, mod, idx, event
        except:
            return None, None, None, None

    def _on_mqtt_message(self, client, userdata, msg):
        self.on_mqtt_message(msg)

    def on_mqtt_message(self, msg):
        raise Exception('Method not implemented')

    def modbus_read(self):
        raise Exception('Method not implemented')

class BitGateway(Gateway):

    topic_sub_pattern = "plc/{namespace}/+/set"
    topic_idx_pattern = "plc/{namespace}/([^/.]+)-([^/]+)/(.+)"
    bit_adr_pattern   = "plc/{}/{}-{}"

    def __init__(self, namespace, mqtt_retain=False, get_address_offset=0, set_address_offset=None, item_count=1, entity_type=BitEntity):
        super(BitGateway, self).__init__(
                topic_sub_pattern=BitGateway.topic_sub_pattern.format(namespace=namespace) if set_address_offset is not None else None,
                topic_idx_pattern=BitGateway.topic_idx_pattern.format(namespace=namespace) if set_address_offset is not None else None,
                get_address_offset=get_address_offset,
                set_address_offset=set_address_offset,
                mqtt_retain=mqtt_retain,
                item_count = item_count)

        self.entity_type = entity_type
        self.namespace = namespace

        self.initialize()

    def initialize(self):
        super(BitGateway, self).initialize()
        
        def address(idx):
            mod = idx//8+1
            rem = idx%8+1
            return BitGateway.bit_adr_pattern.format(self.namespace, mod, rem)

        off = self.set_address_offset
        self.state = [
                self.entity_type(
                    address(idx),
                    off+idx if off is not None else None)
                for idx in range(self.item_count)]

        [entity.discovery() for entity in self.state]
        [entity.birth_msg() for entity in self.state]


    def modbus_read(self):
        return modbus_read_coils(self.get_address_offset, self.item_count)

    def modbus_step(self):
        values = self.modbus_read()
        timestamp = time.time_ns() // 1000000 # get current time in ms
        if values:
            [entity.on_modbus_update(timestamp, val) for entity, val in zip(self.state, values)]

    def on_mqtt_message(self, msg):
        idx, mod, no, event = self.mqtt_topic_split(msg)
        if idx is not None:
            self.state[idx].on_mqtt_msg(event, msg)



gateways = [
    # inputs, read offset = 0, no write is possible
    BitGateway(
        "di",
        item_count=112,
        entity_type=ButtonEntity),
    # meter inputs
    BitGateway(
        "meter",
        item_count=8,
        get_address_offset=112),
    # outputs, read offset = 512, write offset = 0
    BitGateway(
        "do",
        mqtt_retain=True,
        set_address_offset=0,
        get_address_offset=512,
        item_count=152,
        entity_type=LightRelayEntity)
]

while True:
    for gateway in gateways:
        gateway.modbus_step()
        time.sleep(0.01) # 10ms
