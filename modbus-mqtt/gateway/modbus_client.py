"""
Modbus client for Modbus-MQTT gateway.
Implements communication with Modbus TCP and UDP devices.
"""
import logging
import time
from typing import Any, List, Optional, Union, Tuple
import traceback

from pymodbus.client.sync import ModbusTcpClient, ModbusUdpClient
from pymodbus.bit_write_message import WriteSingleCoilRequest, WriteMultipleCoilsRequest
from pymodbus.bit_read_message import  ReadSingleCoilRequest, ReadMultipleCoilsRequest
from pymodbus.register_write_message import WriteSingleRegisterRequest, WriteMultipleRegistersRequest
from pymodbus.register_read_message import ReadSingleRegisterRequest, ReadMultipleRegistersRequest
from pymodbus.exceptions import ModbusException, ConnectionException
from pymodbus.constants import Defaults

from .interfaces import ModbusClientInterface

logger = logging.getLogger('modbus_client')


class ModbusError(Exception):
    """Exception for Modbus communication errors."""
    pass


class ModbusClient(ModbusClientInterface):
    """
    Modbus client handling TCP and UDP communication.
    Implements read and write operations for coils and registers.
    """
    
    def __init__(self, host: str, port: int = 502, timeout: float = 1.0, retries: int = 3):
        """
        Initializes Modbus client.
        
        Args:
            host: Modbus host address
            port: Modbus port (default 502)
            timeout: Response timeout in seconds
            retries: Number of retry attempts on error
        """
        # Configure basic parameters
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        
        # Global pymodbus configuration
        Defaults.RetryOnEmpty = True
        Defaults.Timeout = timeout
        Defaults.Retries = retries
        Defaults.Reconnects = retries
        
        # Initialize clients
        self.tcp_client = ModbusTcpClient(host=host, port=port)
        self.udp_client = ModbusUdpClient(host=host, port=port)
        
        # Connection status
        self._last_connection_error = 0
        self._reconnect_delay = 5  # Reconnection delay in seconds
        
        logger.info(f"Initialized Modbus client for {host}:{port}")
    
    def connect(self) -> bool:
        """
        Establishes connection with Modbus server.
        
        Returns:
            True if connection was established, False otherwise
        """
        # Check if we're not trying to connect too frequently after error
        current_time = time.time()
        if current_time - self._last_connection_error < self._reconnect_delay:
            return False
        
        try:
            # Connect both clients
            tcp_result = self.tcp_client.connect()
            udp_result = self.udp_client.connect()
            
            if tcp_result and udp_result:
                logger.info(f"Connected to Modbus server {self.host}:{self.port}")
                return True
            else:
                logger.warning(
                    f"Unable to connect to Modbus server {self.host}:{self.port} "
                    f"(TCP: {tcp_result}, UDP: {udp_result})"
                )
                return False
                
        except Exception as e:
            self._last_connection_error = current_time
            logger.error(f"Error connecting to Modbus server: {str(e)}")
            return False
    
    def is_connected(self) -> bool:
        """
        Checks if client is connected to Modbus server.
        
        Returns:
            True if client is connected, False otherwise
        """
        return self.tcp_client.is_socket_open()
    
    def _execute_with_retry(self, client: Any, request: Any) -> Any:
        """
        Executes Modbus request with retry handling.
        
        Args:
            client: Modbus client (TCP or UDP)
            request: Modbus request
            
        Returns:
            Response from Modbus device
            
        Raises:
            ModbusError: When communication error occurs
        """
        # Ensure we're connected
        if not client.is_socket_open():
            client.connect()
        
        # Try to execute request with specified number of retries
        for attempt in range(self.retries + 1):
            try:
                response = client.execute(request)
                
                # Check for error in response
                if hasattr(response, 'isError') and response.isError():
                    raise ModbusError(f"Modbus error: {response}")
                
                return response
                
            except ConnectionException as e:
                logger.warning(f"Modbus connection error (attempt {attempt+1}/{self.retries+1}): {str(e)}")
                # Try to reconnect
                client.connect()
                
            except Exception as e:
                if attempt < self.retries:
                    logger.warning(f"Modbus error (attempt {attempt+1}/{self.retries+1}): {str(e)}")

                else:
                    # Last attempt failed
                    self._last_connection_error = time.time()
                    raise ModbusError(f"Modbus error after {self.retries+1} attempts: {str(e)}")
        
        # This code should never be reached
        raise ModbusError("Unexpected error in _execute_with_retry")
    
    def read_coils(self, address: int, count: int) -> List[bool]:
        """
        Reads coils from Modbus device.
        
        Args:
            address: Starting address
            count: Number of coils to read
            
        Returns:
            List of coil values
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Reading coils: address={address}, count={count}")
            request = ReadMultipleCoilcRequest(address=address, count=count)
            response = self._execute_with_retry(self.udp_client, request)
            
            if response and hasattr(response, 'bits'):
                return response.bits[:count]  # Trim to requested count of coils
            else:
                raise ModbusError(f"Invalid response while reading coils: {response}")
                
        except Exception as e:
            raise ModbusError(f"Error reading coils: {str(e)}")
    
    def read_holding_registers(self, address: int, count: int) -> List[int]:
        """
        Reads holding registers from Modbus device.
        
        Args:
            address: Starting address
            count: Number of registers to read
            
        Returns:
            List of register values
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Reading registers: address={address}, count={count}")
            response = self._execute_with_retry(
                self.udp_client,
                self.udp_client.read_holding_registers(address=address, count=count)
            )
            
            if response and hasattr(response, 'registers'):
                return response.registers[:count]  # Trim to requested count of registers
            else:
                raise ModbusError(f"Invalid response while reading registers: {response}")
                
        except Exception as e:
            raise ModbusError(f"Error reading registers: {str(e)}")
    
    def write_coil(self, address: int, value: bool) -> None:
        """
        Writes single coil to Modbus device.
        
        Args:
            address: Coil address
            value: Value to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Writing coil: address={address}, value={value}")
            request = WriteSingleCoilRequest(address=address, value=value)
            self._execute_with_retry(self.tcp_client, request)
            
        except Exception as e:
            raise ModbusError(f"Error writing coil: {str(e)}")
    
    def write_coils(self, address: int, values: List[bool]) -> None:
        """
        Writes multiple coils to Modbus device.
        
        Args:
            address: Starting address
            values: List of values to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Writing multiple coils: address={address}, values={values}")
            request = WriteMultipleCoilsRequest(address=address, values=values)
            self._execute_with_retry(self.tcp_client, request)
            
        except Exception as e:
            raise ModbusError(f"Error writing multiple coils: {str(e)}")
    
    def write_register(self, address: int, value: int) -> None:
        """
        Writes single register to Modbus device.
        
        Args:
            address: Register address
            value: Value to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Writing register: address={address}, value={value}")
            request = WriteSingleRegisterRequest(address=address, value=value)
            self._execute_with_retry(self.tcp_client, request)
            
        except Exception as e:
            raise ModbusError(f"Error writing register: {str(e)}")
    
    def write_registers(self, address: int, values: List[int]) -> None:
        """
        Writes multiple registers to Modbus device.
        
        Args:
            address: Starting address
            values: List of values to write
            
        Raises:
            ModbusError: When communication error occurs
        """
        try:
            logger.debug(f"Writing multiple registers: address={address}, values={values}")
            request = WriteMultipleRegistersRequest(address=address, values=values)
            self._execute_with_retry(self.tcp_client, request)
            
        except Exception as e:
            raise ModbusError(f"Error writing multiple registers: {str(e)}")
    
    def close(self) -> None:
        """Closes Modbus client connections."""
        self.tcp_client.close()
        self.udp_client.close()
        logger.info("Closed Modbus connections")