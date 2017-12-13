import json
import time
from queue import Empty

from pytest import raises
from ws4py.client.threadedclient import WebSocketClient

from pywebostv.connection import arguments, process_payload, WebOSClient


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


class TestArgumentExtraction(object):
    def test_bad_argument_param(self):
        with raises(ValueError):
            arguments(None)

        with raises(ValueError):
            arguments({})

    def test_extract_positional_args(self):
        args = arguments(1)
        assert args([1], {2: 3}, "blah") == {2: 3}

        with raises(TypeError):
            assert args()

    def test_extract_keyword_args(self):
        args = arguments("arg")
        assert args(arg=1) == 1

        with raises(TypeError):
            assert args()

    def test_default_value(self):
        args = arguments(2, default={1, 2})
        assert args() == {1, 2}
        assert args("a", "b", "c") == "c"

    def test_postprocess(self):
        args = arguments(2, postprocess=lambda x: 1, default={1, 2})
        assert args() == {1, 2}
        assert args("a", "b", "c") == 1


class TestProcessPayload(object):
    def test_process_payload(self):
        payload = {
            "level1": {
                "level2": [1, 3],
                "level2a": lambda *a, **b: "{}{}".format(len(a), len(b))
            },
            "level1a": {1, 2}
        }
        expected = {
            "level1": {
                "level2": [1, 3],
                "level2a": "22"
            },
            "level1a": {1, 2}
        }
        assert process_payload(payload, 1, 2, a=4, b=5) == expected

    def test_just_callable_arg(self):
        assert process_payload(lambda x: x**2, 2) == 4


class TestWebOSClient(MockedClientBase):
    def test_unique_id(self):
        uid = "!23"
        client = WebOSClient("ws://abc:123")
        client.send('req', 'uri', {"item": "payload"}, unique_id=uid)

        self.assert_sent_message({
            "id": "!23",
            "payload": {"item": "payload"},
            "type": "req",
            "uri": "uri"
        })

    def test_get_queue(self):
        client = WebOSClient("ws://b")
        queue = client.send('req', 'uri', {"item": "payload"}, unique_id="1",
                            get_queue=True)
        client.received_message(json.dumps({"id": "1", "test": "test"}))

        assert queue.get(block=True, timeout=1) == dict(id="1", test="test")

    def test_send_callback(self):
        obj = {}

        def callback(res):
            obj["res"] = res

        client = WebOSClient("ws://b")
        client.send('req', 'uri', {"item": "payload"}, callback=callback,
                    unique_id="1")
        client.received_message(json.dumps({"id": "1", "test": "test"}))

        assert obj["res"] == dict(id="1", test="test")

    def test_send_minimum_params(self):
        client = WebOSClient("ws://a")
        client.send('req', None, None, unique_id="1")

        self.assert_sent_message({"type": "req", "id": "1"})

    def test_multiple_send(self):
        client = WebOSClient("ws://a")
        q1 = client.send('req', None, None, unique_id="1", get_queue=True)
        q2 = client.send('req', None, None, unique_id="2", get_queue=True)

        client.received_message(json.dumps({"id": "2", "test": "test2"}))
        client.received_message(json.dumps({"id": "1", "test": "test1"}))

        assert q1.get(block=True, timeout=1) == {"id": "1", "test": "test1"}
        assert q2.get(block=True, timeout=1) == {"id": "2", "test": "test2"}

    def test_clear_waiters(self):
        client = WebOSClient("ws://a")
        q1 = client.send('req', None, None, unique_id="1", get_queue=True,
                         cur_time=lambda: time.time() - 80)
        q2 = client.send('req', None, None, unique_id="2", get_queue=True,
                         cur_time=lambda: time.time() - 20)

        client.received_message(json.dumps({"id": "2", "test": "test2"}))
        client.received_message(json.dumps({"id": "1", "test": "test1"}))

        with raises(Empty):
            assert q1.get(block=True, timeout=1)

        assert q2.get(block=True, timeout=1) == {"id": "2", "test": "test2"}
