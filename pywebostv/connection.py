import json
import time
from collections import Sequence, Mapping, Callable
from queue import Queue, Empty
from threading import RLock, Event
from uuid import uuid4

from ws4py.client.threadedclient import WebSocketClient

from pywebostv.discovery import discover
from pywebostv.model import Application


SIGNATURE = ("eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbm" +
             "ctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9.hrVRgjCwXVvE2OOSpDZ58hR" +
             "+59aFNwYDyjQgKk3auukd7pcegmE2CzPCa0bJ0ZsRAcKkCTJrWo5iDzNhMBWRy" +
             "aMOv5zWSrthlf7G128qvIlpMT0YNY+n/FaOHE73uLrS/g7swl3/qH/BGFG2Hu4" +
             "RlL48eb3lLKqTt2xKHdCs6Cd4RMfJPYnzgvI4BNrFUKsjkcu+WD4OO2A27Pq1n" +
             "50cMchmcaXadJhGrOqH5YmHdOCj5NSHzJYrsW0HPlpuAx/ECMeIZYDh6RMqaFM" +
             "2DXzdKX9NmmyqzJ3o/0lkk/N97gfVRLW5hA29yeAwaCViZNCP8iC9aO0q9fQoj" +
             "oa7NQnAtw==")

REGISTRATION_PAYLOAD = {
    "forcePairing": False,
    "manifest": {
        "appVersion": "1.1",
        "manifestVersion": 1,
        "permissions": [
            "LAUNCH",
            "LAUNCH_WEBAPP",
            "APP_TO_APP",
            "CLOSE",
            "TEST_OPEN",
            "TEST_PROTECTED",
            "CONTROL_AUDIO",
            "CONTROL_DISPLAY",
            "CONTROL_INPUT_JOYSTICK",
            "CONTROL_INPUT_MEDIA_RECORDING",
            "CONTROL_INPUT_MEDIA_PLAYBACK",
            "CONTROL_INPUT_TV",
            "CONTROL_POWER",
            "READ_APP_STATUS",
            "READ_CURRENT_CHANNEL",
            "READ_INPUT_DEVICE_LIST",
            "READ_NETWORK_STATE",
            "READ_RUNNING_APPS",
            "READ_TV_CHANNEL_LIST",
            "WRITE_NOTIFICATION_TOAST",
            "READ_POWER_STATE",
            "READ_COUNTRY_INFO"
        ],
        "signatures": [
            {
                "signature": SIGNATURE,
                "signatureVersion": 1
            }
        ],
        "signed": {
            "appId": "com.lge.test",
            "created": "20140509",
            "localizedAppNames": {
                "": "LG Remote App",
                "ko-KR": u"리모컨 앱",
                "zxx-XX": u"ЛГ Rэмotэ AПП"
            },
            "localizedVendorNames": {
                "": "LG Electronics"
            },
            "permissions": [
                "TEST_SECURE",
                "CONTROL_INPUT_TEXT",
                "CONTROL_MOUSE_AND_KEYBOARD",
                "READ_INSTALLED_APPS",
                "READ_LGE_SDX",
                "READ_NOTIFICATIONS",
                "SEARCH",
                "WRITE_SETTINGS",
                "WRITE_NOTIFICATION_ALERT",
                "CONTROL_POWER",
                "READ_CURRENT_CHANNEL",
                "READ_RUNNING_APPS",
                "READ_UPDATE_INFO",
                "UPDATE_FROM_REMOTE_APP",
                "READ_LGE_TV_INPUT_EVENTS",
                "READ_TV_CURRENT_TIME"
            ],
            "serial": "2f930e2d2cfe083771f68e4fe7bb07",
            "vendorId": "com.lge"
        }
    },
    "pairingType": "PROMPT"
}

ARGS_NONE = ()

def arguments(val, default=ARGS_NONE):
    if type(val) not in (str, int):
        raise ValueError("Only numeric indices, or string keys allowed.")

    def func(*args, **kwargs):
        try:
            if isinstance(val, int):
                if default is ARGS_NONE:
                    return args[val]
                return args[val] if 0 <= val < len(args) else default
            elif isinstance(val, str):
                if default is ARGS_NONE:
                    return kwargs[val]
                return kwargs.get(val, default)
        except (KeyError, IndexError):
            raise TypeError("Bad arguments.")
    return func


