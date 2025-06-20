import sys
import os
import json
import random
import listeners
from PyQt6.QtWidgets import QApplication, QLabel
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QTimer
from pyautostart import SmartAutostart
from pathlib import Path

# ###############################################################################
# # This block of code gently suppresses the initial warning if my keyboard or
# # mouse activates an event before it is supposed to
# 
# import warnings
# import threading
# import sys
# 
# # Suppress specific threading warnings on macOS
# warnings.filterwarnings("ignore", category=RuntimeWarning, module="threading")
# 
# # Optional: Redirect stderr temporarily during listener initialization
# class SuppressStderr:
#     def __enter__(self):
#         self._original_stderr = sys.stderr
#         sys.stderr = open(os.devnull, 'w')
#         return self
# 
#     def __exit__(self, exc_type, exc_val, exc_tb):
#         sys.stderr.close()
#         sys.stderr = self._original_stderr
# 
# ###############################################################################

# get_config_file: reads and writes from a user-specific config file to have
# persistent settings across sessions (position, scale, etc.)
def get_config_file():
    if sys.platform == "win32":
        config_dir = Path(os.getenv("APPDATA")) / "TamagotchiPet"
    else:
        config_dir = Path.home() / ".config" / "TamagotchiPet"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# POSITION_FILE = resource_path("position.json")

A_DURATION = 0.25
L_DURATION = 5

A_KPM = 200         # 200 key presses per minute (upper threshold)
L_KPM = 50          # 50 key presses per minute (lower threshold)
L_MPM = 250         # 250 mouse movements per minute (lower threshold)

# save_config: saves all configuration settings (position, scale, etc.)
def save_config(pos=None, scale=None):
    config = {}
    
    # Load existing config if file exists
    if os.path.exists(get_config_file()):
        try:
            with open(get_config_file(), "r") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            config = {}
    
    # Update with new values if provided
    if pos is not None:
        config["x"] = pos.x()
        config["y"] = pos.y()
    if scale is not None:
        config["scale"] = scale
    
    # Save updated config
    with open(get_config_file(), "w") as f:
        json.dump(config, f)

# load_config: loads all configuration settings
def load_config():
    if os.path.exists(get_config_file()):
        try:
            with open(get_config_file(), "r") as f:
                data = json.load(f)
                
                # Load position
                x = data.get("x", 0)
                y = data.get("y", 0)
                if x < 0 or y < 0:
                    x, y = 0, 0
                
                # Load scale
                scale = data.get("scale", 2.0)
                scale = max(0.5, min(5.0, scale))  # Clamp scale between reasonable bounds
                
                return x, y, scale
        except (json.JSONDecodeError, IOError):
            pass
    
    return 0, 0, 2.0  # default values

cat_sheet = resource_path("cat_sprite_sheet.png")
cat_frames = 8
cat_counts = 10
cat_keys = ["idle", "idle", "idle", "idle", "active", "active",
        "lazy", "interact", "interact", "lazy"]
cat_scale = 2

# Create a 1x1 fully transparent QPixmap
def transparent_pixmap():
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(0)  # 0 = fully transparent
    pixmap = QPixmap.fromImage(image)
    return pixmap

# bbox: loads in a sprite frame and finds the max/min of both x and y, if the
# boolean returned is true, that means the current frame is fully transparent
def bbox(pixmap: QPixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)

    width = image.width()
    height = image.height()

    min_x, max_x, min_y, max_y = width, 0, height, 0
    transparent = True

    for x in range(width):
        for y in range(height):
            pixel = image.pixelColor(x, y)
            if pixel.alpha() != 0:
                transparent = False
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

    return min_x, max_x, min_y, max_y, transparent

# smart_crop: loads in a sprite and crops it into the expected dimensions
def smart_crop(min_x, max_x, min_y, max_y, sprite):
    cropped_sprite = sprite.copy(min_x, min_y, max_x - min_x + 1,
                                 max_y - min_y + 1)
    return cropped_sprite

