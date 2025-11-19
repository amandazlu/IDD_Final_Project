"""
MQTT Message Viewer
Lightweight debugging tool to view all MQTT messages in real-time
"""

from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import paho.mqtt.client as mqtt
from datetime import datetime
from collections import deque
import json

import random
import pygame
import sys
import os
from time import sleep
from functools import lru_cache

import threading
import time

chart_data = None
chart_thread = None
chart_playing = False
LEAD_TIME = 3  # seconds early

pending_notes = []
HIT_WINDOW = 0.150   # +/- 150ms

# Initialize once when the module loads
pygame.mixer.init()
print("[OK] Audio system ready")

CHANNELS = {
    'pan': pygame.mixer.Channel(0),
    'cutting_board': pygame.mixer.Channel(1),
    'mixing_bowl': pygame.mixer.Channel(2)
}

# Global playback state
playing_state = {
    'pan': False,
    'cutting_board': False,
    'mixing_bowl': False
}

# Initialize random target values for utensils
random_pan_target = random.randint(10, 10000) 
random_mixing_bowl_target = random.randint(0, 1023)
random_cutting_board_target = random.randint(0, 2)
# add more 

print(f"[INIT] Pan target distance set to: {random_pan_target}")
print(f"[INIT] Mixing Bowl target X set to: {random_mixing_bowl_target}")
print(f"[INIT] Cutting Board target set to: {random_cutting_board_target}")


# Sound configuration: utensil -> (file_path, condition_function)
# Sound configuration: utensil -> (file_path, condition_function)
SOUND_RULES = {
    'pan': {
        'file': 'sounds/pan_sizzle.mp3',
        'target_value': random_pan_target, 
        'should_play': lambda data: data.get('distance', 0) > SOUND_RULES['pan']['target_value'],
        'generate_target': lambda: random.randint(1, 20000) 
    },
    'cutting_board': {
        'file': 'sounds/knife-stab-pull.mp3',
        'target_value': random_cutting_board_target,
        'should_play': lambda data: len(data) > 0 and data[str(SOUND_RULES['cutting_board']['target_value'])] == 1,
        'generate_target': lambda: random.randint(0, 2)
    },
    'mixing_bowl': {
        'file': 'sounds/whisking.mp3',
        'target_value': random_mixing_bowl_target, 
        'should_play': lambda data: data.get('x', 0) > SOUND_RULES['mixing_bowl']['target_value'],
        'generate_target': lambda: random.randint(0, 1023)
    }
}


app = Flask(__name__)
app.config['SECRET_KEY'] = 'mqtt-viewer-2025'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Store recent messages (limited to prevent memory issues)
MAX_MESSAGES = 100
recent_messages = deque(maxlen=MAX_MESSAGES)

# MQTT Configuration
MQTT_BROKER = 'farlab.infosci.cornell.edu'
MQTT_PORT = 1883
MQTT_TOPIC = 'IDD/kitchen-instrument'  # Subscribe to all IDD topics
MQTT_USERNAME = 'idd'
MQTT_PASSWORD = 'device@theFarm'

mqtt_client = None

def broadcast_to_web_client(message, topic):
    # Add to recent messages
    recent_messages.append(message)

    # Broadcast to all connected web clients
    socketio.emit(topic, message, namespace='/')

def on_connect(client, userdata, flags, rc):
    """MQTT connected"""
    if rc == 0:
        print(f'MQTT connected to {MQTT_BROKER}:{MQTT_PORT}')
        client.subscribe(MQTT_TOPIC)
        print(f'Subscribed to {MQTT_TOPIC}')
    else:
        print(f'MQTT connection failed: {rc}')


