"""
Audio Manager - Sound loading and playback
"""

import pygame
import os
from functools import lru_cache
from config import CHANNELS

# ============================================================================
# PLAYBACK STATE
# ============================================================================

# Track which utensils are currently playing sounds
playing_state = {
    'pan': False,
    'cutting_board': False,
    'mixing_bowl': False
}

# ============================================================================
# SOUND CONDITION CHECKING
# ============================================================================

def should_play(utensil, sensor_data, target, threshold):
    """
    Check if the current sensor data meets the target condition for this utensil.
    
    Args:
        utensil: 'pan', 'cutting_board', or 'mixing_bowl'
        sensor_data: dict of sensor values from MQTT
        target: the target value from the chart (e.g., "low", "high", button ID)
        threshold: numeric threshold for comparison
    
    Returns:
        bool: True if condition is met, False otherwise
    """
    if target is None:
        return False

    if utensil == 'pan':
        # Pan uses rotation sensor AND button must be held
        button_held = sensor_data.get('button', False)
        if not button_held:
            return False  # Button must be held for condition to be met
        
        # Then check rotation threshold
        curr_val = sensor_data.get('rotation', 0)
        if target == "low":
            return curr_val < threshold
        elif target == "high":
            return curr_val > threshold
        
    elif utensil == "cutting_board":
        # Cutting board uses button presses
        button_id = str(target)
        return sensor_data.get(button_id, 0) == 1
    
    elif utensil == "mixing_bowl":
        # Mixing bowl uses accelerometer
        return sensor_data.get('x', 0) > target
    
    return False


# ============================================================================
# AUDIO PLAYBACK
# ============================================================================

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
    """Play a sound for a specific utensil on its dedicated channel."""
    sound = load_sound(file_path)
    if not sound:
        return

    channel = CHANNELS.get(utensil)
    if channel:
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


def close_audio():
    """Cleanly shut down the audio system."""
    pygame.mixer.quit()
    print("[CLOSED] Audio system shut down")