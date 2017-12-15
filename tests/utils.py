import json

from ws4py.client.threadedclient import WebSocketClient


class MockedClientBase(object):
    def setup_method(self):
        test = self

        def fake_send(self, msg):
            test.sent_message = msg

        self.backup_send = WebSocketClient.send
        WebSocketClient.send = fake_send

    def teardown_method(self):
        WebSocketClient.send = self.backup_send

    def assert_sent_message(self, obj):
        assert json.loads(self.sent_message) == obj

    def assert_sent_message_without_id(self, obj):
        sent = json.loads(self.sent_message)
        sent.pop("id")
        assert sent == obj
