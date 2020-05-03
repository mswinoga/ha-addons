#!/usr/bin/with-contenv bashio

CONFIG_PATH=/data/options.json

MQTT_HOST=$(bashio::services mqtt "host")
MQTT_USER=$(bashio::services mqtt "username")
MQTT_PASSWORD=$(bashio::services mqtt "password")

python3 /gateway/runner.py

