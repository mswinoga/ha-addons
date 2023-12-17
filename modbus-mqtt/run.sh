#!/usr/bin/with-contenv bashio

export CONFIG_PATH=/data/options.json
export MQTT_HOST=$(bashio::services mqtt "host")
export MQTT_USER=$(bashio::services mqtt "username")
export MQTT_PASSWORD=$(bashio::services mqtt "password")

source /venv/bin/activate
python3 /gateway/runner.py 
