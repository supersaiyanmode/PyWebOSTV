# -*- coding: utf-8 -*-

import json
import time
from threading import RLock
from uuid import uuid4
try:
    from queue import Queue, Empty
except ImportError:
    from Queue import Queue, Empty

from ws4py.client.threadedclient import WebSocketClient

from pywebostv.discovery import discover


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
            "READ_COUNTRY_INFO",
            "READ_SETTINGS",
            "CONTROL_TV_SCREEN",
            "CONTROL_TV_STANBY",
            "CONTROL_FAVORITE_GROUP",
            "CONTROL_USER_INFO",
            "CHECK_BLUETOOTH_DEVICE",
            "CONTROL_BLUETOOTH",
            "CONTROL_TIMER_INFO",
            "STB_INTERNAL_CONNECTION",
            "CONTROL_RECORDING",
            "READ_RECORDING_STATE",
            "WRITE_RECORDING_LIST",
            "READ_RECORDING_LIST",
            "READ_RECORDING_SCHEDULE",
            "WRITE_RECORDING_SCHEDULE",
            "READ_STORAGE_DEVICE_LIST",
            "READ_TV_PROGRAM_INFO",
            "CONTROL_BOX_CHANNEL",
            "READ_TV_ACR_AUTH_TOKEN",
            "READ_TV_CONTENT_STATE",
            "READ_TV_CURRENT_TIME",
            "ADD_LAUNCHER_CHANNEL",
            "SET_CHANNEL_SKIP",
            "RELEASE_CHANNEL_SKIP",
            "CONTROL_CHANNEL_BLOCK",
            "DELETE_SELECT_CHANNEL",
            "CONTROL_CHANNEL_GROUP",
            "SCAN_TV_CHANNELS",
            "CONTROL_TV_POWER",
            "CONTROL_WOL"
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


class WebOSWebSocketClient(WebSocketClient):
    @property
    def handshake_headers(self):
        headers = super(WebOSWebSocketClient, self).handshake_headers
        return [(k, v) for k, v in headers if k.lower() != 'origin']


class WebOSClient(WebOSWebSocketClient):
    PROMPTED = 1
    REGISTERED = 2

    def __init__(self, host):
        ws_url = "ws://{}:3000/".format(host)
        super(WebOSClient, self).__init__(ws_url)
        self.waiters = {}
        self.waiter_lock = RLock()
        self.subscribers = {}
        self.subscriber_lock = RLock()
        self.send_lock = RLock()

    @staticmethod
    def discover():
        res = discover("urn:schemas-upnp-org:device:MediaRenderer:1",
                       keyword="LG", hosts=True, retries=3)
        return [WebOSClient(x) for x in res]

    def register(self, store, timeout=60):
        if "client_key" in store:
            REGISTRATION_PAYLOAD["client-key"] = store["client_key"]

        queue = self.send_message('register', None, REGISTRATION_PAYLOAD,
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

    def send_message(self, request_type, uri, payload, unique_id=None,
                     get_queue=False, callback=None, cur_time=time.time):
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
            obj["payload"] = payload

        with self.send_lock:
            self.send(json.dumps(obj))

        if get_queue:
            return wait_queue

    def subscribe(self, uri, unique_id, callback, payload=None):
        def func(obj):
            callback(obj.get("payload"))

        with self.subscriber_lock:
            self.subscribers[unique_id] = uri
        self.send_message('subscribe', uri, payload, unique_id=unique_id,
                          callback=func, cur_time=lambda: None)
        return unique_id

    def unsubscribe(self, unique_id):
        with self.subscriber_lock:
            uri = self.subscribers.pop(unique_id, None)

        if not uri:
            raise ValueError("Subscription not found: {}".format(unique_id))

        with self.waiter_lock:
            self.waiters.pop(unique_id)

        self.send_message('unsubscribe', uri, payload=None)

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
            if created_time and created_time + delta < cur_time:
                to_clear.append(key)

        for key in to_clear:
            self.waiters.pop(key)
