from entity import ModbusClass, BlindEntity, BinarySensorEntity, ButtonEntity, RelayEntity, SensorEntity
from gateway import Gateway
from config import ENTITY_SETS, DEVICE

import time
from config import text_to_dict
import logging

entity_classes = {
    "binary_sensor": BinarySensorEntity,
    "button": ButtonEntity,
    "blind": BlindEntity,
    "relay": RelayEntity,
    "sensor": SensorEntity
}

# the gateway object
gw = Gateway(DEVICE)

# register all entity sets
[
    gw.register_entity_set(
        ModbusClass(
            eset.get("set_id"),
            read_offset=eset.get("read_offset", 0),
            write_offset=eset.get("write_offset", 0),
            read_only=eset.get("read_only", True),
            data_type=eset.get("data_type"),
            data_size=eset.get("data_size", 1),
            defaults=text_to_dict(eset.get("defaults", ""))
        ),
        entity_classes.get(eset.get("entity_type"), None),
        [text_to_dict(item) for item in eset.get("entities", [])],
        eset.get("entity_count", 0),
        poll_delay_ms=eset.get("poll_delay_ms", 250)
    ) for eset in ENTITY_SETS
]

# run the gateway loop
while True:
    gw.modbus_step()
    time.sleep(0.005)

