#region ADB Event Debug
#
# list all input events: "adb shell getevent -l"
#
#endregion

#region Init
import importlib
import pip
import ast
import os
import time
import re
import math

os.system("pip install --upgrade pip --quiet")

current_file_path = os.path.abspath(__file__)
with open(current_file_path, "r", encoding="utf-8") as f:
    current_file_str = f.read()

def pip_install(p):
    try:
        importlib.import_module(p)
    except ImportError:
        os.system(f"pip install {p}")
        # pip.main(["install", p])

for node in ast.walk(ast.parse(current_file_str)):
    if isinstance(node, ast.Import):
        for alias in node.names:
            pip_install(alias.name)
    elif isinstance(node, ast.ImportFrom):
        pip_install(node.module)

import json
import jsons
import traceback

def debug_obj(obj):
    j = jsons.dump(obj, indent=4)
    print(j)

def debug_traceback(e):
    tb = traceback.extract_tb(e.__traceback__)
    [print(i) for i in tb]
#endregion

#region Config
def __System_Config__():
    root_path = os.path.dirname(os.path.abspath(__file__))
    buildin_adb_path = f"{root_path}/platform-tools/adb.exe"
    with open(f"{root_path}/configs.json", "r", encoding="utf-8") as f:
        configs = json.load(f)
    if len(configs) == 0:
        print("No environment found.")
        exit()
    config = {}
    if len(configs) == 1:
        config = configs[0]
    else:
        for i in range(len(configs)):
            print(f"{i}: {configs[i]['name']}")
        index = int(input("Select an environment: "))
        config = configs[index]
    return config
#endregion

#region Mapper
class Mapper:
    def __init__(self, config):
        self.__pad = None
        self.__pad_stop = None
        self.keys = config["keys"]
        for k, v in self.keys.items():
            self.keys[k] = [Mapper.__float(e) for e in v.split()]

    def __float(s):
        try:
            f = float(s)
            return f
        except ValueError:
            return s

    def map(self, k):
        if k in self.keys:
            return self.keys[k]
        else:
            return None

    def add(self, k, v):
        self.keys[k] = [Mapper.__float(e) for e in v.split()]

    def remove(self, k):
        if k in self.keys:
            del self.keys[k]

    def pad(self):
        if self.__pad is not None:
            return self.__pad
        for k, v in self.keys.items():
            if v[0] != "pad":
                continue
            self.__pad = v
            return v
        return None

    def pad_stop(self):
        if self.__pad_stop is not None:
            return self.__pad_stop
        for k, v in self.keys.items():
            if v[0] != "pad":
                continue
            self.__pad_stop = k
            return k
        return None

#endregion

#region ADB
import threading
import queue

class MultiTouch:
    def __init__(self):
        self.mts = [{
            "slot": i,
            "occupy": False,
            "id": 0,
            "key": 0
        } for i in range(8)]

    def __key_to_id(key):
        return ord(key) - ord("0")

    def request_slot(self, key):
        for i in range(8):
            if not self.mts[i]["occupy"]:
                self.mts[i]["occupy"] = True
                self.mts[i]["id"] = MultiTouch.__key_to_id(key)
                self.mts[i]["key"] = key
                return self.mts[i]
        return None

    def release_slot(self, key):
        for i in range(8):
            if self.mts[i]["key"] == key:
                self.mts[i]["occupy"] = False
                return

    def get_slot(self, key):
        for i in range(8):
            if self.mts[i]["occupy"] == True and self.mts[i]["key"] == key:
                return self.mts[i]
        return None

    def get_active_slot(self):
        return [mt for mt in self.mts if mt["occupy"]]

#region ADB Constants
EV_SYN = 0   # 0: report
EV_KEY = 1   # 1: down, 0: up
EV_ABS = 3   # 0: x, 1: y, 2: pressure
BTN_TOUCH = 330
ABS_MT_SLOT = 47
ABS_MT_TRACKING_ID = 57
BTN_TOOL_FINGER = 325
ABS_MT_POSITION_X = 53
ABS_MT_POSITION_Y = 54
ABS_MT_PRESSURE = 58
SYN_REPORT = 0
#endregion