# load_sprites: loads individual sprites from a sprite sheet and parses them
# into their pre-determined lists in the dictionary of animations and returns it
def load_sprites(sheet_path, sprite_frames, sprite_counts, keys):
    # holds all of the sprite animations
    sprite_map = {key: [] for key in keys}

    # loading the sprite sheet
    sheet = QPixmap(sheet_path)
    sheet_width = sheet.width()
    sheet_height = sheet.height()

    sprite_width = sheet_width // sprite_frames
    sprite_height = sheet_height // sprite_counts

    min_x, max_x, min_y, max_y = sprite_width, 0, sprite_height, 0

    # cropping each sprite
    for count in range(sprite_counts):
        current_animation = []
        for frame in range(sprite_frames):
            x = frame * sprite_width
            y = count * sprite_height

            sprite = sheet.copy(x, y, sprite_width, sprite_height)
            # for each sprite, extract its bounding box (max/min x and y
            # values)
            left, right, top, bottom, transparent = bbox(sprite)
            # only append if the sprite itself has information (ignore blank
            # spots)
            if not transparent:
                # find the overall max/min x and y
                min_x = min(min_x, left)
                max_x = max(max_x, right)
                min_y = min(min_y, top)
                max_y = max(max_y, bottom)
                current_animation.append(sprite)
        sprite_map[keys[count]].append(current_animation)

    # now "smart crop" each sprite based on the global max and min of the width
    # and height
    for key in sprite_map:
        for sprite_list in sprite_map[key]:
            for sindex, sprite in enumerate(sprite_list):
                cropped_sprite = smart_crop(min_x, max_x, min_y, max_y, sprite)
                # sprite_map[keys[count]][index] = cropped_sprite
                sprite_list[sindex] = cropped_sprite

    return sprite_map

