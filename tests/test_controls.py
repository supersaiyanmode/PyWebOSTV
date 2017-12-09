from pytest import raises

from pywebostv.connection import arguments, process_payload

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