def on_message(client, userdata, msg):
    """MQTT message received - broadcast to web clients"""
    global playing_state
    try:
        # Try to parse as JSON, otherwise use as plain text
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            payload_str = json.dumps(payload, indent=2)
            is_json = True
        except:
            payload_str = msg.payload.decode('utf-8', errors='replace')
            is_json = False
        
        # Create message object
        message = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
            'topic': msg.topic,
            'payload': payload_str,
            'is_json': is_json
        }

        broadcast_to_web_client(message, 'mqtt_message')

        # Play sounds based on utensil and data
        utensil = payload.get('utensil', 'unknown') if is_json else 'unknown'
        data = payload.get('data', {}) if is_json else {}
        
        # Get rule for this utensil
        rule = SOUND_RULES.get(utensil)
        if not rule:
            return

        should_play = rule['should_play'](data)
        sound_file = rule['file']

        # if should_play and not playing_state[utensil]:
        #     # Start the sound
        #     loop = utensil == 'pan'  # example: pan sizzle loops, others one-shot
        #     play_sound(utensil, sound_file, loop=loop)
        #     playing_state[utensil] = True

        # elif not should_play and playing_state[utensil]:
        #     # Stop the sound if condition is no longer true
        #     stop_sound(utensil)
        #     playing_state[utensil] = False

        #     # Reset/ Generate new target value for utensil if applicable
        #     # But maybe we can do the reset on "button press" instead?
        #     if utensil in ['pan', 'mixing_bowl','cutting_board']:
        #         generate_new_target(utensil)

        now = time.time()
        instrument = utensil  # you already get this
        value = data

        # Check pending notes for this instrument
        for note in pending_notes:
            if note["instrument"] != instrument:
                continue
            if note["hit"]:
                continue

            dt = now - note["hit_time"]

            # Too early to judge (MQTT reading before window)
            if dt < -HIT_WINDOW:
                continue

            # Too late → miss
            if dt > HIT_WINDOW:
                note["hit"] = True
                socketio.emit("note_result", {
                    "instrument": instrument,
                    "result": "miss",
                    "time": now,
                    "scheduled": note["hit_time"]
                })
                print(f"[MISS] {instrument} missed note scheduled at {note['hit_time']}")
                continue

            # Within window → check if the sensor condition is met
            rule = SOUND_RULES[instrument]
            if rule["should_play"](value):
                note["hit"] = True
                socketio.emit("note_result", {
                    "instrument": instrument,
                    "result": "hit",
                    "time": now,
                    "scheduled": note["hit_time"],
                    "accuracy_ms": int(dt * 1000)
                })
                print(f"[HIT] {instrument} accuracy {int(dt*1000)}ms")
                
        
    except Exception as e:
        print(f'Error processing message: {e}')


def start_mqtt_client():
    """Start MQTT client"""
    global mqtt_client
    
    try:
        import uuid
        mqtt_client = mqtt.Client(str(uuid.uuid1()))
        mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        
        mqtt_client.connect(MQTT_BROKER, port=MQTT_PORT, keepalive=60)
        mqtt_client.loop_start()
        
        print('MQTT viewer started')
        return True
        
    except Exception as e:
        print(f'[ERR] MQTT client failed: {e}')
        return False
    
@lru_cache(maxsize=10)
def load_sound(file_path):
    """Cache loaded sound objects to avoid reloading."""
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return None
    try:
        return pygame.mixer.Sound(file_path)
    except pygame.error as e:
        print(f"[ERROR] Cannot load sound file: {e}")
        return None

def play_sound(utensil, file_path, loop=False):
    """Play a sound for a specific utensil (overlapping allowed)."""
    sound = load_sound(file_path)
    if not sound:
        return

    channel = CHANNELS.get(utensil)
    if channel:
        # Loop indefinitely if needed (e.g., pan sizzle)
        channel.play(sound, loops=-1 if loop else 0)
        print(f"[PLAYING] {utensil}: {file_path}")
    else:
        print(f"[WARN] No channel for utensil '{utensil}'")

def stop_sound(utensil):
    """Stop sound for a specific utensil."""
    channel = CHANNELS.get(utensil)
    if channel:
        channel.stop()
        print(f"[STOPPED] {utensil}")


