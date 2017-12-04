from threading import Event


class Application(object):
    def __init__(self, app_control, data):
        self.app_control = app_control
        self.data = data
        self.launch_info = {}

    def __getitem__(self, val):
        return self.data[val]

    def launch(self, content_id=None, params=None, block=True, callback=None,
               timeout=None):
        payload = {"id": self["id"]}
        if content_id is not None:
            payload["contentId"] = content_id
        if params is not None:
            payload["params"] = params

        response_received = Event()

        def save_launch_info(response):
            self.launch_info = response["payload"]
            if block:
                response_received.set()
            if callback:
                callback(response)

        self.app_control.request("ssap://system.launcher/launch", payload,
                                 block=False, callback=save_launch_info)

        if block:
            response_received.wait(timeout=timeout)
            return self.launch_info["returnValue"]

    def close(self, block=False, callback=None):
        sess_id = self.launch_info.get("sessionId")
        if not sess_id:
            raise Exception("App hasn't been launched.")

        payload = {"id": self["id"], "sessionId": sess_id}

        self.app_control.request("ssap://system.launcher/close", payload,
                                 block=block, callback=callback)

    def __repr__(self):
        return "<Application '{}'>".format(self["title"])
