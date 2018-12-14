import json
from threading import Thread

from pywebostv.connection import WebOSClient


class FakeClient(WebOSClient):
    def __init__(self):
        super(FakeClient, self).__init__("ws://test")
        self.sent_message = None
        self.responses = {}

    def setup_response(self, uri, response):
        self.responses[uri] = {"payload": response}

    def send(self, obj):
        obj = json.loads(obj)
        self.sent_message = obj
        if obj.get("uri") in self.responses:
            Thread(target=self.start_response, args=(obj,)).start()

    def start_response(self, obj):
        unique_id = obj.get("id")
        res = {"id": unique_id}
        res.update(self.responses[obj["uri"]])
        self.received_message(json.dumps(res))

    def assert_sent_message(self, obj):
        assert self.sent_message == obj

    def assert_sent_message_without_id(self, obj):
        sent = self.sent_message
        sent.pop("id")
        assert sent == obj
