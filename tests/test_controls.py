from threading import Event, Semaphore

from pytest import raises, mark

from pywebostv.controls import WebOSControlBase
from pywebostv.controls import arguments, process_payload
from pywebostv.controls import MediaControl, SystemControl, ApplicationControl
from pywebostv.controls import InputControl
from pywebostv.model import Application

from utils import FakeClient, FakeMouseClient


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

    def test_args_default_value(self):
        args = arguments(2, default={1, 2})
        assert args() == {1, 2}
        assert args("a", "b", "c") == "c"

    def test_kwargs_default_value(self):
        args = arguments("key", default="value")
        assert args() == "value"
        assert args("a", "b", key="blah") == "blah"

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


class TestWebOSControlBase(object):
    def test_missing_attribute(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {}
        with raises(AttributeError):
            control_base.attribute()

    def test_exec_command_blocking(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {"uri": "/test"}
        }

        client.setup_response("/test", {"resp": True})
        assert control_base.test() == {"resp": True}

    def test_exec_command_callback(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {"uri": "/test"}
        }

        response = []
        event = Event()

        def callback(status, resp):
            response.append((status, resp))
            event.set()

        client.setup_response("/test", {"resp": True})
        control_base.test(callback=callback)
        event.wait()

        assert response == [(True, {"resp": True})]

    def test_exec_command_failed_callback(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
                "validation": lambda *args: (False, "err"),
                "validation_error": "Error"
            }
        }

        response = []
        event = Event()

        def callback(status, resp):
            response.append((status, resp))
            event.set()

        client.setup_response("/test", {"resp": True})
        control_base.test(callback=callback)
        event.wait()

        assert response == [(False, "err")]

    def test_exec_command_failed_blocking(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
                "validation": lambda *args: (False, "err"),
                "validation_error": "Error"
            },
        }

        client.setup_response("/test", {"resp": True})
        with raises(IOError):
            control_base.test(block=True)

    def test_exec_timeout(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
            },
        }

        client.setup_response("/another-uri", {"resp": True})
        with raises(Exception):
            control_base.test(timeout=1)

    def test_subscribe(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
                "subscription": True,
                "validation": lambda p: (p == {"a": 1}, "Error.")
            },
        }

        resp = []
        e1, e2 = Event(), Event()
        events = [e1, e2]

        def callback(status, payload):
            resp.append((status, payload))
            events.pop(0).set()

        client.setup_subscribe_response("/test", [{"a": 1}, {"a": 2}])
        control_base.subscribe_test(callback)
        assert e1.wait(timeout=2)
        assert e2.wait(timeout=2)

        assert resp == [(True, {"a": 1}), (False, "Error.")]

        with raises(ValueError):
            control_base.subscribe_test(None)

    def test_subscription_not_found(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
                "subscription": True
            },
        }

        with raises(AttributeError):
            control_base.subscribe_something(None)

        with raises(AttributeError):
            control_base.unsubscribe_something()

    def test_subscription_not_allowed(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
            },
        }
        with raises(AttributeError):
            control_base.subscribe_test(None)

        with raises(AttributeError):
            control_base.unsubscribe_test()

    def test_unsubscribe(self):
        client = FakeClient()
        control_base = WebOSControlBase(client)
        control_base.COMMANDS = {
            "test": {
                "uri": "/test",
                "subscription": True
            },
        }

        resp = []
        e1, e2 = Event(), Event()
        events = [e1, e2]

        def callback(status, payload):
            resp.append((status, payload))
            control_base.unsubscribe_test()
            events.pop(0).set()

        client.setup_subscribe_response("/test", [{"a": 1}, {"a": 2}])
        control_base.subscribe_test(callback)
        assert e1.wait(timeout=5)
        assert not e2.wait(timeout=5)

        assert resp == [(True, {"a": 1})]

        with raises(ValueError):
            control_base.unsubscribe_test()


class TestMediaControl(object):
    def test_mute(self):
        client = FakeClient()
        media = MediaControl(client)
        media.mute(True, block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://audio/setMute",
            "payload": {"mute": True}
        })

    def test_unmute(self):
        client = FakeClient()
        media = MediaControl(client)
        media.mute(False, block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://audio/setMute",
            "payload": {"mute": False}
        })

    def test_set_volume(self):
        client = FakeClient()
        media = MediaControl(client)
        media.set_volume(30, block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://audio/setVolume",
            "payload": {"volume": 30}
        })

    def test_get_volume(self):
        client = FakeClient()
        res = dict(returnValue=True, volume=1, mute=True, scenario="")
        client.setup_response("ssap://audio/getVolume", res)
        media = MediaControl(client)
        assert media.get_volume(block=True)["volume"] == 1

    @mark.parametrize("command,uri",
                      [("volume_up", "ssap://audio/volumeUp"),
                       ("volume_down", "ssap://audio/volumeDown"),
                       ("play", "ssap://media.controls/play"),
                       ("pause", "ssap://media.controls/pause"),
                       ("stop", "ssap://media.controls/stop"),
                       ("rewind", "ssap://media.controls/rewind"),
                       ("fast_forward", "ssap://media.controls/fastForward")])
    def test_commands(self, command, uri):
        client = FakeClient()
        media = MediaControl(client)
        getattr(media, command)(block=False)

        client.assert_sent_message_without_id({"type": "request", "uri": uri})


