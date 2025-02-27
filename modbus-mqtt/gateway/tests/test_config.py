"""
Testy jednostkowe dla modułu config.py
"""
import json
import os
import unittest
from unittest import TestCase
from unittest.mock import patch, mock_open

from gateway.config import text_to_dict


class ConfigUtilsTests(TestCase):
    """Testy dla funkcji pomocniczych w module config"""
    
    def test_text_to_dict_empty(self):
        """Test konwersji pustego tekstu"""
        result = text_to_dict("")
        self.assertEqual(result, {})
    
    def test_text_to_dict_single_key_value(self):
        """Test konwersji pojedynczej pary klucz=wartość"""
        result = text_to_dict("key=value")
        self.assertEqual(result, {"key": "value"})
    
    def test_text_to_dict_multiple_pairs(self):
        """Test konwersji wielu par klucz=wartość"""
        result = text_to_dict("key1=value1,key2=value2,key3=value3")
        self.assertEqual(result, {
            "key1": "value1",
            "key2": "value2",
            "key3": "value3"
        })
    
    def test_text_to_dict_with_spaces(self):
        """Test konwersji tekstu ze spacjami"""
        result = text_to_dict("key1 = value1, key2 = value2")
        self.assertEqual(result, {
            "key1": "value1",
            "key2": "value2"
        })
    
    def test_text_to_dict_with_empty_value(self):
        """Test konwersji klucza bez wartości"""
        result = text_to_dict("key1=,key2=value2")
        self.assertEqual(result, {
            "key1": "",
            "key2": "value2"
        })
    
    def test_text_to_dict_with_empty_key(self):
        """Test konwersji pustego klucza"""
        result = text_to_dict("=value1,key2=value2")
        self.assertEqual(result, {
            "key2": "value2"
        })
    
    def test_text_to_dict_with_empty_segments(self):
        """Test konwersji z pustymi segmentami"""
        result = text_to_dict("key1=value1,,key3=value3")
        self.assertEqual(result, {
            "key1": "value1",
            "key3": "value3"
        })
    
    def test_text_to_dict_with_equals_in_value(self):
        """Test konwersji z znakiem '=' w wartości"""
        result = text_to_dict("key1=value=with=equals,key2=value2")
        self.assertEqual(result, {
            "key1": "value=with=equals",
            "key2": "value2"
        })


@patch.dict(os.environ, {
    "CONFIG_PATH": "/path/to/config.json",
    "MQTT_HOST": "test.mosquitto.org",
    "MQTT_USER": "testuser",
    "MQTT_PASSWORD": "testpass"
})
class ConfigLoadingTests(TestCase):
    """Testy dla funkcji ładowania konfiguracji"""
    
    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "device": {
            "identifiers": "Test PLC",
            "name": "Test Device",
            "model": "Test-123",
            "manufacturer": "TestCorp"
        },
        "modbus_host": "192.168.1.100",
        "modbus_port": 502,
        "entity_sets": []
    }))
    @patch("os.path.exists", return_value=True)
    def test_load_config_minimal(self, mock_exists, mock_file):
        """Test ładowania minimalnej konfiguracji"""
        # Importuj load_config tutaj, aby nie uruchamiać jej przy imporcie modułu
        from gateway.config import load_config
        
        config = load_config()
        
        # Sprawdź, czy konfiguracja została poprawnie załadowana
        self.assertEqual(config.modbus_host, "192.168.1.100")
        self.assertEqual(config.modbus_port, 502)
        self.assertEqual(config.mqtt_host, "test.mosquitto.org")
        self.assertEqual(config.mqtt_user, "testuser")
        self.assertEqual(config.mqtt_password, "testpass")
        self.assertEqual(config.device.name, "Test Device")
        self.assertEqual(len(config.entity_sets), 0)
    
    @patch("builtins.open", new_callable=mock_open, read_data=json.dumps({
        "device": {
            "identifiers": "Test PLC",
            "name": "Test Device",
            "model": "Test-123",
            "manufacturer": "TestCorp"
        },
        "modbus_host": "192.168.1.100",
        "modbus_port": 502,
        "discovery_prefix": "ha",
        "entity_sets": [
            {
                "set_id": "test_set",
                "entity_type": "binary_sensor",
                "entity_count": 2,
                "entities": ["name=Test1", "name=Test2"],
                "data_type": "coil",
                "poll_delay_ms": 100
            }
        ]
    }))
    @patch("os.path.exists", return_value=True)
    def test_load_config_with_entities(self, mock_exists, mock_file):
        """Test ładowania konfiguracji z encjami"""
        # Importuj load_config tutaj, aby nie uruchamiać jej przy imporcie modułu
        from gateway.config import load_config
        
        config = load_config()
        
        # Sprawdź, czy konfiguracja została poprawnie załadowana
        self.assertEqual(config.discovery_prefix, "ha")
        self.assertEqual(len(config.entity_sets), 1)
        
        # Sprawdź konfigurację zestawu encji
        entity_set = config.entity_sets[0]
        self.assertEqual(entity_set.set_id, "test_set")
        self.assertEqual(entity_set.entity_type, "binary_sensor")
        self.assertEqual(entity_set.entity_count, 2)
        self.assertEqual(entity_set.entities, ["name=Test1", "name=Test2"])
        self.assertEqual(entity_set.data_type, "coil")
        self.assertEqual(entity_set.poll_delay_ms, 100)
    
    @patch("os.path.exists", return_value=False)
    def test_load_config_file_not_found(self, mock_exists):
        """Test ładowania konfiguracji gdy plik nie istnieje"""
        # Importuj load_config tutaj, aby nie uruchamiać jej przy imporcie modułu
        from gateway.config import load_config
        
        with self.assertRaises(FileNotFoundError):
            load_config()
    
    def test_load_config_missing_env_vars(self):
        """Test ładowania konfiguracji bez wymaganych zmiennych środowiskowych"""
        # Importuj load_config tutaj, aby nie uruchamiać jej przy imporcie modułu
        from gateway.config import load_config
        
        # Save original environment
        original_environ = os.environ.copy()
        
        try:
            # Clear environment variables
            os.environ.clear()
            os.environ["CONFIG_PATH"] = "/path/to/config.json"
            
            # Mock os.path.exists to return True
            with patch("os.path.exists", return_value=True):
                # Mock open to return valid JSON
                mock_data = json.dumps({
                    "device": {
                        "identifiers": "Test PLC",
                        "name": "Test Device",
                        "model": "Test-123",
                        "manufacturer": "TestCorp"
                    },
                    "modbus_host": "192.168.1.100",
                    "modbus_port": 502,
                    "entity_sets": []
                })
                
                with patch("builtins.open", new_callable=mock_open, read_data=mock_data):
                    # Test should raise KeyError for missing environment variables
                    with self.assertRaises(KeyError):
                        load_config()
        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_environ)


if __name__ == '__main__':
    unittest.main()