def process_payload(obj, *args, **kwargs):
    if isinstance(obj, list):
        res = []
        for item in obj:
            if isinstance(item, Callable):
                res.append(item(*args, **kwargs))
            else:
                res.append(process_payload(item, *args, **kwargs))
        return res
    elif isinstance(obj, dict):
        res = {}
        for key, value in obj.items():
            if isinstance(value, Callable):
                res[key] = value(*args, **kwargs)
            else:
                res[key] = process_payload(value, *args, **kwargs)
        return res
    else:
        return obj


class WebOSClient(WebSocketClient):
    PROMPTED = 1
    REGISTERED = 2

    def __init__(self, host):
        ws_url = "ws://{}:3000/".format(host)
        super(WebOSClient, self).__init__(ws_url, exclude_headers=["Origin"])
        self.waiters = {}
        self.waiter_lock = RLock()
        self.send_lock = RLock()

    @staticmethod
    def discover():
        res = discover("urn:schemas-upnp-org:device:MediaRenderer:1",
                       keyword="LG", hosts=True, retries=3)
        return [WebOSClient(x) for x in res]

    def register(self, store, timeout=60):
        if "client_key" in store:
            REGISTRATION_PAYLOAD["client-key"] = store["client_key"]

        queue = self.send('register', None, REGISTRATION_PAYLOAD,
                          get_queue=True)
        while True:
            try:
                item = queue.get(block=True, timeout=timeout)
            except Empty:
                raise Exception("Timeout.")

            if item.get("payload", {}).get("pairingType") == "PROMPT":
                yield WebOSClient.PROMPTED
            elif item["type"] == "registered":
                store["client_key"] = item["payload"]["client-key"]
                yield WebOSClient.REGISTERED
                break
            else:
                # TODO: Better exception.
                raise Exception("Failed to register.")

    def send(self, request_type, uri, payload, unique_id=None, get_queue=False,
             callback=None, cur_time=time.time):
        if unique_id is None:
            unique_id = str(uuid4())

        if get_queue:
            wait_queue = Queue()
            callback = wait_queue.put

        if callback is not None:
            with self.waiter_lock:
                self.waiters[unique_id] = (callback, cur_time())

        obj = {"type": request_type, "id": unique_id}
        if uri is not None:
            obj["uri"] = uri
        if payload is not None:
            if isinstance(payload, str) or True:
                obj["payload"] = payload
            else:
                obj["payload"] = json.dumps(payload)

        with self.send_lock:
            super(WebOSClient, self).send(json.dumps(obj))

        if get_queue:
            return wait_queue

    def received_message(self, msg):
        obj = json.loads(str(msg))

        with self.waiter_lock:
            self.clear_old_waiters()
            if "id" in obj and obj["id"] in self.waiters:
                callback, created_time = self.waiters[obj["id"]]
                callback(obj)

    def clear_old_waiters(self, delta=60):
        to_clear = []
        cur_time = time.time()
        for key, value in self.waiters.items():
            callback, created_time = value
            if created_time + delta < cur_time:
                to_clear.append(key)

        for key in to_clear:
            self.waiters.pop(key)


class WebOSControlBase(object):
    COMMANDS = []

    def __init__(self, client):
        self.client = client

    def request(self, uri, params, callback=None, block=False, timeout=60):
        if block:
            queue = self.client.send('request', uri, params, get_queue=True)
            try:
                return queue.get(timeout=timeout, block=True)
            except Empty:
                raise Exception("Failed.")
        else:
            self.client.send('request', uri, params, callback=callback)

    def __getattr__(self, name):
        if name in self.COMMANDS:
            return self.exec_command(name, self.COMMANDS[name])
        raise AttributeError(name)

    def exec_command(self, cmd, cmd_info):
        def request_func(*args, **kwargs):
            callback = kwargs.pop('callback', None)
            block = kwargs.pop('block', False)
            timeout = kwargs.pop('timeout', 60)
            params = process_payload(cmd_info.get("payload"), *args, **kwargs)
            return self.request(cmd_info["uri"], params,
                                callback=callback, block=block, timeout=timeout)
        return request_func


class MediaControl(WebOSControlBase):
    COMMANDS = {
        "volume_up": {"uri": "ssap://audio/volumeUp"},
        "volume_down": {"uri": "ssap://audio/volumeDown"},
        "get_volume": {"uri": "ssap://audio/getVolume"},
        "set_volume": {
            "uri": "ssap://audio/setVolume",
            "args": [int],
            "payload": {"volume": arguments(0)}
        },
        "mute": {
            "uri": "ssap://audio/setMute",
            "args": [bool],
            "payload": {"mute": arguments(0)}
        },
        "play": {"uri": "ssap://media.controls/play"},
        "pause": {"uri": "ssap://media.controls/pause"},
        "stop": {"uri": "ssap://media.controls/stop"},
        "rewind": {"uri": "ssap://media.controls/rewind"},
        "fast_forward": {"uri": "ssap://media.controls/fastForward"},
     }