class TestSystemControl(object):
    @mark.parametrize(
        "command,uri",
        [("info", "ssap://com.webos.service.update/getCurrentSWInformation"),
         ("power_off", "ssap://system/turnOff")])
    def test_commands(self, command, uri):
        client = FakeClient()
        system = SystemControl(client)
        getattr(system, command)(block=False)

        client.assert_sent_message_without_id({"type": "request", "uri": uri})

    def test_notify(self):
        client = FakeClient()
        system = SystemControl(client)
        system.notify("test", block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://system.notifications/createToast",
            "payload": {"message": "test"}
        })


class TestApplicationControl(object):
    def test_list_apps(self):
        client = FakeClient()
        app = ApplicationControl(client)

        appInfo = {"id": "1", "key": "value"}
        fake_response = {
            "returnValue": True,
            "apps": [appInfo]
        }
        client.setup_response("ssap://com.webos.applicationManager/listApps",
                              fake_response)
        assert app.list_apps()[0].data == appInfo

    def test_bad_list_apps(self):
        client = FakeClient()
        app = ApplicationControl(client)

        client.setup_response("ssap://com.webos.applicationManager/listApps",
                              {"returnValue": False})
        with raises(IOError):
            app.list_apps()

    def test_launch(self):
        client = FakeClient()
        app = ApplicationControl(client)

        client.setup_response("ssap://system.launcher/launch",
                              {"returnValue": True})
        application = Application({"id": "123"})
        app.launch(application, content_id="1", params={"a": "b"})

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://system.launcher/launch",
            "payload": {
                "id": "123",
                "contentId": "1",
                "params": {"a": "b"}
            }
        })

    def test_bad_launch(self):
        client = FakeClient()
        app = ApplicationControl(client)

        client.setup_response("ssap://system.launcher/launch",
                              {"returnValue": False})
        with raises(IOError):
            app.launch(Application({"id": "123"}))

    def test_get_current(self):
        client = FakeClient()
        app = ApplicationControl(client)

        client.setup_response(
            "ssap://com.webos.applicationManager/getForegroundAppInfo",
            {"returnValue": True, "appId": "123"})
        assert app.get_current() == "123"

    def test_close(self):
        client = FakeClient()
        app = ApplicationControl(client)

        client.setup_response("ssap://system.launcher/close",
                              {"returnValue": True})
        app.close({"123": "435"})

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://system.launcher/close",
            "payload": {
                "123": "435",
            }
        })


class TestInputControl(object):
    def test_type(self):
        client = FakeClient()
        inp = InputControl(client)

        inp.type("hello world", block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://com.webos.service.ime/insertText",
            "payload": {
                "text": "hello world",
                "replace": 0,
            }
        })

    def test_delete(self):
        client = FakeClient()
        inp = InputControl(client)

        inp.delete(4, block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://com.webos.service.ime/deleteCharacters",
            "payload": {
                "count": 4,
            }
        })

    def test_enter(self):
        client = FakeClient()
        inp = InputControl(client)

        inp.enter(block=False)

        client.assert_sent_message_without_id({
            "type": "request",
            "uri": "ssap://com.webos.service.ime/sendEnterKey",
        })

    def test_invalid_input_command(self):
        client = FakeClient()
        inp = InputControl(client)
        with raises(AttributeError):
            inp.invalid_command()

    @mark.parametrize(
        "command,args,kwargs,data",
        [
            ("move", [5, 6], {}, "type move dx 5 dy 6 down 0"),
            ("move", [5, 6], {"drag": 1}, "type move dx 5 dy 6 down 1"),
            ("click", [], {}, "type click"),
            ("scroll", [5, 6], {}, "type scroll dx 5 dy 6"),
            ("left", [], {}, "type button name LEFT"),
            ("right", [], {}, "type button name RIGHT"),
            ("down", [], {}, "type button name DOWN"),
            ("up", [], {}, "type button name UP"),
            ("home", [], {}, "type button name HOME"),
            ("back", [], {}, "type button name BACK"),
            ("ok", [], {}, "type button name ENTER"),
            ("dash", [], {}, "type button name DASH"),
            ("info", [], {}, "type button name INFO"),
        ])
    def test_input_commands(self, command, args, kwargs, data):
        client = FakeClient()
        inp = InputControl(client, ws_class=FakeMouseClient)

        client.setup_response(
            "ssap://com.webos.service.networkinput/getPointerInputSocket",
            {"socketPath": "x"})
        inp.connect_input()
        getattr(inp, command)(*args, block=False, **kwargs)
        inp.disconnect_input()

        split = data.split()
        expected = [x + ":" + y for x, y in zip(split[::2], split[1::2])]
        inp.mouse_ws.assert_sent_message("\n".join(expected) + "\n\n")

    def test_bad_mouse_socket(self):
        client = FakeClient()
        inp = InputControl(client, ws_class=FakeMouseClient)

        client.setup_response(
            "ssap://com.webos.service.networkinput/getPointerInputSocket",
            {"socketPath": ""})
        with raises(IOError):
            inp.connect_input()
