#region Init
import importlib
import pip
import ast
import os
import time

pip.main(["install", "--upgrade", "pip"])

current_file_path = os.path.abspath(__file__)
with open(current_file_path, "r", encoding="utf-8") as f:
    current_file_str = f.read()

for node in ast.walk(ast.parse(current_file_str)):
    if isinstance(node, ast.Import):
        for alias in node.names:
            p = alias.name
            try:
                importlib.import_module(p)
            except ImportError:
                pip.main(["install", p])
    elif isinstance(node, ast.ImportFrom):
        p = node.module
        try:
            importlib.import_module(p)
        except ImportError:
            pip.main(["install", p])
#endregion

#region Config
import json

root_path = os.path.dirname(os.path.abspath(__file__))
buildin_adb_path = f"{root_path}/platform-tools/adb.exe"

with open(f"{root_path}/configs.json", "r") as f:
    configs = json.load(f)

if len(configs) == 0:
    print("No environment found.")
    exit()

config = {}
keys = {}
if len(configs) == 1:
    config = configs[0]
else:
    for i in range(len(configs)):
        print(f"{i}: {configs[i]['name']}")
    index = int(input("Select an environment: "))
    config = configs[index]

print(f"Using environment: {config['name']}")
adb_path = config["adb_path"] if "adb_path" in config else buildin_adb_path
keys = config["keys"] if "keys" in config else {}
#endregion

#region Mapper
class Mapper:
    def __init__(self, keys):
        self.keys = keys
    def map(self, k):
        if k in self.keys:
            return self.keys[k]
        else:
            return None
    def add(self, k, v):
        self.keys[k] = v
    def remove(self, k):
        if k in self.keys:
            del self.keys[k]
#endregion

#region ADB
class Adb:
    def __init__(self, mapper):
        self.adb_prefix = f"\"{adb_path}\""
        self.screen_width = 0
        self.screen_height = 0
        self.mapper = mapper
        self.__adb_setup()

    def __adb(self, cmd):
        os.system(f"{self.adb_prefix} {cmd}")

    def __adb_r(self, cmd):
        return os.popen(f"{self.adb_prefix} {cmd}").read()

    def __adb_connect(self, ip_port):
        self.__adb(f"connect {ip_port} > nul")

    def __adb_get_devices(self):
        return self.__adb_r("devices")

    def __adb_screen_size(self):
        size_str = self.__adb_r("shell wm size")
        size_arr = size_str.split()[2].split("x")
        self.screen_width = int(size_arr[1])
        self.screen_height = int(size_arr[0])

    def __adb_setup(self):
        if "adb_ip_port" in config:
            self.__adb_connect(config["adb_ip_port"])
        devices = [d.split()[0] for d in self.__adb_get_devices().split("\n")[1:] if len(d) > 0]
        if len(devices) == 0:
            print("No device found.")
            exit()
        if len(devices) == 1:
            target_device = devices[0]
        else:
            for i in range(len(devices)):
                print(f"{i}: {devices[i]}")
            index = int(input("Select a device: "))
            target_device = devices[index]
        print(f"Using device: {target_device}")
        self.adb_prefix = f"{self.adb_prefix} -s {target_device}"
        self.__adb_screen_size()

    def adb_action(self, key):
        release = False
        if key[0] == "!":
            release = True
            key = key[1:]
        act = self.mapper.map(key)
        if act is None:
            return
        act = act.split()
        act_type = act[0]
        if act_type == "click":
            self.adb_click(release, act[1], act[2])
        elif act_type == "swipe":
            self.adb_swipe(release, act[1], act[2], act[3], act[4])
        elif act_type == "swipe_direction":
            self.adb_swipe_direction(release, act[1], act[2])
        elif act_type == "swipe_area":
            self.adb_swipe_area(release, act[1], act[2])
        else:
            print(f"Unknown action: {act_type}")

    def adb_click(self, release, x, y):
        if release:
            return
        x = float(x) * self.screen_width
        y = float(y) * self.screen_height
        self.__adb(f"shell input tap {x} {y}")

    def adb_swipe(self, release, x, y, x_d, y_d):
        if release:
            return
        x = float(x) * self.screen_width
        y = float(y) * self.screen_height
        x_d = float(x_d) * self.screen_width
        y_d = float(y_d) * self.screen_height
        self.__adb(f"shell input swipe {x} {y} {x_d} {y_d} 20")
#endregion

#region Windows
import threading
from pynput import keyboard as Keyboard, mouse as Mouse

