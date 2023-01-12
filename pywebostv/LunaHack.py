# Function to run luna commands that are normally blocked. Got heavy inspiration from https://github.com/bendavid/aiopylgtv

from pywebostv.controls import WebOSControlBase, process_payload

original_exec_command = WebOSControlBase.exec_command

def LunaHack(self, cmd, cmd_info):
    if "luna://" in cmd_info["uri"]:
        def lunaCommand(*args,**kwargs):
            cmd_info["payload"] = process_payload(cmd_info.get("payload"), *args, **kwargs)
            payload = {
                "uri":"ssap://system.notifications/createAlert",
                "payload":{
                        "message": " ",
                        "buttons": [{"label": "", "onClick": cmd_info["uri"], "params": cmd_info["payload"]}],
                        "onclose": {"uri": cmd_info["uri"], "params": cmd_info["payload"]},
                        "onfail":  {"uri": cmd_info["uri"], "params": cmd_info["payload"]},
                    },
                }
            alertId = original_exec_command(self,"blank",payload)()["alertId"]
            payload = {
                "uri":"ssap://system.notifications/closeAlert",
                "payload":{
                    "alertId": alertId
                    }
                }
            original_exec_command(self,"blank",payload)()
            return None
        return lunaCommand
    else:
        return original_exec_command(self, cmd, cmd_info)

WebOSControlBase.exec_command = LunaHack
'