from pywebostv.controls import *
from pywebostv.lunaHack import *

# Adds functions to read from and write to screen brightness. Uses LunaHack.py

class PictureControl(WebOSControlBase):
    COMMANDS = {
        "get_backlight": {
            "uri": "SSAP://settings/getSystemSettings",
            "payload":{
                "category": "picture",
                "keys": ["brightness"]
            },
            "validation": standard_validation,
            "return": lambda p: p['settings']['brightness'],
        },
        "set_backlight": {
            "uri": "luna://com.webos.settingsservice/setSystemSettings",
            #"args": [int],
            "payload": {
                "category": "picture",
                "settings": {"backlight":arguments(0)}
            },
            "validation": standard_validation,
            "return": lambda p: [p],
        },
    }
