# PyWebOSTV

[![Build Status](https://api.travis-ci.org/supersaiyanmode/PyWebOSTV.svg?branch=develop)](https://travis-ci.org/supersaiyanmode/PyWebOSTV)
[![Coverage Status](https://coveralls.io/repos/github/supersaiyanmode/PyWebOSTV/badge.svg?branch=master)](https://coveralls.io/github/supersaiyanmode/PyWebOSTV?branch=master)

## Why another Library?

I looked at a few libraries. The LGWebOSRemote repository by
[klattimer](https://github.com/klattimer/LGWebOSRemote) is definitely a good library, but it has a
few problems:

- Meant to be used with Python 2.x.
- Assumes all the users of the library would like to save the credentials to ~/.lgtv.json.
- Assumes only a single command will be fired and waited on at any given time (ctrl+F for `self.__waiting_callback`)
- Mouse/Keyboard not supported.

This SDK is a tiny attempt at overcoming some of the above problems.

## Current status?

~~At the moment, I haven't been able to do any kind of extensive testing. No unit test cases too!~~
Current status: Works for quite a few people! :)

Currently working on more controls~~and unit test cases~~. I will soon upload it to PyPI.

## How to Use: Connecting to the TV

### Establishing the connection.

```python
from pywebostv.discovery import *    # Because I'm lazy, don't do this.
from pywebostv.connection import *
from pywebostv.controls import *

# The 'store' gets populated during the registration process. If it is empty, a registration prompt
# will show up on the TV. You can pass any dictionary-like interface instead -- that when values are
# set, will persist to a DB, a config file or something similar.
store = {}

# Scans the current network to discover TV. Avoid [0] in real code. If you already know the IP,
# you could skip the slow scan and # instead simply say:
#    client = WebOSClient("<IP Address of TV>")
client = WebOSClient.discover()[0]
client.connect()
for status in client.register(store):
    if status == WebOSClient.PROMPTED:
        print("Please accept the connect on the TV!")
    elif status == WebOSClient.REGISTERED:
        print("Registration successful!")
```

### Using the connection to call APIs

The `client` instance represents the main channel of communication with the TV. All `*Control`
instances (`MediaControl`, `ApplicationControl` etc) share the same underlying connection. All
available APIs are grouped into separate classes (for cleanliness) like `MediaControl`,
`SystemControl` etc.

Most `*Control` classes behave in a very similar way and are super extensible. This is because most
of the heavy lifting is done in the base class -- incorporating a new API that isn't currently
supported by this library should be very easy. Read the extension section for more on this.

Things to note:

- Most APIs support `block=` argument. If `True` the call blocks for the response to arrive. If
   `False`, it is a good idea to provide a `callback=` argument. If you don't care about the
   response at all, simply call the API with `block=False`.
- Some APIs support subscribing for changes. Provide a callback and you will be notified when the
   event happens. It is an error to subscribe more than once on the same underlying connection. To
   subscribe, the function you'd call is `control.subscribe_api_name()` assuming the regular API is
   called `api_name`. To unsubscribe, just call: `control.unsubscribe_api_name()`.

The general pattern is:

```python
control = SomeControl(client)

# Blocking call
api_response = control.some_api()

# Blocking call, with parameters (the table below lists API & arguments)
api_response = control.some_other_api(arg1, arg2)

# Blocking call can throw as error:
try:
    control.good_api(bad_argument1)
except ...:
    print("Something went wrong.")

# non-blocking call with callback
def my_function(status_of_call, payload):
    if status_of_call:
        # Successful response from TV.
        # payload is a dict or an object (see API details)
        print(payload)  # Successful response from TV
    else:
        # payload is the error string.
        print("Error message: ", payload)
control.async_api(arg1, arg2, callback=my_function)

# Subscription (if the API supports it, that is).
control.subscribe_api(my_function).

# Unsubscribe
control.unsubscribe_api()  # After this point, you can resubscribe.

```

### API Details

Please note that all the examples below use the blocking calls. Their return values and structure
are documented in the comments. They throw python exceptions when unsuccessful. To make non-blocking
calls, refer to the section above.

### Media Controls

```python
media = MediaControl(client)
media.volume_up()          # Increase the volume by 1 unit. Doesn't return anything
media.volume_down()        # Decrease the volume by 1 unit. Doesn't return anything
media.get_volume()         # Get volume status. Returns something like:
                           # {'scenario': 'mastervolume_tv_speaker', 'volume': 9, 'muted': False}
media.set_volume(<int>)    # The argument is an integer from 1 to 100. Doesn't return anything.
media.mute(status)         # status=True mutes the TV. status=Fale unmutes it.
media.play()
media.pause()
media.stop()
media.rewind()
media.fast_forward()
```

#### Subscriptions

`get_volume` supports subscription. To subscribe to volume changes, say something like:

```python
def on_volume_change(status, payload):
    if status:
        print(payload)
    else:
        print("Something went wrong.")

media.subscribe_get_volume(on_volume_change)  # on_volume_change(..) will now be called when the
                                              # volume/mute status etc changes.
```

### System Controls

```python
system = SystemControl(client)
system.notify("This is a notification message!")  # Show a notification message on the TV.
system.power_off()                                # Turns off the TV. There is no way to turn it
                                                  # back on programmically unless you use
                                                  # something like Wake-on-LAN or something liker
                                                  # that.
system.info()                                     # Returns a dict with keys such as product_name,
                                                  # model_name, # major_ver, minor_ver etc.
```

### Application Controls

```python
app = ApplicationControl(client)
apps = app.list_apps()                            # Returns a list of `Application` instances.

# Let's launch YouTube!
yt = [x for x in apps if "youtube" in x["title"].lower()][0]
                                                  # Search for YouTube & launch it (Of course, don't
                                                  # be this lazy. Check for errors). Also, Try
                                                  # searching similarly for "amazon", "netflix" etc.
launch_info = app.launch(yt)                      # Launches YouTube and shows the main page.
launch_info = app.launch(yt, content_id="dQw4w9WgXcQ")
                                                  # Or you could even launch a video directly!
app.close(launch_info)                            # Close what we just launched.

# Let's get the icon of the foreground app.
app_id = app.get_current()                        # Returns the application ID (string) of the
                                                  # foreground app.
foreground_app = [x for x in apps if app_id == x["id"]][0]
                                                  # Application app["id"] == app.data["id"].
icon_url = foreground_app["icon"]                 # This returns an HTTP URL hosted by the TV.
```

#### Subscription

`.get_current()` supports subscription. To subscribe, call `app.subscribe_get_current(callback)` in
the same way as `.subscribe_get_volume(..)` above.

### Mouse and Button Controls

```python
inp = InputControl(client)

inp.type("This sends keyboard input!")            # This sends keystrokes, but needs the keyboard to
                                                  # be displayed on the screen.
inp.enter()                                       # Return key.
inp.delete(10)                                    # Backspace 10 chars
```

The above APIs behave much like the other APIs above. The ones below are a little different. WebOS
requires that we open a different connection and uses a different message structure. You must call
`inp.connect_input()` to create this connection and `inp.disconnect_input()` to close it. All the
APIs below should be called between connect and disconnect.

```python
inp.connect_input()
inp.move(10, 10)    # Moves mouse
inp.click()         # Click where the mouse pointer is. It sometimes also acts as the center "OK"
                    # button on the remote.
inp.up()
inp.down()
inp.left()
inp.right()
inp.home()
inp.back()
inp.dash()
inp.info()
inp.num_1()         # Number keys...
inp.num_2()
inp.num_3()
inp.num_4()
inp.num_5()
inp.num_6()
inp.num_7()
inp.num_8()
inp.num_9()
inp.num_0()
inp.asterisk()      # Literally just an "*"
inp.cc()            # Closed captioning
inp.exit()          
inp.red()           # Colored buttons
inp.green()
inp.blue()
inp.mute()          # The remaining commands are also available in either MediaControl or TvControl
inp.volume_up()
inp.volume_down()
inp.channel_up()
inp.channel_down()
inp.disconnect_input()
```

### TV Controls

```python
tv_control = TvControl()
tv_control.channel_down()
tv_control.channel_up()
```

### Source Controls

```python
source_control = SourceControl(client)
sources = source_control.list_sources()    # Returns a list of InputSource instances.
source_control.set_source(sources[0])      # .set_source(..) accepts an InputSource instance.

# To get the current current source being used, please use the API that retrieves the foreground
# app.
```

More controls coming soon!

## Credits

- [klattimer](https://github.com/klattimer/LGWebOSRemote) for his library! Since WebOS team decided
   against providing any sort of documentation, his repository was extremely useful for an initial
   implementation
- As far as input controls are concerned, they are based on the Java package written by
   [Connect-SDK folks](https://github.com/ConnectSDK/Connect-SDK-Android-Core/tree/master/src/com/connectsdk/service/webos)!
- All individual contributors to this repository.