# FloatingPet: a class that creates a new floating window of the tamagotchi pet
class FloatingPet(QLabel):
    def __init__(self, scale=1, pet_sprites=None):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.pet_sprites = pet_sprites
        self.scale = scale
        self.drag_pos = None
        x, y, _ = load_config()  # Load position from config, ignore scale since it's passed as parameter

        self.move(x, y)

        #######################################################################
        # four different states: idle, active, interact, lazy
        #
        # idle state - randomly determine which idle animation it is based on
        #              I * [10, 15], for I idle frames and 10-15 cycles
        #            - default if not active or lazy
        #
        # active state - randomly determine which active animation it is based
        #                on A * [5, 10], for A active frames and 5-10 cycles
        #              - >200 keys_pressed/min for 15 seconds
        #
        # interact state - interrupt! stops the current state and immediately
        #                  enter the interact state and animate one cycle
        #
        # lazy state - randomly determine which lazy animation it is based on 
        #              L * [15, 30], for L lazy frames and 15-30 cycles
        #            - <250 mouse_move/min AND <50 keys_pressed/min for 5 mins
        #
        # states will be determined dynamically, and animation switches are
        # "interrupts" and instantaneous; the idle animation will be displayed
        # on start up
        #
        #######################################################################

        # hard-coding the cycle ranges for different states
        self.state_cycles = {"idle":     (10, 15),
                             "active":   (5, 10),
                             "interact": (1, 1),
                             "lazy":     (15, 30)}
        self.keys = list(pet_sprites.keys()) # ("idle", "active", "interact",
                                             #  "lazy")

        # animate the idle cycle state on start up
        self.state = "lazy"
        self.prev_state = "lazy"
        self.refresh_animation(curr_state="lazy")
        self.frame_index = 0
        
        self.setPixmap(transparent_pixmap())

        # set up QTimer to cycle the frames
        self.timer = QTimer()
        self.timer.timeout.connect(self.next_frame)
        self.timer.start(100)

        self.show()

    # refresh_animation: only called to re-pick which animation to do for the
    # next X cycles, if the curr_state is set to interact, play one cycle of
    # interact animation and return to the previous state
    def refresh_animation(self, curr_state):
        # preserve previous state in the event of interact
        previous_state = self.state

        if self.state == "interact":
            self.state = self.prev_state
        else:
            self.state = curr_state

        self.animation = random.randrange(len(self.pet_sprites[self.state]))
        self.cycles = 0
        self.frame_index = 0    # reset in the event that the refresh is
                                # triggered by an "interrupt" or 'interact'
        self.prev_state = previous_state

    # update_pixmap: redraws the window with the current frame to display the
    # tamagotchi
    def update_pixmap(self):
        current_state = self.state
        current_animation = self.animation
        frames = self.pet_sprites[current_state][current_animation]

        if frames:
            pixmap = QPixmap(frames[self.frame_index])
            scaled_pixmap = pixmap.scaled(
                int(pixmap.width() * self.scale),
                int(pixmap.height() * self.scale),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.clear()
            self.setPixmap(scaled_pixmap)
            self.resize(scaled_pixmap.size())
            self.setFixedSize(scaled_pixmap.size())

    # complete_animation: after each cycle of animation, check whether or not
    # we've reached the desired number to refresh to a new animation in the same
    # state
    def complete_animation(self):
        # each time an animation is completed, check if we are switching states
        # if keystrokes >250/min for 30 seconds, state = active
        key_count_a, mouse_count_a = listeners.get_knm_activity(A_DURATION)
        key_count_l, mouse_count_l = listeners.get_knm_activity(L_DURATION)

        if key_count_a > A_DURATION * A_KPM:
            self.state = "active"
        elif key_count_l < L_DURATION * L_KPM and \
             mouse_count_l < L_DURATION * L_MPM:
            self.state = "lazy"
        else:
            self.state = "idle"

        # here, we decide how many times the same animation is used before
        # switching to a new animation of the same state
        self.frame_index = 0
        self.cycles += 1
        a, b = self.state_cycles[self.state]
        expected_cycle = random.randint(a, b)
        if (self.cycles >= expected_cycle):
            # maintain the same state, but refresh which animation it is
            self.refresh_animation(curr_state=self.state)

    # next_frame: cycles through the frames of each animation
    def next_frame(self):
        current_state = self.state
        current_animation = self.animation
        total_frames = len(self.pet_sprites[current_state][current_animation])
        self.frame_index += 1

        if self.frame_index >= total_frames:
            self.complete_animation()
        self.update_pixmap()

    # interactEvent: a custom "interrupt" that forces the current animation to
    # be of type 'interact' for one cycle, and then returns to
    def interactEvent(self):
        self.refresh_animation(curr_state = "interact")

    def wheelEvent(self, event):
        """Handle mouse wheel scrolling to adjust scale"""
        # Get the scroll delta (positive for up, negative for down)
        delta = event.angleDelta().y()
        
        # Adjust scale based on scroll direction
        scale_change = 0.1 if delta > 0 else -0.1
        new_scale = self.scale + scale_change
        
        # Clamp scale between reasonable bounds (0.5x to 5.0x)
        new_scale = max(0.5, min(5.0, new_scale))
        
        if new_scale != self.scale:
            self.scale = new_scale
            self.update_pixmap()
            save_config(scale=self.scale)
        
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.interactEvent()
            event.accept()
        if event.button() == Qt.MouseButton.RightButton:
            quit_app()
        listeners.get_knm_activity(0.5)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            # Calculate the new position
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            
            # Get screen geometry
            screen = QApplication.primaryScreen().geometry()
            
            # Get widget size
            widget_size = self.size()
            
            # Constrain position to screen boundaries
            x = max(0, min(new_pos.x(), screen.width() - widget_size.width()))
            y = max(0, min(new_pos.y(), screen.height() - widget_size.height()))
            
            # Move to constrained position
            self.move(x, y)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = None
            save_config(pos=self.pos())
            event.accept()

    def quit(self):
        QApplication.instance().quit()

def quit_app():
    pet.quit()
    keyboard_listener.stop()
    mouse_listener.stop()

cat_sprites = None
pet = None
keyboard_listener = None
mouse_listener = None

if __name__ == "__main__":
    # enabling autostart
    try:
        autostart = SmartAutostart()
        options = {
            "args": [
                os.path.abspath(__file__)  # Fixed: was using undefined 'file' variable
            ]
        }
        autostart.enable(name="TamagotchiPet", options=options)

    except Exception as e:
        pass

    try:
        app = QApplication(sys.argv)
        cat_sprites = load_sprites(cat_sheet, cat_frames, cat_counts, cat_keys)
        
        # Load saved position and scale from config
        x, y, saved_scale = load_config()
        pet = FloatingPet(scale=saved_scale, pet_sprites=cat_sprites)

        keyboard_listener, mouse_listener = listeners.start_listeners()
    except KeyboardInterrupt:
        quit_app()

    sys.exit(app.exec())
