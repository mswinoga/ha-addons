import re
import json
import logging
from unidecode import unidecode

from config import DISCOVERY_PREFIX, MQTT_AVAILABILITY_TOPIC
from abc import ABC, ABCMeta, abstractmethod

logger = logging.getLogger('entity')
logger.setLevel(logging.INFO)

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
            read_only=True,
            defaults=None):
        self.name = name
        self.data_type = data_type
        self.data_size = data_size
        self.read_offset = read_offset
        self.write_offset = write_offset
        self.read_only = read_only
        self.defaults = defaults if defaults else {}

    def __str__(self):
        return "ModbusClass(name={}, data_type={}, data_size={}, read_offset={}, write_offset={}, read_only={}, defaults={})".format(
            self.name,
            self.data_type,
            self.data_size,
            self.read_offset,
            self.write_offset,
            self.read_only,
            self.defaults
        )


class Entity(ABC):

    TOPIC_BASE   = "plc/{e.modbus_class.name}/{e.discovery_uid}"
    TOPIC_STATE = "state"
    TOPIC_SET    = "set"

    DISCOVERY_TOPIC_PATTERN = DISCOVERY_PREFIX+"/{e.component}/plc/{e.discovery_uid}/config"

    def __init__(self,
            gateway,
            entity_def,
            modbus_class: ModbusClass,
            modbus_idx):
        # do not process unnamed entities
        if entity_def is None:
            return

        # entity attributes
        self.gateway = gateway
        self.entity_def = entity_def
        self.modbus_class = modbus_class
        self.modbus_idx = modbus_idx

        self.entity_name = self.entity_def.get("name")
        uid = unidecode("{}_{}".format(self.entity_name.lower(), self.modbus_class.name))
        self.discovery_uid = re.sub(r"\s+", "_", uid)

        attr = "component"
        cmp = self.entity_def.get(attr) if attr in self.entity_def else self.modbus_class.defaults.get(attr)
        self.component = cmp if cmp else self.class_component

        self.modbus_read_address = self.modbus_idx+self.modbus_class.read_offset
        self.modbus_write_address = self.modbus_idx*self.modbus_class.data_size+self.modbus_class.write_offset
        self.mqtt_topic_base = Entity.TOPIC_BASE.format(e=self)
        self.discovery_topic = Entity.DISCOVERY_TOPIC_PATTERN.format(e=self) if self.component else None

        # state data
        self.reset()

        # initialize
        self.initialize()

    def reset(self):
        self.state = None

    def initialize(self):

        if not self.entity_name:
            logger.info("skipping empty name in {} set".format(self.modbus_class.name))
            return

        data_type = self.modbus_class.data_type
        if data_type not in [TYPE_REGISTER, TYPE_COIL]:
            raise Exception("Data class not supported: {}".format(data_type))

        # send discovery info to mqtt
        topic = self.discovery_topic
        payload = {}
        payload.update(self.modbus_class.defaults)
        payload.update(self.entity_def)
        payload.update(self.discovery_payload())
        if topic is not None and payload is not None:
            self.gateway.mqtt_publish(
                topic=topic,
                payload=json.dumps({k:v for k,v in payload.items() if v is not None}),
                retain=True
            )

    @property
    def class_component(self):
        ''' default homeassistant component implemented by this entity class '''
        return None

    def discovery_payload(self):
        return {
            "~": self.mqtt_topic_base,
            "name": self.entity_name,
            "device": self.gateway.device_info,
            "unique_id": self.discovery_uid,
            "availability_topic": MQTT_AVAILABILITY_TOPIC,
            "command_topic": "~/{}".format(Entity.TOPIC_SET),
            "state_topic": "~/{}".format(Entity.TOPIC_STATE),
        }

    def mqtt_topic(self, *args):
        topic = "/".join([self.mqtt_topic_base]+list(args))
        logging.debug("topic: {}".format(topic))
        return topic

    def on_modbus_data(self, timestamp, data):
        # skip entities without names
        if not self.entity_name:
            return

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
                self.mqtt_topic(Entity.TOPIC_STATE),
                value,
                retain=retain
            )
            self.state = new_val

        # pass back the old value
        return old_val


