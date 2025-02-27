#!/bin/bash
# Script for running the Modbus-MQTT gateway locally for testing

# Set environment variables for local testing
# You can override these by setting them before running this script
export CONFIG_PATH=${CONFIG_PATH:-"$(pwd)/gateway/test_config.json"}
export MQTT_HOST=${MQTT_HOST:-"localhost"}
export MQTT_USER=${MQTT_USER:-"test"}
export MQTT_PASSWORD=${MQTT_PASSWORD:-"test"}
export LOGLEVEL=${LOGLEVEL:-"INFO"}

echo "Starting Modbus-MQTT gateway locally with log level: $LOGLEVEL"
echo "Configuration: $CONFIG_PATH"
echo "MQTT Host: $MQTT_HOST"

source .venv/bin/activate
# Run the gateway
python3 -m gateway.runner