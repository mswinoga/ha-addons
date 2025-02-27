#!/usr/bin/with-contenv bashio

# Environment variables configuration
export CONFIG_PATH=/data/options.json
export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")

# Logger configuration
export LOGLEVEL=${LOGLEVEL:-INFO}

# Mark as running in Home Assistant
export RUNNING_IN_HA=true

# Virtual environment activation
source /venv/bin/activate

echo "Starting Modbus-MQTT gateway with log level: $LOGLEVEL"
echo "Configuration: $CONFIG_PATH"
echo "MQTT Host: $MQTT_HOST"

# Run as Python module
python3 -c "import logging; logging.basicConfig(level='$LOGLEVEL'); from gateway.runner import main; main()"
