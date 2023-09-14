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

import json
import jsons

def debug_obj(obj):
    j = jsons.dump(obj, indent=4)
    print(j)
#endregion

#region Config
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
player = config["player"] if "player" in config else {}
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
    def __init__(self):
        self.adb_prefix = f"\"{adb_path}\""
        self.screen_width = 0
        self.screen_height = 0
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

    def click(self, release, x, y):
        x = float(x) * self.screen_width
        y = float(y) * self.screen_height
        self.__adb(f"shell input tap {x} {y}")

    def swipe(self, x, y, x_dst, y_dst):
        x = float(x) * self.screen_width
        y = float(y) * self.screen_height
        x_dst = float(x_dst) * self.screen_width
        y_dst = float(y_dst) * self.screen_height
        self.__adb(f"shell input swipe {x} {y} {x_dst} {y_dst} 20")

    def swipe_diff(self, x, y, x_diff, y_diff):
        x = float(x) * self.screen_width
        y = float(y) * self.screen_height
        self.__adb(f"shell input swipe {x} {y} {x + x_diff} {y + y_diff} 20")
#endregion

#region Windows
import threading
from pynput import keyboard as Keyboard, mouse as Mouse

class Desktop:
    def __init__(self):
        self.key_ctrl = False
        self.key_shift = False
        self.key_alt = False
        self.key_records = set()
        self.key_worker = threading.Thread(target=self.key_work, args=(self,))
        self.mouse_x = -1
        self.mouse_y = -1
        self.mouse_worker = threading.Thread(target=self.mouse_work, args=(self,))

    def start(self, conn):
        self.conn = conn
        self.key_worker.start()
        self.mouse_worker.start()

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

    def __format_key(self, vk, is_pressed):
        if vk in self.key_records and is_pressed:
            return None
        if vk in self.key_records:
            self.key_records.remove(vk)
        else:
            self.key_records.add(vk)
        if vk == 0xA2 or vk == 0xA3:
            self.key_ctrl = is_pressed
            return None
        if vk == 0xA0 or vk == 0xA1:
            self.key_shift = is_pressed
            return None
        if vk == 0xA4 or vk == 0xA5:
            self.key_alt = is_pressed
            return None
        if vk >= 0x70 and vk <= 0x7B:
            # F1 ~ F12
            return "F" + str(vk - 0x6F)
        fk = ""
        if is_pressed:
            if self.key_ctrl:
                fk += "C"
            if self.key_shift:
                fk += "S"
            if self.key_alt:
                fk += "A"
        if vk >= 0x30 and vk <= 0x39:
            # 0 ~ 9
            fk += str(vk - 0x30)
        elif vk >= 0x41 and vk <= 0x5A:
            # a ~ z
            fk += chr(vk + 0x20)
        else:
            return None
        return fk if is_pressed else "!" + fk

    def __to_vk(key):
        if hasattr(key, "value"):
            return key.value.vk
        else:
            return key.vk

    def on_press(self, key):
        vk = Desktop.__to_vk(key)
        fk = self.__format_key(vk, True)
        if fk is not None:
            self.conn.send(fk)
            # print(f"Format Key: {fk}")
        return True

    def on_release(self, key):
        vk = Desktop.__to_vk(key)
        fk = self.__format_key(vk, False)
        if fk is not None:
            self.conn.send(fk)
            # print(f"Format Key: {fk}")
        return True

    def on_move(self, x, y):
        if x != self.mouse_x or y != self.mouse_y:
            self.mouse_x = x
            self.mouse_y = y
            self.conn.send(f"M {x} {y}")

    def on_click(self, x, y, button, pressed):
        if button == Mouse.Button.left and pressed:
            self.conn.send(f"L {x} {y}")
        elif button == Mouse.Button.right and pressed:
            self.conn.send(f"R {x} {y}")
        return True

    def on_scroll(self, x, y, dx, dy):
        # print(f"Mouse scroll is: {x}, {y}, {dx}, {dy}")
        return True
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

#region Reactor
import multiprocessing as mp

