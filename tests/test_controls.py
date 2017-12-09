from pytest import raises

from pywebostv.connection import arguments


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
