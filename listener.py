#!/usr/bin/env python3
"""
Standalone TCP socket server for receiving and decoding raw GT06-like GPS packets.
Forwards validated position data to the Flask API endpoint via HTTP POST.
Must be run separately from app.py.
"""

import socket
import threading
import datetime
import time
import math
import requests
from requests.adapters import HTTPAdapter, Retry
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Tuple, Dict
import struct
import sys

# --------------------- CONFIG ---------------------
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5001 # This is the port your GPS device should send data to

# Flask API endpoint (must match the route in app.py)
API_URL = "http://127.0.0.1:5000/api/update_location"

# Safety / filtering settings
MAX_REASONABLE_SPEED_KMH = 250.0  
MAX_DISTANCE_M = 5000.0          
MIN_TIME_DIFF_S = 2              

# HTTP forwarding pool and session for non-blocking API updates
HTTP_POOL = ThreadPoolExecutor(max_workers=5)
HTTP_SESSION = requests.Session()
# Set up retries for posting data to the Flask API
retries = Retry(total=5, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
HTTP_SESSION.mount('http://', HTTPAdapter(max_retries=retries))


# --------------------- UTILITIES ---------------------

def log(message):
    """Prints a timestamped message to the console."""
    sys.stdout.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    sys.stdout.flush()

def decode_bcd(data: bytes, length: int) -> str:
    """Decodes Binary Coded Decimal (BCD) data, used for IMEI."""
    s = ""
    for b in data[:length]:
        s += str((b >> 4) & 0x0F)
        s += str(b & 0x0F)
    return s.lstrip('0')

def distance(lat1, lon1, lat2, lon2):
    """Calculates haversine distance between two points in meters."""
    R = 6371000  # radius of Earth in meters
    phi_1 = math.radians(lat1)
    phi_2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi_1) * math.cos(phi_2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Simple cache for last valid position (IMEI -> (timestamp, latitude, longitude, speed))
last_positions: Dict[str, Tuple[datetime.datetime, float, float, float]] = {}


def validate_position(imei: str, timestamp: datetime.datetime, lat: float, lon: float, speed: float) -> bool:
    """Filters out noisy, zero, or unrealistic positions."""
    # Check for zero coordinates (often indicates no GPS fix or default data)
    if lat == 0.0 and lon == 0.0:
        log(f"Filter: Zero coordinates for {imei}")
        return False

    # Check for unrealistic speed
    if speed > MAX_REASONABLE_SPEED_KMH:
        log(f"Filter: Speed too high ({speed:.1f} km/h) for {imei}")
        return False

    current = (timestamp, lat, lon, speed)
    if imei in last_positions:
        prev_ts, prev_lat, prev_lon, prev_speed = last_positions[imei]
        
        time_diff = (timestamp - prev_ts).total_seconds()
        
        # Check distance traveled too quickly (teleporting)
        dist_m = distance(prev_lat, prev_lon, lat, lon)
        if dist_m > MAX_DISTANCE_M:
            log(f"Filter: Distance too large ({dist_m:.1f}m) in {time_diff:.1f}s for {imei}")
            return False

    # If all checks pass, update the last known position and accept the point
    last_positions[imei] = current
    return True


def post_location(payload: Dict):
    """Posts location data to the Flask API with retries."""
    imei = payload.get('imei', 'UNKNOWN')
    try:
        # Use a short timeout for non-blocking behavior
        r = HTTP_SESSION.post(API_URL, json=payload, timeout=5)
        r.raise_for_status()
        log(f"Sent update for {imei}: Status {r.status_code}")
    except requests.exceptions.RequestException as e:
        log(f"Failed to post location for {imei} to API: {e}")


# --------------------- PROTOCOL DECODING ---------------------

def decode_gps_location(data: bytes) -> Optional[Dict]:
    """Decodes the main GPS data packet (0x12)."""
    try:
        # Date: 6 bytes (YY MM DD HH MM SS)
        date_tuple = struct.unpack('>BBBBBB', data[0:6])
        # Note: Traccar often assumes 2000-based year.
        timestamp = datetime.datetime(2000 + date_tuple[0], date_tuple[1], date_tuple[2], 
                                      date_tuple[3], date_tuple[4], date_tuple[5])
        
        # Read lat/lon (Int32, multiplied by 1800000)
        lat_raw, lon_raw = struct.unpack('>ii', data[7:15])
        
        latitude = lat_raw / 1800000.0
        longitude = lon_raw / 1800000.0
        
        # Speed (1 byte, value in 0.5 knots)
        speed_half_knots = data[15]
        speed_kmh = speed_half_knots * 0.5 * 1.852 # 1 knot = 1.852 km/h
        
        # Course/Status (2 bytes)
        status_raw = struct.unpack('>H', data[16:18])[0]
        
        # Check for GPS Fix (Bit 13)
        gps_fixed = (status_raw >> 13) & 0x01
        
        if not gps_fixed:
            log("Warning: Position does not have a GPS fix (0x12)")
            # return None # Option: discard points without fix

        return {
            "timestamp": timestamp,
            "latitude": latitude,
            "longitude": longitude,
            "speed": speed_kmh,
        }
        
    except struct.error as e:
        log(f"Error decoding 0x12 packet: {e}")
        return None
    except Exception as e:
        log(f"General error in 0x12 decoding: {e}")
        return None


# --------------------- CLIENT HANDLER ---------------------

def handle_client(conn: socket.socket, addr: Tuple[str, int]):
    """Handles a single connection from a GPS device."""
    log(f"Connection opened {addr}")
    conn.settimeout(60) 
    imei: Optional[str] = None

    try:
        while True:
            # 1. Read Header (0x7878)
            header = conn.recv(2)
            if not header: break 
            if header != b'\x78\x78':
                log(f"Invalid header from {addr}: {header.hex()}. Closing.")
                break

            # 2. Read Packet Length (1 byte)
            length_byte = conn.recv(1)
            if not length_byte: break
            packet_len = length_byte[0]
            
            # 3. Read Command Code + Payload
            data_and_cmd = conn.recv(packet_len)
            if len(data_and_cmd) != packet_len:
                log("Incomplete data/command payload.")
                break
            
            # 4. Read Serial Number (2 bytes) and CRC (2 bytes)
            serial_crc = conn.recv(4)
            if len(serial_crc) != 4:
                log("Incomplete serial/CRC.")
                break
                
            command_code = data_and_cmd[0]
            payload = data_and_cmd[1:]
            serial_number = serial_crc[0:2]
            
            # --- Handle different Command Codes (Protocol Types) ---
            
            if command_code == 0x01: # Login packet
                imei_data = payload[:8]
                imei = decode_bcd(imei_data, 8)[:15] 
                log(f"Login 0x01 from {addr}: IMEI={imei}")
                
                # Send Login Response (0x7878 0x05 0x01 <Serial> <CRC>)
                response = b'\x78\x78\x05\x01' + serial_number + b'\x00\x00' 
                conn.sendall(response)
                log(f"Login ACK sent to {imei}")
                
            elif command_code == 0x12: # GPS Location Data
                if not imei: continue
                    
                location_data = decode_gps_location(payload)
                
                if location_data:
                    ts = location_data['timestamp']
                    lat = location_data['latitude']
                    lon = location_data['longitude']
                    sp = location_data['speed']
                    
                    if validate_position(imei, ts, lat, lon, sp):
                        payload_api = {
                            "imei": imei,
                            "latitude": lat,
                            "longitude": lon,
                            "speed": sp,
                            "timestamp": ts.isoformat() + "Z" 
                        }
                        log(f"Accept 0x12 {imei}: {lat:.6f},{lon:.6f} speed={sp:.1f} km/h (forwarding)")
                        HTTP_POOL.submit(post_location, payload_api)
                    else:
                        log(f"Reject 0x12 {imei}: Filtered out.")
                    
                # Send ACK (0x7878 0x05 0x12 <Serial> <CRC>)
                response = b'\x78\x78\x05\x12' + serial_number + b'\x00\x00'
                conn.sendall(response)
                
            elif command_code == 0x13: # Heartbeat packet
                if not imei: continue
                log(f"Heartbeat 0x13 from {imei}. Acknowledging.")
                
                # Send ACK (0x7878 0x05 0x13 <Serial> <CRC>)
                response = b'\x78\x78\x05\x13' + serial_number + b'\x00\x00'
                conn.sendall(response)

            elif command_code in [0x20, 0x79]: # Extended/LBS/WIFI Data (often includes location)
                if not imei: continue
                
                # Assume GPS data starts at offset 1 for simplicity in 0x20/0x79
                location_offset = 1 
                if len(payload) > location_offset:
                    location_data = decode_gps_location(payload[location_offset:])
                else:
                    location_data = None
                
                if location_data:
                    ts = location_data['timestamp']
                    lat = location_data['latitude']
                    lon = location_data['longitude']
                    sp = location_data['speed']
                    
                    if validate_position(imei, ts, lat, lon, sp):
                        payload_api = {
                            "imei": imei,
                            "latitude": lat,
                            "longitude": lon,
                            "speed": sp,
                            "timestamp": ts.isoformat() + "Z"
                        }
                        log(f"Accept EXT {imei}: {lat:.6f},{lon:.6f} km/h (forwarding)")
                        HTTP_POOL.submit(post_location, payload_api)

                # Send ACK 
                response = b'\x78\x78\x05' + command_code.to_bytes(1, 'big') + serial_number + b'\x00\x00'
                conn.sendall(response)

            else:
                log(f"Unhandled proto 0x{command_code:02x} from {imei}")

    except socket.timeout:
        log(f"Connection timed out {addr} (IMEI: {imei})")
    except Exception as e:
        log(f"Exception for {addr} (IMEI: {imei}): {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        log(f"Connection closed {addr} (IMEI: {imei})")

# --------------------- SERVER ---------------------\
def start_server():
    """Starts the TCP socket server to listen for GPS devices."""
    log(f"Listening for GPS devices on {SERVER_HOST}:{SERVER_PORT}")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SERVER_HOST, SERVER_PORT))
        s.listen(16)
        while True:
            conn, addr = s.accept()
            t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            t.start()
    except KeyboardInterrupt:
        log("Shutting down listener (KeyboardInterrupt)")
    except Exception as e:
        log(f"Server exception: {e}")
    finally:
        if 's' in locals():
            s.close()
            
if __name__ == '__main__':
    # Ensure all threads are killed on exit
    log(f"Starting GPS Listener...")
    start_server()