class Reactor:
    def __init__(self, adb, mapper):
        self.adb = adb
        self.mapper = mapper

        self.window_left = 0
        self.window_top = 0
        self.window_right = 0
        self.window_bottom = 0
        self.window_width = 0
        self.window_height = 0

        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_x_in = 0
        self.mouse_y_in = 0
        self.player_x_pct = player["x"] if "x" in player else 0.5
        self.player_y_pct = player["y"] if "y" in player else 0.5
        self.player_x = 0
        self.player_y = 0
        self.vector_x = 0
        self.vector_y = 0

    def desktop_start_entry(conn):
        Desktop().start(conn)

    def __setup_desktop(self):
        mp.freeze_support()
        parent_conn, child_conn = mp.Pipe()
        self.desktop_process = mp.Process(
            target=Reactor.desktop_start_entry, args=(child_conn,))
        self.conn = parent_conn
        self.child_conn = child_conn
        self.desktop_process.start()

    def loop(self):
        self.__setup_desktop()
        while True:
            msg = self.conn.recv()
            if msg == "exit":
                self.desktop_process.terminate()
                break
            try:
                self.__act(msg)
            except Exception as e:
                print(f"Exception: {e}")

    def __act(self, fk):
        release = False
        if fk[0] == "!":
            release = True
            fk = fk[1:]
        if self.__act_util(fk, release):
            return
        if self.__act_mouse(fk, release):
            return
        if self.__act_key(fk, release):
            return

    def __calc_window_size(self):
        self.window_width = self.window_right - self.window_left
        self.window_height = self.window_bottom - self.window_top
        self.player_x = int(self.window_width * self.player_x_pct)
        self.player_y = int(self.window_height * self.player_y_pct)

    def __act_util(self, fk, release):
        if fk == "CSAi":
            # control + shift + alt + i
            self.window_left = self.mouse_x
            self.window_top = self.mouse_y
            self.__calc_window_size()
            print(f"Window Left-Top is: {self.mouse_x}, {self.mouse_y}")
            return True
        elif fk == "CSAo":
            # control + shift + alt + o
            self.window_right = self.mouse_x
            self.window_bottom = self.mouse_y
            self.__calc_window_size()
            print(f"Window Right-Bottom is: {self.mouse_x}, {self.mouse_y}")
            return True
        else:
            return False

    def __unformat_key(self, fk):
        is_ctrl = False
        is_shift = False
        is_alt = False
        is_fn = False
        if fk.startswith("C"):
            fk = fk[1:]
            is_ctrl = True
        if fk.startswith("S"):
            fk = fk[1:]
            is_shift = True
        if fk.startswith("A"):
            fk = fk[1:]
            is_alt = True
        if fk.startswith("F"):
            fk = fk[1:]
            is_fn = True
        return fk, is_ctrl, is_shift, is_alt, is_fn

    def __act_key(self, fk, release):
        if release:
            return
        k, is_ctrl, is_shift, is_alt, is_fn = self.__unformat_key(fk)
        act = self.mapper.map(k)
        if act is None:
            return
        act = act.split()
        act_type = act[0]
        if act_type == "click":
            self.adb.click(act[1], act[2])
        elif act_type == "swipe":
            self.adb.swipe(act[1], act[2], act[3], act[4])
        elif act_type == "swipe_direction":
            self.adb.swipe_diff(act[1], act[2], self.vector_x, self.vector_y)
        elif act_type == "swipe_area":
            self.adb.swipe_area(release, act[1], act[2])
        else:
            print(f"Unknown action: {act_type}")

    def __act_mouse(self, fk, release):
        is_move = fk.startswith("M")
        is_left = fk.startswith("L")
        is_right = fk.startswith("R")
        if is_move or is_left or is_right:
            fk = fk.split()
            x = int(fk[1])
            y = int(fk[2])
        else:
            return False
        self.mouse_x = x
        self.mouse_y = y
        if x <= self.window_left or x >= self.window_right or y <= self.window_top or y >= self.window_bottom:
            return True
        if is_left or is_right:
            #todo
            pass
        self.mouse_x_in = x - self.window_left
        self.mouse_y_in = y - self.window_top
        self.vector_x = self.mouse_x_in - self.player_x
        self.vector_y = self.mouse_y_in - self.player_y
        # print(f"Vector is: {self.vector_x}, {self.vector_y}")
        # print(f"Mouse position is: {self.mouse_x_in}, {self.mouse_y_in}")
        return True
#endregion

mapper = Mapper(keys)
adb = Adb()
reactor = Reactor(adb, mapper)

if __name__ == "__main__":
    print("Start Running...")
    reactor.loop()
    while True:
        time.sleep(1)