class SystemControl(WebOSControlBase):
    COMMANDS = {
        "power_off": {"uri": "ssap://system/turnOff"},
        "info": {
            "uri": "ssap://com.webos.service.update/getCurrentSWInformation"
        },
        "notify": {
            "uri": "ssap://system.notifications/createToast",
            "args": [str],
            "payload": {"message": arguments(0)}
        }
    }


class ApplicationControl(WebOSControlBase):
    COMMANDS = {
    }

    def list_apps(self):
        res = self.request("ssap://com.webos.applicationManager/listApps",
                           params=None, block=True)
        if not res.get("payload", {}).get("returnValue"):
            raise Exception("Could not list apps.")

        return [Application(x) for x in res["payload"]["apps"]]

    def launch(self, app, content_id=None, params=None, block=True,
               callback=None, timeout=None):
        payload = {"id": app["id"]}
        if content_id is not None:
            payload["contentId"] = content_id
        if params is not None:
            payload["params"] = params

        response_received = Event()
        launch_data = []

        def save_launch_info(response):
            launch_info = response["payload"]
            if launch_info.get("returnValue"):
                launch_info.pop("returnValue")
                launch_data.append(launch_info)
            else:
                launch_info = None

            if block:
                response_received.set()
            if callback:
                callback(launch_info)

        self.request("ssap://system.launcher/launch", payload, block=False,
                     callback=save_launch_info)

        if block:
            response_received.wait(timeout=timeout)
            if not launch_data:
                raise Exception("Unable to launch app.")
            return launch_data[0]

    def close(self, launch_info, block=False, callback=None):
        sess_id = launch_info.get("sessionId")
        if not sess_id:
            raise Exception("Session not found.")

        self.request("ssap://system.launcher/close", launch_info, block=block,
                     callback=callback)


class InputControl(WebOSControlBase):
    COMMANDS = {
        "type": {
            "uri": "ssap://com.webos.service.ime/insertText",
            "args": [str],
            "payload": {"text": arguments(0), "replace": 0}
        },
        "delete": {
            "uri": "ssap://com.webos.service.ime/deleteCharacters",
            "payload": [int],
            "payload": {"count": arguments(0)}
        },
        "enter": {"uri": "ssap://com.webos.service.ime/sendEnterKey"},
    }

    INPUT_COMMANDS = {
        "move": {
            "command": [["type", "move"],
                        ["dx", arguments(0)],
                        ["dy", arguments(1)],
                        ["down", arguments("drag", 0)]]
        },
        "click": {
            "command": [["type", "click"]]
        },
        "scroll": {
            "command": [["type", "scroll"],
                        ["dx", arguments(0)],
                        ["dy", arguments(1)]]
        },
        "left": {
            "command": [["type", "button"], ["name", "LEFT"]]
        },
        "right": {
            "command": [["type", "button"], ["name", "RIGHT"]]
        },
        "down": {
            "command": [["type", "button"], ["name", "DOWN"]]
        },
        "up": {
            "command": [["type", "button"], ["name", "UP"]]
        },
        "home": {
            "command": [["type", "button"], ["name", "HOME"]]
        },
        "back": {
            "command": [["type", "button"], ["name", "BACK"]]
        }
    }

    def __getattr__(self, name):
        if name in self.INPUT_COMMANDS:
            return self.exec_mouse_command(name, self.INPUT_COMMANDS[name])
        if name in self.COMMANDS:
            return super(InputControl, self).__getattr__(name)
        raise AttributeError(name)

    def connect_input(self):
        uri = "ssap://com.webos.service.networkinput/getPointerInputSocket"
        res = self.request(uri, None, block=True)
        sock_path = res.get("payload").get("socketPath")
        if not sock_path:
            raise Exception("Unable to connect to mouse.")
        self.mouse_ws = WebSocketClient(sock_path, exclude_headers=["Origin"])
        self.mouse_ws.connect()

    def disconnect_input(self):
        self.mouse_ws.close()

    def exec_mouse_command(self, cmd_name, cmd_info):
        def request_func(*args, **kwargs):
            callback = kwargs.pop('callback', None)
            block = kwargs.pop('block', True)
            timeout = kwargs.pop('timeout', 60)
            params = process_payload(cmd_info["command"], *args, **kwargs)
            payload = "\n".join(":".join(str(y) for y in x) for x in params)
            payload += "\n\n"
            self.mouse_ws.send(payload)
        return request_func
