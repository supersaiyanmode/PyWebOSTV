
class Application(object):
    def __init__(self, data):
        self.data = data

    def __getitem__(self, val):
        return self.data[val]

    def __repr__(self):
        return "<Application '{}'>".format(self["title"])


class InputSource(object):
    def __init__(self, data):
        self.data = data
        self.label = data["label"]

    def __getitem__(self, val):
        return self.data[val]

    def __repr__(self):
        return "<InputSource '{}'>".format(self["label"])


class AudioOutputSource(object):
    def __init__(self, data):
        self.data = data

    def __repr__(self):
        return "<AudioOutputSource '{}'>".format(self.data)
