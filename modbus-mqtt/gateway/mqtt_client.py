"""
MQTT client for Modbus-MQTT gateway.
Implements communication with MQTT broker.
"""
import logging
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

from .interfaces import MQTTClientInterface, MQTTMessage

logger = logging.getLogger('mqtt_client')


class MQTTError(Exception):
    """Exception for MQTT communication errors."""
    pass


class MQTTClient(MQTTClientInterface):
    """
    MQTT client handling broker communication.
    Implements publishing and topic subscription.
    """
    
    def __init__(
        self, 
        client_id: str, 
        host: str, 
        port: int = 1883, 
        username: Optional[str] = None, 
        password: Optional[str] = None, 
        availability_topic: Optional[str] = None
    ):
        """
        Initializes MQTT client.
        
        Args:
            client_id: MQTT client identifier
            host: MQTT broker host address
            port: MQTT broker port (default 1883)
            username: Username for authentication (optional)
            password: Password for authentication (optional)
            availability_topic: Availability topic for last will (optional)
        """
        self.client_id = client_id
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.availability_topic = availability_topic
        
        # Connection state
        self._is_connected = False
        self._last_connection_attempt = 0
        self._reconnect_delay = 5  # Reconnection delay in seconds
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=client_id)
        
        # Configure authentication if credentials provided
        if username and password:
            self.client.username_pw_set(username=username, password=password)
        
        # Configure last will testament if availability topic provided
        if availability_topic:
            self.client.will_set(
                topic=availability_topic,
                payload="offline", 
                qos=1, 
                retain=True
            )
        
        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # Topic to callback mapping
        self._topic_callbacks: Dict[str, Callable[[MQTTMessage], None]] = {}
        
        logger.info(f"Initialized MQTT client {client_id} for {host}:{port}")
    
    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int) -> None:
        """
        Callback called on connection to MQTT broker.
        
        Args:
            client: MQTT client
            userdata: User data
            flags: Connection flags
            rc: Result code
        """
        if rc == 0:
            self._is_connected = True
            logger.info(f"Connected to MQTT broker {self.host}:{self.port}")
            
            # Re-subscribe to all topics after reconnect
            for topic in self._topic_callbacks.keys():
                self.client.subscribe(topic)
                logger.debug(f"Re-subscribing to topic: {topic}")
            
            # Publish online status
            if self.availability_topic:
                self.publish(self.availability_topic, "online", retain=True)
                
        else:
            self._is_connected = False
            logger.error(f"Cannot connect to MQTT broker, code: {rc}")
    
    def _on_disconnect(self, client: mqtt.Client, userdata: Any, rc: int) -> None:
        """
        Callback called on disconnection from MQTT broker.
        
        Args:
            client: MQTT client
            userdata: User data
            rc: Result code
        """
        self._is_connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
    
    def _on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        """
        Callback called on message receipt from MQTT broker.
        
        Args:
            client: MQTT client
            userdata: User data
            msg: Received MQTT message
        """
        topic = msg.topic
        
        # Call appropriate callback for topic
        if topic in self._topic_callbacks:
            try:
                self._topic_callbacks[topic](msg)
            except Exception as e:
                logger.error(f"Error processing MQTT message for topic {topic}: {str(e)}")
        else:
            logger.warning(f"Received message for unhandled topic: {topic}")
    
    def connect(self) -> bool:
        """
        Establishes connection with MQTT broker.
        
        Returns:
            True if connection was established, False otherwise
        """
        # Check if we're not trying to connect too frequently
        current_time = time.time()
        if current_time - self._last_connection_attempt < self._reconnect_delay:
            return False
        
        self._last_connection_attempt = current_time
        
        try:
            # Connect to broker
            result = self.client.connect(self.host, self.port)
            if result == mqtt.MQTT_ERR_SUCCESS:
                # Start message handling thread
                self.client.loop_start()
                return True
            else:
                logger.error(f"Error connecting to MQTT broker, code: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {str(e)}")
            return False
    
    def is_connected(self) -> bool:
        """
        Checks if client is connected to MQTT broker.
        
        Returns:
            True if client is connected, False otherwise
        """
        return self._is_connected
    
    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """
        Publishes message to specified MQTT topic.
        
        Args:
            topic: MQTT topic
            payload: Message content
            retain: Whether message should be retained by broker
            
        Raises:
            MQTTError: When publishing error occurs
        """
        try:
            # Convert payload to string if it's not string or bytes
            if not isinstance(payload, (str, bytes)):
                payload = str(payload)
            
            logger.debug(f"Publishing: {topic} = {payload} (retain={retain})")
            result = self.client.publish(topic, payload, retain=retain)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise MQTTError(f"MQTT publish error, code: {result.rc}")
                
        except Exception as e:
            logger.error(f"Error publishing to topic {topic}: {str(e)}")
            raise MQTTError(f"MQTT publish error: {str(e)}")
    
    def subscribe(self, topic: str, callback: Callable[[MQTTMessage], None]) -> None:
        """
        Subscribes to MQTT topic.
        
        Args:
            topic: MQTT topic to subscribe to
            callback: Function called when message is received
            
        Raises:
            MQTTError: When subscription error occurs
        """
        try:
            logger.debug(f"Subscribing to topic: {topic}")
            
            # Save callback for topic
            self._topic_callbacks[topic] = callback
            
            # Perform subscription if connected
            if self.is_connected():
                result = self.client.subscribe(topic)
                
                if result[0] != mqtt.MQTT_ERR_SUCCESS:
                    raise MQTTError(f"MQTT subscription error, code: {result[0]}")
                    
        except Exception as e:
            logger.error(f"Error subscribing to topic {topic}: {str(e)}")
            raise MQTTError(f"MQTT subscription error: {str(e)}")
    
    def close(self) -> None:
        """Closes connection to MQTT broker."""
        try:
            # Publish offline status before closing if connected
            if self.is_connected() and self.availability_topic:
                self.publish(self.availability_topic, "offline", retain=True)
            
            # Stop message handling thread
            self.client.loop_stop()
            
            # Disconnect from broker
            self.client.disconnect()
            
            logger.info("Closed MQTT connection")
            
        except Exception as e:
            logger.error(f"Error closing MQTT connection: {str(e)}")