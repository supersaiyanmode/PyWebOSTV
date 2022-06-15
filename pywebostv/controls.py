try:
    # begin try for python <= 3.5
    from collections import Callable
except ImportError:
    # after try for python >= 3.10
    from typing import Callable

from queue import Empty
from uuid import uuid4

from pywebostv.connection import WebOSWebSocketClient
from pywebostv.model import Application, InputSource, AudioOutputSource


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


def standard_validation(payload):
    if not payload.pop("returnValue", None):
        return False, payload.pop("errorText", "Unknown error.")
    return True, None


class WebOSControlBase(object):
    COMMANDS = {}

    def __init__(self, client):
        self.client = client
        self.subscriptions = {}

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
        subscribe_prefix = "subscribe_"
        unsubscribe_prefix = "unsubscribe_"
        if name in self.COMMANDS:
            return self.exec_command(name, self.COMMANDS[name])
        elif name.startswith(subscribe_prefix):
            subscribe_name = name.lstrip(subscribe_prefix)
            sub_cmd_info = self.COMMANDS.get(subscribe_name)
            if not sub_cmd_info:
                raise AttributeError(name)
            elif not sub_cmd_info.get("subscription"):
                raise AttributeError("Subscription not found or allowed.")
            else:
                return self.subscribe(subscribe_name, sub_cmd_info)
        elif name.startswith(unsubscribe_prefix):
            unsubscribe_name = name.lstrip(unsubscribe_prefix)
            sub_cmd_info = self.COMMANDS.get(unsubscribe_name)
            if not sub_cmd_info:
                raise AttributeError(name)
            elif not sub_cmd_info.get("subscription"):
                raise AttributeError("Subscription not found or allowed.")
            else:
                return self.unsubscribe(unsubscribe_name, sub_cmd_info)
        else:
            raise AttributeError(name)

    def exec_command(self, cmd, cmd_info):
        def request_func(*args, **kwargs):
            callback = kwargs.pop('callback', None)
            response_valid = cmd_info.get("validation", lambda p: (True, None))
            return_fn = cmd_info.get('return', lambda x: x)
            block = kwargs.pop('block', True)
            timeout = kwargs.pop('timeout', 60)
            params = process_payload(cmd_info.get("payload"), *args, **kwargs)

            # callback in the args has higher priority.
            if callback:
                def callback_wrapper(res):
                    payload = res.get("payload")
                    if res.get("type", None) == "error":
                        callback(False, res.get("type", "Unknown Communication Error"))
                    status, message = response_valid(payload)
                    if not status:
                        return callback(False, message)
                    return callback(True, return_fn(payload))

                self.request(cmd_info["uri"], params, timeout=timeout,
                             callback=callback_wrapper)
            elif block:
                res = self.request(cmd_info["uri"], params, block=block,
                                   timeout=timeout)
                if res.get("type", None) == "error":
                    raise IOError(res.get("error", "Unknown Communication Error"))
                payload = res.get("payload")
                status, message = response_valid(payload)
                if not status:
                    raise IOError(message)

                return return_fn(payload)
            else:
                self.request(cmd_info["uri"], params)
        return request_func

    def subscribe(self, name, cmd_info):
        def request_func(callback):
            response_valid = cmd_info.get("validation", lambda p: (True, None))
            return_fn = cmd_info.get('return', lambda x: x)

            def callback_wrapper(payload):
                status, message = response_valid(payload)
                if not status:
                    return callback(False, message)
                return callback(True, return_fn(payload))

            if name in self.subscriptions:
                raise ValueError("Already subscribed.")

            uid = str(uuid4())
            self.subscriptions[name] = uid
            self.client.subscribe(cmd_info["uri"], uid, callback_wrapper)
        return request_func

    def unsubscribe(self, name, cmd_info):
        def request_func():
            uid = self.subscriptions.get(name)
            if not uid:
                raise ValueError("Not subscribed.")
            self.client.unsubscribe(uid)
            del self.subscriptions[name]
        return request_func


class MediaControl(WebOSControlBase):
    def list_audio_output_sources(self):
        sources = ['tv_speaker', 'external_speaker', 'soundbar', 'bt_soundbar', 'tv_external_speaker']

        return [AudioOutputSource(x) for x in sources]

    COMMANDS = {
        "volume_up": {"uri": "ssap://audio/volumeUp"},
        "volume_down": {"uri": "ssap://audio/volumeDown"},
        "get_volume": {
            "uri": "ssap://audio/getVolume",
            "validation": standard_validation,
            "subscription": True,
        },
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
        "get_audio_output": {
            "uri": "ssap://audio/getSoundOutput",
            "validation": standard_validation,
            "subscription": True,
            "return": lambda p: AudioOutputSource(p["soundOutput"])
        },
        "set_audio_output": {
            "uri": "ssap://audio/changeSoundOutput",
            "args": [AudioOutputSource],
            "kwargs": {},
            "payload": {
                "output": arguments(0, postprocess=lambda source: source.data),
            },
            "validation": standard_validation,
        }
     }