class Adb:
    def __init__(self, config):
        adb_path = config["adb"]["path"]
        self.config = config
        self.adb_prefix = f"\"{adb_path}\""
        self.screen_width = 0
        self.screen_height = 0
        self.mouse_handle_count = 0
        self.mouse_handle_cycle = 5
        self.mt = MultiTouch()
        self.__adb_setup()
        self.__adb_executor_setup()

    def __adb_executor_setup(self):
        self.task_queue = queue.Queue()
        self.executor = threading.Thread(
            target=Adb.__adb_executor, args=(self,))
        self.executor.start()

    def __adb_executor(adb):
        while True:
            task_move_args = None
            tasks = []

            while True:
                fn, args = adb.task_queue.get()
                if fn == "touch_move":
                    task_move_args = args
                else:
                    tasks.append((fn, args))
                if adb.task_queue.empty():
                    break

            for t in tasks:
                fn, args = t
                getattr(adb, fn)(*args)
            if task_move_args != None:
                adb.touch_move(*task_move_args)

    def __adb_executor_queue(self, fn, args):
        self.task_queue.put((fn, args))

    def __adb(self, cmd):
        os.system(f"{self.adb_prefix} {cmd}")

    def __adb_r(self, cmd):
        return os.popen(f"{self.adb_prefix} {cmd}").read()

    def __adb_connect(self):
        ip_port = self.config["adb"]["ip_port"]
        self.__adb(f"connect {ip_port} > nul")

    def __adb_get_devices(self):
        return self.__adb_r("devices")

    def __extract_event(self, event):
        event = " ".join(event.replace('\n', '').split())
        match = re.search(r'(\d+)\s+name:\s+"(.*?)"', event)
        num, name = match.groups()
        return ("/dev/input/event" + num, name)

    def __adb_get_event(self):
        events = self.__adb_r("shell getevent -pl")
        events = events.split("/dev/input/event")
        events = events[1:]
        events = [e for e in events if "ABS_MT_SLOT" in e]
        if len(events) == 0:
            print("No event found.")
            exit()
        index = -1
        if len(events) == 1:
            index = 0
        else:
            for i in range(len(events)):
                e, e_name = self.__extract_event(events[i])
                print(f"{i}: {e_name}")
            index = int(input("Select an event: "))
        self.adb_event, _ = self.__extract_event(events[index])
        print(f"Using event: {self.adb_event}")

    def __adb_screen_size(self):
        size_str = self.__adb_r("shell wm size")
        size_arr = size_str.split()[2].split("x")
        self.screen_width = int(size_arr[1])
        self.screen_height = int(size_arr[0])

    def __adb_setup(self):
        self.__adb_connect()
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

        self.__adb_get_event()
        self.adb_prefix = f"{self.adb_prefix} -s {target_device}"
        self.__adb_screen_size()

    def __coord(self, x, y):
        return (x * self.screen_width, y * self.screen_height)

    def execute(self, fn, *args):
        self.__adb_executor_queue(fn, args)

    def click(self, x, y):
        x, y = self.__coord(x, y)
        self.__adb(f"shell input tap {x} {y}")

    def swipe(self, x, y, x_dst, y_dst):
        x, y = self.__coord(x, y)
        x_dst, y_dst = self.__coord(x_dst, y_dst)
        self.__adb(f"shell input swipe {x} {y} {x_dst} {y_dst} 20")

    def swipe_diff(self, x, y, x_diff, y_diff):
        x, y = self.__coord(x, y)
        min_extent = min(self.screen_width, self.screen_height)
        x_diff = x_diff * min_extent / 4
        y_diff = y_diff * min_extent / 4
        self.__adb(f"shell input swipe {x} {y} {x + x_diff} {y + y_diff} 20")

    def __event(self, cmd):
        self.__adb(f"shell sendevent {self.adb_event} {cmd}")

    def touch_start(self, key, x, y):
        self.__event(f"{EV_ABS} {ABS_MT_SLOT} 0")
        self.__event(f"{EV_ABS} {ABS_MT_TRACKING_ID} 66")
        self.__event(f"{EV_ABS} {ABS_MT_POSITION_X} {0xea}")
        self.__event(f"{EV_ABS} {ABS_MT_POSITION_Y} {0x1d7}")
        self.__event(f"{EV_SYN} {SYN_REPORT} 0")
        print(f"touch... start... {y} {x}")
        return True

    def touch_move(self, x, y):
        self.__event(f"{EV_ABS} {ABS_MT_SLOT} 0")
        self.__event(f"{EV_ABS} {ABS_MT_POSITION_X} {0xea - int(y * 50)}")
        self.__event(f"{EV_ABS} {ABS_MT_POSITION_Y} {0x1d7 + int(x * 50)}")
        self.__event(f"{EV_SYN} {SYN_REPORT} 0")

        print(f"Moving {x} {y}")
        self.mouse_handle_count += 1
        if self.mouse_handle_count == self.mouse_handle_cycle:
            self.mouse_handle_count = 0
            print(f"Moving {x} {y}")

    def touch_end(self, key):
        self.__event(f"{EV_ABS} {ABS_MT_SLOT} 0")
        self.__event(f"{EV_ABS} {ABS_MT_TRACKING_ID} -1")
        self.__event(f"{EV_SYN} {SYN_REPORT} 0")
        print(f"touch... end...")
#endregion

#region Window
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

import pygetwindow as gw

