from collections import Callable
from queue import Empty

from pywebostv.connection import WebOSWebSocketClient
from pywebostv.model import Application, InputSource


ARGS_NONE = ()


def arguments(val, postprocess=lambda x: x, default=ARGS_NONE):
    if type(val) not in (str, int):
        raise ValueError("Only numeric indices, or string keys allowed.")

    def func(*args, **kwargs):
        try:
            if isinstance(val, int):
                if default is ARGS_NONE:
                    return postprocess(args[val])
                valid_index = 0 <= val < len(args)
                return postprocess(args[val]) if valid_index else default
            elif isinstance(val, str):
                if default is ARGS_NONE:
                    return postprocess(kwargs[val])
                return postprocess(kwargs[val]) if val in kwargs else default
        except (KeyError, IndexError):
            raise TypeError("Bad arguments.")
    return func


def process_payload(obj, *args, **kwargs):
    if isinstance(obj, list):
        return [process_payload(item, *args, **kwargs) for item in obj]
    elif isinstance(obj, dict):
        return {k: process_payload(v, *args, **kwargs) for k, v in obj.items()}
    elif isinstance(obj, Callable):
        return obj(*args, **kwargs)
    else:
        return obj


class WebOSControlBase(object):
    COMMANDS = {}

    def __init__(self, client):
        self.client = client

    def request(self, uri, params, callback=None, block=False, timeout=60):
        if block:
            queue = self.client.send_message('request', uri, params,
                                             get_queue=True)
            try:
                return queue.get(timeout=timeout, block=True)
            except Empty:
                raise Exception("Failed.")
        else:
            self.client.send_message('request', uri, params, callback=callback)

    def __getattr__(self, name):
        if name in self.COMMANDS:
            return self.exec_command(name, self.COMMANDS[name])
        raise AttributeError(name)

    def exec_command(self, cmd, cmd_info):
        def request_func(*args, **kwargs):
            callback = kwargs.pop('callback', None)
            response_valid = cmd_info.get("validation", lambda p: True)
            return_fn = cmd_info.get('return', lambda x: x)
            block = kwargs.pop('block', False)
            timeout = kwargs.pop('timeout', 60)
            params = process_payload(cmd_info.get("payload"), *args, **kwargs)

            # callback in the args has higher priority.
            if callback:
                def callback_wrapper(res):
                    if not response_valid(res):
                        return callback(False, cmd_info["validation_error"])
                    return callback(True, return_fn(res.get("payload")))

                self.request(cmd_info["uri"], params, timeout=timeout,
                             callback=callback_wrapper)
            elif block:
                res = self.request(cmd_info["uri"], params, block=block,
                                   timeout=timeout)
                if not response_valid(res):
                    raise ValueError(cmd_info["validation_error"])

                return return_fn(res.get("payload"))
            else:
                self.request(cmd_info["uri"], params)
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
        "list_apps": {
            "uri": "ssap://com.webos.applicationManager/listApps",
            "args": [],
            "kwargs": {},
            "payload": {},
            "validation": lambda payload: payload.pop("returnValue"),
            "validation_error": "Unable to retrieve apps list.",
            "return": lambda payload: [Application(x) for x in payload["apps"]]
        },
        "launch": {
            "uri": "ssap://system.launcher/launch",
            "args": [Application],
            "kwargs": {"content_id": str, "params": dict},
            "payload": {
                "id": arguments(0, postprocess=lambda app: app["id"]),
                "contentId": arguments("content_id", default=None),
                "params": arguments("params", default=None)
            },
            "validation": lambda payload: payload.pop("returnValue"),
            "validation_error": "Unable to launch application.",
        },
        "get_current": {
            "uri": "ssap://com.webos.applicationManager/getForegroundAppInfo",
            "args": [],
            "kwargs": {},
            "payload": {},
            "validity": lambda p: p.pop("returnValue"),
            "return": lambda p: p["appId"],
        },
        "close": {
            "uri": "ssap://system.launcher/close",
            "args": [dict],
            "kwargs": {},
            "payload": arguments(0),
            "validation": lambda p: p.pop("returnValue"),
            "validation_error": "Something went wrong while closing app.",
        }
    }


class InputControl(WebOSControlBase):
    COMMANDS = {
        "type": {
            "uri": "ssap://com.webos.service.ime/insertText",
            "args": [str],
            "payload": {"text": arguments(0), "replace": 0}
        },
        "delete": {
            "uri": "ssap://com.webos.service.ime/deleteCharacters",
            "args": [int],
            "payload": {"count": arguments(0)}
        },
        "enter": {"uri": "ssap://com.webos.service.ime/sendEnterKey"},
    }

    INPUT_COMMANDS = {
        "move": {
            "command": [["type", "move"],
                        ["dx", arguments(0)],
                        ["dy", arguments(1)],
                        ["down", arguments("drag", default=0)]]
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
        self.mouse_ws = WebOSWebSocketClient(sock_path)
        self.mouse_ws.connect()

    def disconnect_input(self):
        self.mouse_ws.close()

    def exec_mouse_command(self, cmd_name, cmd_info):
        def request_func(*args, **kwargs):
            params = process_payload(cmd_info["command"], *args, **kwargs)
            payload = "\n".join(":".join(str(y) for y in x) for x in params)
            payload += "\n\n"
            self.mouse_ws.send(payload)
        return request_func


class SourceControl(WebOSControlBase):
    COMMANDS = {
        "list_sources": {
            "uri": "ssap://tv/getExternalInputList",
            "args": [],
            "kwargs": {},
            "payload": {},
            "validation": lambda payload: payload.pop("returnValue"),
            "validation_error": "Unable to get list of sources.",
            "return": lambda p: [InputSource(x) for x in p["devices"]],
        },
        "set_source": {
            "uri": "ssap://tv/switchInput",
            "args": [InputSource],
            "kwargs": {},
            "payload": {
                "inputId": arguments(0, postprocess=lambda inp: inp["id"]),
            },
            "validation": lambda p: p.pop("returnValue"),
            "validation_error": "Unable to set source.",
        },
    }
