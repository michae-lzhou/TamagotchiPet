from pynput import mouse, keyboard
from datetime import datetime, timedelta
import threading
import time

activity_log = []

activity_lock = threading.Lock()

ACTIVITY_WINDOW_MINUTES = 15

def record_activity(event_type):
    cutoff = datetime.now() - timedelta(minutes=ACTIVITY_WINDOW_MINUTES)
    with activity_lock:
        activity_log.append((event_type, datetime.now()))
        # purge old activities so it doesn't take up more and more memory
        while activity_log and activity_log[0][1] < cutoff:
            activity_log.pop(0)

def on_key_press(key):
    record_activity("key")

def on_mouse_move(x, y):
    record_activity("mouse")

def get_activity_within(minutes):
    cutoff = datetime.now() - timedelta(minutes=minutes)
    with activity_lock:
        return [(t, ts) for t, ts in activity_log if ts > cutoff]

# get_knm_activity: returns the keyboard and mouse activity in the past X
# minutes
def get_knm_activity(activity_window):
    recent = get_activity_within(activity_window)
    # print(f"[{datetime.now().strftime('%H:%M:%S')}] User activity in last "
    #         f"{activity_window} min: {len(recent)} events")
    key_count = sum(1 for t, _ in recent if t == "key")
    mouse_count = sum(1 for t, _ in recent if t == "mouse")
    # print(f"    → Keystrokes: {key_count}, Mouse movements: {mouse_count}")
    
    return key_count, mouse_count

# start_listeners: starts two threads of listeners keeping track of keystrokes
# and mouse movements
def start_listeners():
    keyboard_listener = keyboard.Listener(on_press=on_key_press)
    mouse_listener = mouse.Listener(on_move=on_mouse_move)

    keyboard_listener.start()
    mouse_listener.start()

    return keyboard_listener, mouse_listener

# if __name__ == "__main__":
#     print("Starting activity tracker... (press keys or move mouse)")
#     keyboard_listener, mouse_listener = start_listeners()
# 
#     try:
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         print("Stopping listeners...")
#         keyboard_listener.stop()
#         mouse_listener.stop()