class Window:
    def __init__(self, config):
        self.title = config["window"]["title"]
        self.resolution = [int(v) for v in config["window"]["resolution"].split("x")]
        targets = [w for w in gw.getWindowsWithTitle(self.title) if self.title in w.title]
        if targets is None or len(targets) == 0:
            print("No window found.")
            exit()
        index = -1
        if len(targets) == 1:
            index = 0
        else:
            print("Multiple windows found.")
            for i in range(len(targets)):
                print(f"{i}: {targets[i].title}")
            index = int(input("Select a window: "))
        self.left_f = targets[index].left
        self.top_f = targets[index].top
        self.right_f = targets[index].right
        self.bottom_f = targets[index].bottom
        self.left = self.left_f
        self.right = self.right_f
        self.bottom = self.bottom_f
        resolution_aspect = self.resolution[1] / self.resolution[0]
        self.top = self.bottom - (self.right - self.left) * resolution_aspect
        self.top = round(self.top)
        self.calc_window()

    def calc_window(self):
        self.width = self.right - self.left
        self.height = self.bottom - self.top
        print(f"Window Screen [{self.left}, {self.right}], [{self.top}, {self.bottom}]")
#endregion

#region Reactor
import multiprocessing as mp

class Reactor:
    def __init__(self, config, adb, mapper):
        self.config = config
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

        self.player_x_pct = config["player"]["x"]
        self.player_y_pct = config["player"]["y"]
        self.player_x = 0
        self.player_y = 0
        self.vector_x = 0
        self.vector_y = 0
        self.vector_x_n = 0
        self.vector_y_n = 0

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
        self.win = Window(self.config)
        self.__calc_window()
        self.__setup_desktop()
        print("Start Running...")
        while True:
            msg = self.conn.recv()
            if msg == "exit":
                self.desktop_process.terminate()
                break
            try:
                self.__act(msg)
            except Exception as e:
                print(f"Error: {e}")
                debug_traceback(e)

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

    def __calc_window(self):
        self.win.calc_window()
        self.player_x = int(self.win.width * self.player_x_pct)
        self.player_y = int(self.win.height * self.player_y_pct)
        print(f"Player position is: {self.player_x}, {self.player_y}")

    def __act_util(self, fk, release):
        if fk == "CSAi":
            # ctrl + shift + alt + i
            self.win.left = self.mouse_x
            self.win.top = self.mouse_y
            self.__calc_window()
            print(f"Window Left-Top is: {self.mouse_x}, {self.mouse_y}")
            return True
        elif fk == "CSAo":
            # ctrl + shift + alt + o
            self.win.right = self.mouse_x
            self.win.bottom = self.mouse_y
            self.__calc_window()
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

    def __normalize(self, x, y, factor=1):
        x2 = x ** 2
        y2 = y ** 2
        sr = math.sqrt(x2 + y2)
        if sr < 0.001:
            return 0, 0
        return x * factor / sr, y * factor / sr

    def __act_key(self, fk, release):
        if release:
            return
        k, is_ctrl, is_shift, is_alt, is_fn = self.__unformat_key(fk)
        act = self.mapper.map(k)
        if k == "y":
            self.adb.execute("touch_start", 1, 2, 3)
        if k == "u":
            self.adb.execute("touch_end", 1)
        if act is None:
            return
        act_type = act[0]
        # debug
        if act_type == "click":
            self.adb.execute("click", act[1], act[2])
        elif act_type == "swipe":
            self.adb.execute("swipe", act[1], act[2], act[3], act[4])
        elif act_type == "swipe_direction":
            self.adb.execute("swipe_diff", act[1], act[2], act[3], act[4])
        elif act_type == "swipe_area":
            self.adb.execute("swipe_area", act[1], act[2])
        elif act_type == "pad" and not release:
            self.adb.execute("touch_end", self.mapper.pad_stop())
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
        if x <= self.win.left or x >= self.win.right or y <= self.win.top or y >= self.win.bottom:
            return True
        self.mouse_x_in = float(x - self.win.left) / float(self.win.width)
        self.mouse_y_in = float(y - self.win.top) / float(self.win.height)
        self.vector_x = self.mouse_x_in - self.player_x_pct
        self.vector_y = self.mouse_y_in - self.player_y_pct
        self.vector_x_n, self.vector_y_n = self.__normalize(self.vector_x, self.vector_y)
        # print(f"Vector is: {self.vector_x_n}, {self.vector_y_n}")
        # print(f"Mouse position is: {self.mouse_x_in}, {self.mouse_y_in}")
        if is_left:
            # todo
            pass
        if is_right and not release:
            pass
            # self.__act_mouse_right()
        self.adb.execute("touch_move", self.vector_x_n, self.vector_y_n)
        return True

    def __act_mouse_right(self):
        pad = self.mapper.pad()
        # self.adb.touch_start(self.mapper.pad_stop(), pad[1], pad[2])

#endregion

if __name__ == "__main__":
    config = __System_Config__()
    print(f"Using environment: {config['name']}")
    mapper = Mapper(config)
    adb = Adb(config)
    reactor = Reactor(config, adb, mapper)
    reactor.loop()
    while True:
        time.sleep(1)
