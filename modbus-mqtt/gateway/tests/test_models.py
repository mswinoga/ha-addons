"""
Testy jednostkowe dla modułu models.py
"""
import unittest
from unittest import TestCase

from gateway.models import (
    DeviceInfo,
    ModbusClassConfig,
    EntityDefinition,
    TYPE_COIL,
    TYPE_REGISTER
)


class DeviceInfoTests(TestCase):
    """Testy dla klasy DeviceInfo"""
    
    def test_initialization(self):
        """Test inicjalizacji DeviceInfo"""
        device = DeviceInfo(
            identifiers="test_id",
            name="Test Device",
            model="Test Model",
            manufacturer="Test Manufacturer"
        )
        
        self.assertEqual(device.identifiers, "test_id")
        self.assertEqual(device.name, "Test Device")
        self.assertEqual(device.model, "Test Model")
        self.assertEqual(device.manufacturer, "Test Manufacturer")
    
    def test_to_dict(self):
        """Test konwersji DeviceInfo do słownika"""
        device = DeviceInfo(
            identifiers="test_id",
            name="Test Device",
            model="Test Model",
            manufacturer="Test Manufacturer"
        )
        
        device_dict = device.to_dict()
        
        self.assertEqual(device_dict["identifiers"], ["test_id"])
        self.assertEqual(device_dict["name"], "Test Device")
        self.assertEqual(device_dict["model"], "Test Model")
        self.assertEqual(device_dict["manufacturer"], "Test Manufacturer")


class ModbusClassConfigTests(TestCase):
    """Testy dla klasy ModbusClassConfig"""
    
    def test_default_initialization(self):
        """Test inicjalizacji ModbusClassConfig z domyślnymi wartościami"""
        modbus_class = ModbusClassConfig(name="test_class")
        
        self.assertEqual(modbus_class.name, "test_class")
        self.assertEqual(modbus_class.data_type, TYPE_COIL)
        self.assertEqual(modbus_class.data_size, 1)
        self.assertEqual(modbus_class.read_offset, 0)
        self.assertEqual(modbus_class.write_offset, 0)
        self.assertTrue(modbus_class.read_only)
        self.assertEqual(modbus_class.defaults, {})
    
    def test_custom_initialization(self):
        """Test inicjalizacji ModbusClassConfig z niestandardowymi wartościami"""
        modbus_class = ModbusClassConfig(
            name="test_class",
            data_type=TYPE_REGISTER,
            data_size=2,
            read_offset=100,
            write_offset=200,
            read_only=False,
            defaults={"key": "value"}
        )
        
        self.assertEqual(modbus_class.name, "test_class")
        self.assertEqual(modbus_class.data_type, TYPE_REGISTER)
        self.assertEqual(modbus_class.data_size, 2)
        self.assertEqual(modbus_class.read_offset, 100)
        self.assertEqual(modbus_class.write_offset, 200)
        self.assertFalse(modbus_class.read_only)
        self.assertEqual(modbus_class.defaults, {"key": "value"})
    
    def test_string_representation(self):
        """Test reprezentacji tekstowej ModbusClassConfig"""
        modbus_class = ModbusClassConfig(name="test_class")
        
        string_repr = str(modbus_class)
        
        self.assertIn("test_class", string_repr)
        self.assertIn(TYPE_COIL, string_repr)
        self.assertIn("data_size=1", string_repr)


class EntityDefinitionTests(TestCase):
    """Testy dla klasy EntityDefinition"""
    
    def test_default_initialization(self):
        """Test inicjalizacji EntityDefinition z domyślnymi wartościami"""
        entity_def = EntityDefinition()
        
        self.assertIsNone(entity_def.name)
        self.assertIsNone(entity_def.component)
        self.assertIsNone(entity_def.device_class)
        self.assertIsNone(entity_def.payload_on)
        self.assertIsNone(entity_def.payload_off)
    
    def test_custom_initialization(self):
        """Test inicjalizacji EntityDefinition z niestandardowymi wartościami"""
        entity_def = EntityDefinition(
            name="Test Entity",
            component="switch",
            device_class="outlet",
            payload_on="ON",
            payload_off="OFF"
        )
        
        self.assertEqual(entity_def.name, "Test Entity")
        self.assertEqual(entity_def.component, "switch")
        self.assertEqual(entity_def.device_class, "outlet")
        self.assertEqual(entity_def.payload_on, "ON")
        self.assertEqual(entity_def.payload_off, "OFF")
    
    def test_from_dict(self):
        """Test tworzenia EntityDefinition ze słownika"""
        data = {
            "name": "Test Entity",
            "component": "switch",
            "device_class": "outlet",
            "payload_on": "ON",
            "payload_off": "OFF"
        }
        
        entity_def = EntityDefinition.from_dict(data)
        
        self.assertEqual(entity_def.name, "Test Entity")
        self.assertEqual(entity_def.component, "switch")
        self.assertEqual(entity_def.device_class, "outlet")
        self.assertEqual(entity_def.payload_on, "ON")
        self.assertEqual(entity_def.payload_off, "OFF")
    
    def test_to_dict(self):
        """Test konwersji EntityDefinition do słownika"""
        entity_def = EntityDefinition(
            name="Test Entity",
            component="switch",
            device_class="outlet",
            payload_on="ON",
            payload_off="OFF"
        )
        
        entity_dict = entity_def.to_dict()
        
        self.assertEqual(entity_dict["name"], "Test Entity")
        self.assertEqual(entity_dict["component"], "switch")
        self.assertEqual(entity_dict["device_class"], "outlet")
        self.assertEqual(entity_dict["payload_on"], "ON")
        self.assertEqual(entity_dict["payload_off"], "OFF")
    
    def test_is_valid(self):
        """Test sprawdzania poprawności EntityDefinition"""
        # Encja bez nazwy - niepoprawna
        entity_def1 = EntityDefinition()
        self.assertFalse(entity_def1.is_valid)
        
        entity_def2 = EntityDefinition(name="")
        self.assertFalse(entity_def2.is_valid)
        
        # Encja z nazwą - poprawna
        entity_def3 = EntityDefinition(name="Test Entity")
        self.assertTrue(entity_def3.is_valid)
    
    def test_discovery_uid(self):
        """Test generowania UID dla discovery"""
        # Pusta encja
        entity_def1 = EntityDefinition()
        self.assertIsNone(entity_def1.discovery_uid)
        
        # Encja z prostą nazwą
        entity_def2 = EntityDefinition(name="Test Entity")
        self.assertEqual(entity_def2.discovery_uid, "test_entity")
        
        # Encja z polskimi znakami i spacjami
        entity_def3 = EntityDefinition(name="Łazienka Górna")
        self.assertEqual(entity_def3.discovery_uid, "lazienka_gorna")


if __name__ == '__main__':
    unittest.main()