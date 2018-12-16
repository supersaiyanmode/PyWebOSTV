import json
import time
from threading import Thread

from pywebostv.connection import WebOSClient


class FakeClient(WebOSClient):
    def __init__(self, url="ws://test"):
        super(FakeClient, self).__init__(url)
        self.sent_message = None
        self.responses = {}

    def connect(self):
        pass

    def close(Self):
        pass

    def setup_response(self, uri, response):
        self.responses[uri] = {"payload": response}

    def setup_subscribe_response(self, uri, responses):
        self.responses[uri] = [{"payload": x} for x in responses]

    def send(self, obj):
        obj = json.loads(obj)
        self.sent_message = obj
        if obj.get("uri") in self.responses:
            if obj.get("type") == "request":
                Thread(target=self.start_response, args=(obj,)).start()
            elif obj.get("type") == "subscribe":
                Thread(target=self.start_subscribe, args=(obj,)).start()

    def start_response(self, obj):
        unique_id = obj.get("id")
        res = {"id": unique_id}
        res.update(self.responses[obj["uri"]])
        self.received_message(json.dumps(res))

    def start_subscribe(self, obj):
        unique_id = obj.get("id")
        for item in self.responses[obj["uri"]]:
            res = {"id": unique_id}
            res.update(item)
            self.received_message(json.dumps(res))
            time.sleep(0.1)

    def assert_sent_message(self, obj):
        assert self.sent_message == obj

    def assert_sent_message_without_id(self, obj):
        sent = self.sent_message
        sent.pop("id")
        assert sent == obj


class FakeMouseClient(FakeClient):
    def send(self, obj):
        self.sent_message = obj

    def assert_sent_message(self, obj):
        assert self.sent_message == obj