class TvControl(WebOSControlBase):
    COMMANDS = {
        "channel_down": {"uri": "ssap://tv/channelDown"},
        "channel_up": {"uri": "ssap://tv/channelUp"},
        "set_channel_with_id": {
            "uri": "ssap://tv/openChannel",
            "args": [str],
            "payload": {
                "channelId": arguments(0)
            }
        },
        "get_current_channel": {
            "uri": "ssap://tv/getCurrentChannel",
            "validation": standard_validation,
            "subscription": True
        },
        "channel_list": {"uri": "ssap://tv/getChannelList"},
        "get_current_program": {
            "uri": "ssap://tv/getChannelProgramInfo",
            "validation": standard_validation
        }
     }


class SystemControl(WebOSControlBase):
    COMMANDS = {
        "power_off": {"uri": "ssap://system/turnOff"},
        "screen_off": {
            "uri": "ssap://com.webos.service.tvpower/power/turnOffScreen",
            "payload": {"standbyMode": "active"}
        },
        "screen_on": {
            "uri": "ssap://com.webos.service.tvpower/power/turnOnScreen",
            "payload": {"standbyMode": "active"}
        },
        "info": {
            "uri": "ssap://com.webos.service.update/getCurrentSWInformation",
            "validation": standard_validation,
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
            "validation": standard_validation,
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
            "validation": standard_validation,
        },
        "get_current": {
            "uri": "ssap://com.webos.applicationManager/getForegroundAppInfo",
            "args": [],
            "kwargs": {},
            "payload": {},
            "validation": standard_validation,
            "return": lambda p: p["appId"],
            "subscription": True,
        },
        "close": {
            "uri": "ssap://system.launcher/close",
            "args": [dict],
            "kwargs": {},
            "payload": arguments(0),
            "validation": standard_validation,
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
        },
        "menu": {
            "command": [["type", "button"], ["name", "MENU"]]
        },
        "ok": {
            "command": [["type", "button"], ["name", "ENTER"]]
        },
        "dash": {
            "command": [["type", "button"], ["name", "DASH"]]
        },
        "info": {
            "command": [["type", "button"], ["name", "INFO"]]
        },
        "num_1": {
            "command": [["type", "button"], ["name", "1"]]
        },
        "num_2": {
            "command": [["type", "button"], ["name", "2"]]
        },
        "num_3": {
            "command": [["type", "button"], ["name", "3"]]
        },
        "num_4": {
            "command": [["type", "button"], ["name", "4"]]
        },
        "num_5": {
            "command": [["type", "button"], ["name", "5"]]
        },
        "num_6": {
            "command": [["type", "button"], ["name", "6"]]
        },
        "num_7": {
            "command": [["type", "button"], ["name", "7"]]
        },
        "num_8": {
            "command": [["type", "button"], ["name", "8"]]
        },
        "num_9": {
            "command": [["type", "button"], ["name", "9"]]
        },
        "num_0": {
            "command": [["type", "button"], ["name", "0"]]
        },
        "asterisk": {
            "command": [["type", "button"], ["name", "ASTERISK"]]
        },
        "cc": {
            "command": [["type", "button"], ["name", "CC"]]
        },
        "exit": {
            "command": [["type", "button"], ["name", "EXIT"]]
        },
        "mute": {
            "command": [["type", "button"], ["name", "MUTE"]]
        },
        "red": {
            "command": [["type", "button"], ["name", "RED"]]
        },
        "green": {
            "command": [["type", "button"], ["name", "GREEN"]]
        },
        "yellow": {
            "command": [["type", "button"], ["name", "YELLOW"]]
        },
        "blue": {
            "command": [["type", "button"], ["name", "BLUE"]]
        },
        "volume_up": {
            "command": [["type", "button"], ["name", "VOLUMEUP"]]
        },
        "volume_down": {
            "command": [["type", "button"], ["name", "VOLUMEDOWN"]]
        },
        "channel_up": {
            "command": [["type", "button"], ["name", "CHANNELUP"]]
        },
        "channel_down": {
            "command": [["type", "button"], ["name", "CHANNELDOWN"]]
        },
        "play": {
            "command": [["type", "button"], ["name", "PLAY"]]
        },
        "pause": {
            "command": [["type", "button"], ["name", "PAUSE"]]
        },
        "stop": {
            "command": [["type", "button"], ["name", "STOP"]]
        },
        "rewind": {
            "command": [["type", "button"], ["name", "REWIND"]]
        },
        "fastforward": {
            "command": [["type", "button"], ["name", "FASTFORWARD"]]
        }
    }

    def __init__(self, *args, **kwargs):
        self.ws_class = kwargs.pop('ws_class', WebOSWebSocketClient)
        super(InputControl, self).__init__(*args, **kwargs)

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
            raise IOError("Unable to connect to mouse.")
        self.mouse_ws = self.ws_class(sock_path)
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
            "validation": standard_validation,
            "return": lambda p: [InputSource(x) for x in p["devices"]],
        },
        "set_source": {
            "uri": "ssap://tv/switchInput",
            "args": [InputSource],
            "kwargs": {},
            "payload": {
                "inputId": arguments(0, postprocess=lambda inp: inp["id"]),
            },
            "validation": standard_validation,
        },
    }
