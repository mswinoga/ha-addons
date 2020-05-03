from entity import ModbusClass, BlindEntity, BitEntity, ButtonEntity, LightRelayEntity
from gateway import Gateway

import time
import logging

logger = logging.getLogger('runner')
logger.setLevel(logging.DEBUG)

gw = Gateway()
gw.register_entity_set(
    ModbusClass("di"),
    ButtonEntity,
    14*8,
    time_wait=10
)
gw.register_entity_set(
    ModbusClass("meter", read_offset=112),
    BitEntity,
    1*8,
    time_wait=1000
)
gw.register_entity_set(
    ModbusClass("do", read_offset=512, write_supported=True),
    LightRelayEntity,
    19*8,
    time_wait=250
)
gw.register_entity_set(
    ModbusClass("blind", read_offset=0x3100, write_offset=0x3100, write_supported=True, width=2, unit=16),
    BlindEntity,
    20,
    time_wait=750
)

while True:
    gw.modbus_step()
    time.sleep(0.005)

