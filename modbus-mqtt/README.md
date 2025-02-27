# Modbus-MQTT Gateway

A Home Assistant addon that bridges Modbus devices with MQTT, allowing integration with Home Assistant.

## Features

- Connects Modbus TCP/UDP devices to MQTT
- Supports various entity types (binary sensors, buttons, relays, sensors, blinds)
- Automatic Home Assistant discovery
- Configurable polling intervals

## Usage

### As a Home Assistant Addon

1. Install the addon from the Home Assistant Addon Store
2. Configure the addon through the Home Assistant UI
3. Start the addon

### Local Development and Testing

For local development and testing, you can run the gateway without Home Assistant:

1. Make sure you have Python 3 installed with the required dependencies:
   ```
   pip install pymodbus==2.5.3 paho-mqtt Unidecode
   ```

2. Run the gateway using the provided script:
   ```
   ./run_local.sh
   ```

3. You can customize the environment variables to change the configuration:
   ```
   CONFIG_PATH=/path/to/your/config.json MQTT_HOST=your-mqtt-broker MQTT_USER=username MQTT_PASSWORD=password LOGLEVEL=DEBUG ./run_local.sh
   ```

## Running Tests

To run the unit tests:

```
python -m unittest discover -s gateway/tests
```

## Configuration

The gateway is configured using a JSON file. See `gateway/test_config.json` for an example configuration.

### Configuration Options

- `device`: Information about the device (identifiers, name, model, manufacturer)
- `modbus_host`: Modbus server host address
- `modbus_port`: Modbus server port (default: 502)
- `discovery_prefix`: Home Assistant discovery prefix (default: "homeassistant")
- `entity_sets`: Array of entity sets to configure

## License

This project is licensed under the MIT License - see the LICENSE file for details.
