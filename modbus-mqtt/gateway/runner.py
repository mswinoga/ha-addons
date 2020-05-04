from entity import ModbusClass, BlindEntity, BitEntity, ButtonEntity, LightRelayEntity
from gateway import Gateway
from config import ENTITY_SETS

import time
import logging

entity_classes = {
    "binary_input": BitEntity,
    "button": BitEntity,
    "blind": BlindEntity,
    "light_relay": LightRelayEntity
}

# the gateway object
gw = Gateway()

# register all entity sets
[
    gw.register_entity_set(
        ModbusClass(
            entity.get("set_id"),
            read_offset=entity.get("read_offset", 0),
            write_offset=entity.get("write_offset", 0),
            read_only=entity.get("read_only", True),
            data_type=entity.get("data_type"),
            data_size=entity.get("data_size")
        ),
        entity_classes.get(entity.get("entity_type"), None),
        entity.get("entity_count", 1),
        poll_delay_ms=entity.get("poll_delay_ms", 250)
    ) for entity in ENTITY_SETS
]

# run the gateway loop
while True:
    gw.modbus_step()
    time.sleep(0.005)