class Desktop:
    def __init__(self, adb):
        self.window_left = 0
        self.window_top = 0
        self.window_right = 0
        self.window_bottom = 0
        self.window_width = 0
        self.window_height = 0

        self.key_letters = [ False for _ in range(26) ]
        self.key_digits = [ False for _ in range(10) ]
        self.key_fns = [ False for _ in range(13) ]
        self.key_ctrl = False
        self.key_shift = False
        self.key_alt = False
        self.key_space = False
        self.key_worker = threading.Thread(target=self.key_work, args=(self,))
        self.key_worker.start()

        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_x_pct = 0.0
        self.mouse_y_pct = 0.0
        self.mouse_left = False
        self.mouse_right = False
        self.mouse_worker = threading.Thread(target=self.mouse_work, args=(self,))
        self.mouse_worker.start()

        self.adb = adb

    def key_work(arg, _):
        key_listener = Keyboard.Listener(
            on_press   = lambda k: arg.on_press(k),
            on_release = lambda k: arg.on_release(k))
        key_listener.start()
        key_listener.join()

    def mouse_work(arg, _):
        mouse_listener = Mouse.Listener(
            on_move   = lambda x, y: arg.on_move(x, y),
            on_click  = lambda x, y, b, p: arg.on_click(x, y, b, p),
            on_scroll = lambda x, y, dx, dy: arg.on_scroll(x, y, dx, dy))
        mouse_listener.start()
        mouse_listener.join()

    def __calc_window_size(self):
        self.window_width = self.window_right - self.window_left
        self.window_height = self.window_bottom - self.window_top

    def format_key(key):
        if Desktop.is_ctrl(key):
            return "ctrl"
        elif Desktop.is_shift(key):
            return "shift"
        elif Desktop.is_alt(key):
            return "alt"
        elif Desktop.is_digit(key) >= 0:
            return str(Desktop.is_digit(key))
        elif Desktop.is_fn(key) >= 0:
            return "f" + str(Desktop.is_fn(key))
        else:
            a = Desktop.is_alpha(key)
            if a >= 0:
                return chr(a + ord('a'))
        return ""

    def __record_key(self, key, is_pressed):
        fk = Desktop.format_key(key)
        if fk == "":
            return ""
        elif fk == "ctrl":
            self.key_ctrl = is_pressed
        elif fk == "shift":
            self.key_shift = is_pressed
        elif fk == "alt":
            self.key_alt = is_pressed
        elif Desktop.is_digit(key) >= 0:
            self.key_digits[Desktop.is_digit(key)] = is_pressed
        elif Desktop.is_fn(key) >= 0:
            self.key_fns[Desktop.is_fn(key)] = is_pressed
        else:
            a = Desktop.is_alpha(key)
            if a >= 0:
                if a == ord("i") - ord("a") and self.is_ctrl and self.is_shift and self.is_alt:
                    # record left-top corner
                    self.window_left = self.mouse_x
                    self.window_top = self.mouse_y
                    self.__calc_window_size()
                elif a == ord("o") - ord("a") and self.is_ctrl and self.is_shift and self.is_alt:
                    # record right-bottom corner
                    self.window_right = self.mouse_x
                    self.window_bottom = self.mouse_y
                    self.__calc_window_size()
                self.key_letters[a] = is_pressed
        return "!" + fk if not is_pressed else fk

    def on_press(self, key):
        fk = self.__record_key(key, True)
        self.adb.adb_action(fk)
        # print(f"Key press is: {key}")
        return True

    def on_release(self, key):
        fk = self.__record_key(key, False)
        self.adb.adb_action(fk)
        # print(f"Key release is: {key}")
        return True

    def on_move(self, x, y):
        self.mouse_x = x
        self.mouse_y = y

        if self.window_width > 0:
            self.mouse_x_pct = (x - self.window_left) / self.window_width
        else:
            self.mouse_x_pct = 0.0

        if self.window_height > 0:
            self.mouse_y_pct = (y - self.window_top) / self.window_height
        else:
            self.mouse_y_pct = 0.0
        # print(f"Mouse position is: {x}, {y}")
        return True

    def on_click(self, x, y, button, pressed):
        if button == Mouse.Button.left:
            self.mouse_left = pressed
        elif button == Mouse.Button.right:
            self.mouse_right = pressed
        # print(f"Mouse click is: {x}, {y}, {button}, {pressed}")
        return True

    def on_scroll(self, x, y, dx, dy):
        # print(f"Mouse scroll is: {x}, {y}, {dx}, {dy}")
        return True

    def is_ctrl(key):
        return key == Keyboard.Key.ctrl_l or key == Keyboard.Key.ctrl_r or key == Keyboard.Key.ctrl

    def is_shift(key):
        return key == Keyboard.Key.shift_l or key == Keyboard.Key.shift_r or key == Keyboard.Key.shift

    def is_alt(key):
        return key == Keyboard.Key.alt_l or key == Keyboard.Key.alt_r or key == Keyboard.Key.alt

    def is_alpha(key):
        s = str(key)
        if len(s) == 3 and s[0] == "'" and s[2] == "'" and s[1].isalpha():
            return ord(s[1]) - ord('a')
        else:
            return -1

    def is_digit(key):
        s = str(key)
        if len(s) == 3 and s[0] == "'" and s[2] == "'" and s[1].isdigit():
            return ord(s[1]) - ord('0')
        else:
            return -1

    def is_fn(key):
        if key == Keyboard.Key.f1:
            return 1
        elif key == Keyboard.Key.f2:
            return 2
        elif key == Keyboard.Key.f3:
            return 3
        elif key == Keyboard.Key.f4:
            return 4
        elif key == Keyboard.Key.f5:
            return 5
        elif key == Keyboard.Key.f6:
            return 6
        elif key == Keyboard.Key.f7:
            return 7
        elif key == Keyboard.Key.f8:
            return 8
        elif key == Keyboard.Key.f9:
            return 9
        elif key == Keyboard.Key.f10:
            return 10
        elif key == Keyboard.Key.f11:
            return 11
        elif key == Keyboard.Key.f12:
            return 12
        else:
            return -1
#endregion

print("Start Running...")
mapper = Mapper(keys)
adb = Adb(mapper)
desk = Desktop(adb)

while True:
    time.sleep(1)

