import json
import logging

from config import DISCOVERY_PREFIX, MQTT_AVAILABILITY_TOPIC
from abc import ABC, ABCMeta, abstractmethod

logger = logging.getLogger('entity')
logger.setLevel(logging.DEBUG)

class GatewayInterface(metaclass=ABCMeta):

    @abstractmethod
    def mqtt_publish(self, topic, payload, retain=False):
        raise NotImplementedError

    @abstractmethod
    def mqtt_subscribe(self, topic, callback):
        raise NotImplementedError

    @abstractmethod
    def modbus_write_coils(self, address, data):
        raise NotImplementedError

    @abstractmethod
    def modbus_write_registers(self, address, data):
        raise NotImplementedError


TYPE_REGISTER = "register"
TYPE_COIL = "coil"

class ModbusClass(object):

    def __init__(self,
            name,
            data_type=TYPE_COIL,
            data_size=1,
            read_offset=0,
            write_offset=0,
            read_only=True):
        self.name = name
        self.data_type = data_type
        self.data_size = data_size
        self.read_offset = read_offset
        self.write_offset = write_offset
        self.read_only = read_only

    def __str__(self):
        return "ModbusClass(name={}, data_type={}, data_size={}, read_offset={}, write_offset={}, read_only={})".format(
            self.name,
            self.data_type,
            self.data_size,
            self.read_offset,
            self.write_offset,
            self.read_only
        )


    @abstractmethod
    def mqtt_coordinate(self, address, slot_size=8):
        mod = address//slot_size+1
        rem = address%slot_size+1
        return "{}-{}".format(mod, rem)

class Entity(ABC):

    TOPIC_BASE   = "plc/{e.modbus_class.name}/{e.mqtt_coordinate}"
    TOPIC_STATUS = "status"
    TOPIC_SET    = "set"

    DISCOVERY_TOPIC_PATTERN = DISCOVERY_PREFIX+"/{e.discovery_component}/plc/{e.discovery_uid}/config"
    DISCOVERY_UID_PATTERN = "{e.discovery_component}-{e.modbus_class.name}-{e.mqtt_coordinate}"

    def __init__(self,
            gateway: GatewayInterface,
            modbus_class: ModbusClass,
            modbus_idx):
        # entity attributes
        self.gateway = gateway
        self.modbus_class = modbus_class
        self.modbus_idx = modbus_idx

        # state data
        self.state = None

        # initialize
        self.initialize()

    def initialize(self):
        data_type = self.modbus_class.data_type
        if data_type not in [TYPE_REGISTER, TYPE_COIL]:
            raise Exception("Data class not supported: {}".format(data_type))

        # send discovery info to mqtt
        topic = self.discovery_topic
        payload = self.discovery_payload
        if topic is not None and payload is not None:
            self.gateway.mqtt_publish(
                topic=topic,
                payload=payload,
                retain=True
            )

    @property
    def modbus_read_address(self):
        return self.modbus_idx+self.modbus_class.read_offset

    @property
    def modbus_write_address(self):
        return self.modbus_idx*self.modbus_class.data_sizdata_size+self.modbus_class.write_offset
        
    @property
    def mqtt_coordinate(self):
        return self.modbus_class.mqtt_coordinate(self.modbus_idx)

    @property
    def mqtt_topic_base(self):
        return Entity.TOPIC_BASE.format(e=self)

    @property
    def discovery_topic(self):
        return Entity.DISCOVERY_TOPIC_PATTERN.format(e=self)

    @property
    def discovery_uid(self):
        return Entity.DISCOVERY_UID_PATTERN.format(e=self)

    @property
    def discovery_component(self):
        ''' implement this method to send a discovery message to HA '''
        return None

    @property
    def discovery_payload(self):
        return None

    def mqtt_topic(self, *args):
        topic = "/".join([self.mqtt_topic_base]+list(args))
        logging.debug("topic: {}".format(topic))
        return topic

    def on_modbus_data(self, timestamp, data):
        if len(data) != self.modbus_class.data_size:
            raise Exception("data lenght is supported: {}".format(data))

        self.process_modbus_data(timestamp, data)

    @abstractmethod
    def process_modbus_data(self, timestamp, data):
        pass


class BitEntity(Entity):

    def process_modbus_data(self, timestamp, data):
        # store current value
        old_val = self.state
        new_val = data[0]

        if new_val != self.state:
            # retain mqtt messages for outputs (with write operation supported)
            retain = self.modbus_class.read_only
            value = "ON" if new_val else "OFF"
            self.gateway.mqtt_publish(
                self.mqtt_topic(Entity.TOPIC_STATUS),
                value,
                retain=retain
            )
            self.state = new_val

        # pass back the old value
        return old_val


class ButtonEntity(BitEntity):

    CLICK_PAUSE_MAX = 250
    LONG_PRESS_MIN = 400

    def __init__(self, gateway, modbus_class, modbus_idx):
        super(ButtonEntity, self).__init__(
            gateway,
            modbus_class=modbus_class,
            modbus_idx=modbus_idx
        )
        self.click_count = 0
        self.hold = False
        self.timestamp = 0

    def process_modbus_data(self, timestamp, data):
        old_val = super(ButtonEntity, self).process_modbus_data(timestamp, data)
        
        # the following implementation is based on the fact,
        # that 'process_modbus_data' is called frequently
        if old_val != self.state:

            if self.state == True:
                self.click_count = self.click_count+1
            elif self.state == False:
                if self.hold == True:
                    self.gateway.mqtt_publish(
                        self.mqtt_topic("long"),
                        "RELEASE"
                    )
                    self.hold = False
                    self.click_count = 0

            self.timestamp = timestamp
        elif self.state == True and self.hold == False:
            # possible click timeout (hold)
            delta = timestamp - self.timestamp
            if delta > ButtonEntity.LONG_PRESS_MIN:
                self.gateway.mqtt_publish(
                    self.mqtt_topic('long'),
                    self.click_count
                )
                self.hold = True

        elif self.state == False and self.click_count > 0:
            # possible pause timeout (click)
            delta = timestamp - self.timestamp
            if delta > ButtonEntity.CLICK_PAUSE_MAX:
                self.gateway.mqtt_publish(
                    self.mqtt_topic("click"),
                    self.click_count
                )
                self.click_count = 0

        return old_val

