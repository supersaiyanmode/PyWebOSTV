import json
import time
from queue import Empty
from threading import Event, Thread

from pytest import raises

import pywebostv.connection
from pywebostv.connection import WebOSClient

from utils import MockedClientBase


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

    def test_subscription(self):
        result = []
        result_event = Event()

        def callback(obj):
            result.append(obj)
            result_event.set()

        client = WebOSClient("ws://a")
        uri = client.subscribe('unique_uri', callback)

        client.received_message(json.dumps({"id": uri, "payload": [1]}))
        client.received_message(json.dumps({"id": uri, "payload": [2]}))
        client.received_message(json.dumps({"id": uri, "payload": [3]}))

        result_event.wait()
        assert result == [[1], [2], [3]]

        result = []
        client.unsubscribe(uri)

        client.received_message(json.dumps({"id": uri, "payload": [1]}))
        assert result == []

        with raises(ValueError):
            client.unsubscribe(uri)

    def test_new_registration(self):
        client = WebOSClient("ws://a")
        store = {}
        with raises(Exception, message="Timeout."):
            next(client.register(store, timeout=1))

        assert 'client-key' not in self.sent_message

        store["client_key"] = "KEY!@#"

        with raises(Exception, message="Timeout."):
            next(client.register(store, timeout=1))

        assert 'KEY!@#' in self.sent_message

    def test_discovery(self):
        def mock_discover(*args, **kwargs):
            return ["host1", "host2"]
        backup = pywebostv.connection.discover
        pywebostv.connection.discover = mock_discover

        expected = ["ws://{}:3000/".format(x) for x in ["host1", "host2"]]
        assert [x.url for x in WebOSClient.discover()] == expected

        pywebostv.connection.discover = backup

    def test_registration_timeout(self):
        client = WebOSClient("test-host")
        with raises(Exception):
            list(client.register({}, timeout=5))

    def test_registration(self):
        client = WebOSClient("test-host")
        sent_event = Event()

        def make_response(prompt, registered, wrong):
            def send_response():
                sent_event.wait()
                sent_event.clear()

                if prompt:
                    client.received_message(json.dumps({
                        "id": "1",
                        "payload": {"pairingType": "PROMPT"}
                    }))
                if registered:
                    client.received_message(json.dumps({
                        "id": "1",
                        "payload": {"client-key": "xyz"},
                        "type": "registered"
                    }))
                if wrong:
                    client.received_message(json.dumps({
                        "id": "1",
                        "type": "wrong-response"
                    }))
            return send_response

        def patched_send(*args, **kwargs):
            obj = WebOSClient.send(client, unique_id="1", *args, **kwargs)
            sent_event.set()
            return obj

        client.send = patched_send

        store = {}
        Thread(target=make_response(True, True, False)).start()
        gen = client.register(store, timeout=10)
        assert next(gen) == WebOSClient.PROMPTED
        assert next(gen) == WebOSClient.REGISTERED

        assert store == {"client_key": "xyz"}

        # Test with non-empty store.
        Thread(target=make_response(False, True, False)).start()
        list(client.register(store, timeout=10)) == [WebOSClient.REGISTERED]
        assert "xyz" in self.sent_message

        # Test wrong response.
        Thread(target=make_response(False, False, True)).start()
        with raises(Exception):
            list(client.register(store, timeout=10))
