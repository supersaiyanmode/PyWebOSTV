import json
import time
from queue import Queue, Empty
from uuid import uuid4

from ws4py.client.threadedclient import WebSocketClient


SIGNATURE = "eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbmctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9.hrVRgjCwXVvE2OOSpDZ58hR+59aFNwYDyjQgKk3auukd7pcegmE2CzPCa0bJ0ZsRAcKkCTJrWo5iDzNhMBWRyaMOv5zWSrthlf7G128qvIlpMT0YNY+n/FaOHE73uLrS/g7swl3/qH/BGFG2Hu4RlL48eb3lLKqTt2xKHdCs6Cd4RMfJPYnzgvI4BNrFUKsjkcu+WD4OO2A27Pq1n50cMchmcaXadJhGrOqH5YmHdOCj5NSHzJYrsW0HPlpuAx/ECMeIZYDh6RMqaFM2DXzdKX9NmmyqzJ3o/0lkk/N97gfVRLW5hA29yeAwaCViZNCP8iC9aO0q9fQojoa7NQnAtw=="
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


class WebOSClient(WebSocketClient):
    PROMPTED = 1
    REGISTERED = 2

    def __init__(self, host):
        ws_url = "ws://{}:3000/".format(host)
        super(WebOSClient, self).__init__(ws_url, exclude_headers=["Origin"])
        self.waiters = {}

    def register(self, store):
        if "client_key" in store:
            REGISTRATION_PAYLOAD["payload"]["client-key"] = store["client_key"]

        response = self.send('register', None, REGISTRATION_PAYLOAD, block=True)
        for r in response:
            if "payload" in r and r["payload"].get("pairingType") == "PROMPT":
                yield WebOSClient.PROMPTED
            elif r["type"] == "registered":
                store["client_key"] = r["payload"]["client-key"]
                yield WebOSClient.REGISTERED
                break
            else:
                # TODO: Better exception.
                raise Exception("Failed to register.")

    def send(self, request_type, uri, payload, unique_id=None, block=False,
             timeout=60, callback=None):
        if unique_id is None:
            unique_id = str(uuid4())

        if block:
            wait_queue = Queue()
            self.waiters[unique_id] = (wait_queue.put, time.time())
        else:
            if callback is not None:
                self.waiters[unique_id] = (callback, time.time())

        obj = {"type": request_type, "id": unique_id, "payload": payload}
        if uri is not None:
            obj["uri"] = uri

        super(WebOSClient, self).send(json.dumps(obj))

        while block:
            try:
                yield wait_queue.get(block=True, timeout=timeout)
                wait_queue.task_done()
            except Empty:
                break

    def received_message(self, msg):
        obj = json.loads(str(msg))

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