class BinarySensorEntity(BitEntity):

    @property
    def class_component(self):
        return "binary_sensor"

class ButtonEntity(BitEntity):

    CLICK_PAUSE_MAX = 250
    LONG_PRESS_MIN = 400

    def reset(self):
        super(ButtonEntity, self).reset()

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

class RelayEntity(BitEntity):

    def initialize(self):
        super(RelayEntity, self).initialize()
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
    def class_component(self):
        return "switch"


class SensorEntity(Entity):

    def initialize(self):
        super(SensorEntity, self).initialize()

        if self.modbus_class.data_type != TYPE_REGISTER:
            raise Exception("SensorEntity only supports word data format")
        if self.modbus_class.data_size > 2:
            raise Exception("SensorEntity only supports up to two word data size: {}".format(self.modbus_class))

        if not self.modbus_class.read_only:
            self.gateway.mqtt_subscribe(self.mqtt_topic("set"), self.on_mqtt_set)

    def on_mqtt_set(self, msg):
        payload = msg.payload.decode('utf-8')
        try:
            value = int(payload)
            if self.modbus_class.data_size == 1:
                encoded = [value]
            else:
                encoded = [value & 0xFFFF, (value >> 16) & 0xFFFF]
            self.gateway.modbus_write_registers(self.modbus_write_address, encoded)
        except:
            logger.warn("SensorEntity operation not supported: {}".format(payload))


    def process_modbus_data(self, timestamp, data):

        # store current value
        if self.modbus_class.data_size == 1:
            value = data[0]
        else:
            value = (data[1]<<16)+data[0]

        if value != self.state:
            self.gateway.mqtt_publish(self.mqtt_topic(Entity.TOPIC_STATE), value)
            self.state = value

    @property
    def class_component(self):
        return "sensor"


class BlindEntity(Entity):

    def reset(self):
        super(BlindEntity, self).reset()

        self.pos = None
        self.target = 0
        self.t_up = None
        self.t_dn = None
        self.state = "stopped"

    def initialize(self):
        super(BlindEntity, self).initialize()

        if self.modbus_class.data_type != TYPE_REGISTER:
            raise Exception("BlindEntity only supports word data format")
        if self.modbus_class.data_size != 2:
            raise Exception("BlindEntity only supports two word data size: {}".format(self.modbus_class))

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
                value = 0 & 0x7F
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

        check_state = False
        if self.pos != new_pos:
            publish_state(Entity.TOPIC_STATE, new_pos)
            check_state = True
            self.pos = new_pos
        
        if self.target != new_target:
            publish_state("target", new_target)
            check_state = True
            self.target = new_target

        if self.t_up != new_t_up:
            publish_state("t_up", new_t_up)
            self.t_up = new_t_up
        
        if self.t_dn != new_t_dn:
            publish_state("t_dn", new_t_dn)
            self.t_dn = new_t_dn

        if check_state and self.pos is not None:
            new_state = self.state
            if self.target is None:
                if self.state != 'stopped':
                    new_state = 'stopped'
            elif self.pos < self.target:
                if self.state != 'opening':
                    new_state = 'opening'
            elif self.pos > self.target:
                if self.state != 'closing':
                    new_state = 'closing'
            elif self.pos == self.target and self.pos == 0:
                if self.state != 'closed':
                    new_state = 'closed'
            elif self.pos == self.target and self.pos == 100:
                if self.state != 'open':
                    new_state = 'open'
            elif self.pos == self.target:
                new_state = 'stopped'

            if self.state != new_state:
                self.state = new_state
                publish_state('state', self.state)

    def discovery_payload(self):
        return dict(
            **super(BlindEntity, self).discovery_payload(),
            set_position_topic="~/{}".format(Entity.TOPIC_SET),
            position_topic="~/{}".format(Entity.TOPIC_STATE)
        )

    @property
    def class_component(self):
        return "cover"