class BitOutputEntity(BitEntity):

    def initialize(self):
        super(BitOutputEntity, self).initialize()
        self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)

    def on_mqtt_set(self, msg):
        payload = msg.payload.decode('utf-8')
        upper_payload = str(payload).upper()
        value = None
        if upper_payload == "ON" or upper_payload == "1":
            value = True
        elif upper_payload == "OFF" or upper_payload == "0":
            value = False
        elif upper_payload == "TOGGLE":
            value = not self.state

        if value is not None:
            logging.info("{}: {} --> modbus({}) = {}".format(msg.topic, msg.payload, self.modbus_write_address, value))
            self.gateway.modbus_write_coils(self.modbus_write_address, value)
        else:
            logging.info("{}: unrecognized command {}".format(msg.topic, msg.payload))

    @property
    def discovery_component(self):
        return None
    
    @property
    def discovery_payload(self):
        return json.dumps({
                "~": self.mqtt_topic_base,
                "name": "{} {}".format(self.discovery_component, self.modbus_idx),
                "unique_id": self.discovery_uid,
                "availability_topic": MQTT_AVAILABILITY_TOPIC,
                "command_topic": "~/{}".format(Entity.TOPIC_SET),
                "state_topic": "~/{}".format(Entity.TOPIC_STATUS)
            })

class LightRelayEntity(BitOutputEntity):

    @property
    def discovery_component(self):
        return "light"

class BlindEntity(Entity):

    def __init__(self, gateway, modbus_class, modbus_idx):
        super(BlindEntity, self).__init__(
            gateway,
            modbus_class=modbus_class,
            modbus_idx=modbus_idx
        )

        if modbus_class.data_type != TYPE_REGISTER:
            raise Exception("BlindEntity only supports word data format")
        if modbus_class.data_size != 2:
            raise Exception("BlindEntity only supports two word data size: {}".format(modbus_class))

        self.pos = 0
        self.target = 0
        self.t_up = 0
        self.t_dn = 0

    def initialize(self):
        super(BlindEntity, self).initialize()
        self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)
        self.gateway.mqtt_subscribe(self.mqtt_topic("config"), self.on_mqtt_config)

    def on_mqtt_set(self, msg):
        payload = msg.payload.decode('utf-8')
        try:
            value = int(payload)
            if value < 0:
                value = 0
            elif value > 100:
                value = 100
            value = value | 0x80
        except:
            if payload == "OPEN":
                value = 100 | 0x80
            elif payload == "CLOSE":
                value = 0 | 0x80
            elif payload == "STOP":
                value = self.target & 0x7F
            else:
                logger.warn("BlindEntity operation not supported: {}".format(payload))
                return

        # TODO: overwriting current position
        self.gateway.modbus_write_registers(self.modbus_write_address, value)

    def on_mqtt_config(self, msg):
        payload = msg.payload.decode('utf-8')
        config = json.loads(payload)
        t_up = config.get("t_up", None)
        t_dn = config.get("t_dn", None)
        if t_up is not None or t_dn is not None:
            if t_up is not None and t_dn is not None:
                t_conf = (t_up<<8) + t_dn
            elif t_up is not None:
                t_conf = (t_up<<8) + self.t_dn
            else:
                t_conf = (self.t_up<<8) + t_dn

            self.gateway.modbus_write_registers(self.modbus_write_address+1, t_conf)

    def process_modbus_data(self, timestamp, data):

        def publish_state(topic, val):
            self.gateway.mqtt_publish(self.mqtt_topic(topic), val)

        # store current value
        if data[0] & 0x80 == 0: # stop command
            new_target = None
        else:
            new_target = data[0] & 0x7F

        new_pos    = (data[0] & 0xFF00) >> 8
        new_t_up   = (data[1] & 0xFF00) >> 8
        new_t_dn   = (data[1] & 0x00FF)

        if self.pos != new_pos:
            publish_state(Entity.TOPIC_STATUS, new_pos)
            self.pos = new_pos
        
        if self.target != new_target:
            publish_state("target", new_target)
            self.target = new_target

        if self.t_up != new_t_up:
            publish_state("t_up", new_t_up)
            self.t_up = new_t_up
        
        if self.t_dn != new_t_dn:
            publish_state("t_dn", new_t_dn)
            self.t_dn = new_t_dn

    @property
    def discovery_component(self):
        return "cover"

    @property
    def discovery_payload(self):
        return json.dumps({
                "~": self.mqtt_topic_base,
                "name": "{} {}".format(self.discovery_component, self.modbus_idx),
                "unique_id": self.discovery_uid,
                "availability_topic": MQTT_AVAILABILITY_TOPIC,
                "command_topic": "~/{}".format(Entity.TOPIC_SET),
                "set_position_topic": "~/{}".format(Entity.TOPIC_SET),
                "position_topic": "~/{}".format(Entity.TOPIC_STATUS)
            })

    @property
    def mqtt_coordinate(self):
        return self.modbus_class.mqtt_coordinate(self.modbus_idx, slot_size=4)