def generate_new_target(utensil):
    """Generate a new random target value for a specific utensil and update SOUND_RULES."""
    assert utensil in ['pan', 'mixing_bowl', 'cutting_board']

    SOUND_RULES[utensil]['target_value'] = SOUND_RULES[utensil]['generate_target']() 

    # Create message object
    message = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        'utensil': utensil,
        'target': SOUND_RULES[utensil]['target_value']
    }

    # Add to recent messages
    broadcast_to_web_client(message, 'mqtt_message_target')
    print(f"[NEW TARGET for {utensil}] {message['target']}")

    return None

def parse_file(file_path="charts/song01.json"):
    """Load a rhythm chart file and prepare event playback."""
    global chart_data

    if not os.path.exists(file_path):
        print(f"[ERROR] Chart file not found: {file_path}")
        return None

    try:
        with open(file_path, "r") as f:
            chart = json.load(f)
    except Exception as e:
        print(f"[ERROR] Failed to load chart: {e}")
        return None

    # Sort events by time (recommended for consistent playback)
    events = sorted(chart.get("events", []), key=lambda e: e["time"])
    chart_data = {
        "bpm": chart.get("bpm", 120),
        "offset": chart.get("offset", 0.0),
        "events": events,
    }

    print(f"[CHART LOADED] {len(events)} events loaded")
    return chart_data


def start_chart_playback():
    """Start a thread that updates target values in real-time."""
    global chart_thread, chart_playing

    if chart_data is None:
        print("[ERROR] No chart loaded. Call parse_file() first.")
        return

    if chart_thread and chart_thread.is_alive():
        print("[WARN] Chart already running.")
        return

    chart_playing = True
    chart_thread = threading.Thread(target=_chart_loop, daemon=True)
    chart_thread.start()


def _chart_loop():
    global chart_playing

    events = chart_data["events"]
    start_time = time.time() + chart_data["offset"]

    print("[CHART] Playback started")

    for event in events:
        if not chart_playing:
            break

        backend_event_time = start_time + event["time"]

        # Wait until it's time to SEND this event early
        now = time.time()
        send_time = backend_event_time - LEAD_TIME

        if send_time > now:
            time.sleep(send_time - now)

        # Send event early to client
        socketio.emit("chart_event", {
            "instrument": event["instrument"],
            "target": event["target"],
            "event_time": backend_event_time,  # exact beat time
            "server_time": time.time()         # when server sent it
        })

        pending_notes.append({
            "instrument": event["instrument"],
            "target": event["target"],
            "hit_time": backend_event_time,
            "hit": False
        })

        print(f"[CHART SCHEDULE] Sent {event['instrument']} early (will occur at {backend_event_time})")

    chart_playing = False
    print("[CHART] Playback finished")


def close_audio():
    """Cleanly shut down the audio system."""
    pygame.mixer.quit()
    print("[CLOSED] Audio system shut down")


@app.route('/')
def index():
    """Main viewer page"""
    return render_template('kitchen.html')


@socketio.on('connect')
def handle_connect():
    """Client connected - send recent messages"""
    print(f'Web client connected')
    # Send recent messages to newly connected client
    for msg in recent_messages:
        emit('mqtt_message', msg)


@socketio.on('disconnect')
def handle_disconnect():
    """Client disconnected"""
    print(f'Web client disconnected')


@socketio.on('clear_messages')
def handle_clear():
    """Clear message history"""
    recent_messages.clear()
    emit('messages_cleared', broadcast=True)
    print('Messages cleared')


@socketio.on('update_filter')
def handle_filter(data):
    """Update topic filter settings"""
    # Just acknowledge - filtering happens client-side
    print(f'Filter updated: {data}')
    emit('filter_updated', data)


if __name__ == '__main__':
    print("=" * 60)
    print("  MQTT Message Viewer")
    print("=" * 60)
    print(f"  Viewer URL:  http://0.0.0.0:5001")
    print(f"  Monitoring:  {MQTT_TOPIC} on {MQTT_BROKER}")
    print("=" * 60)
    
    # Start MQTT client
    start_mqtt_client()
    
    print("=" * 60)
    print()
    
    # Run Flask app on port 5001 (different from main app)
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
