import os
import sys
from configparser import ConfigParser
from kivy.config import Config
from kivy.utils import platform
"""
configstartup.py is used to set graphics

This code must be at the top of the 'main' executable file.

Config.set('graphics'...) are used to set the size of the main window.
"""
# Default window size and position, also used to set minimum window size
if platform == 'macosx':
    window_width = 175
    window_height = 550
elif platform == 'linux':
    window_width = 222
    window_height = 600
else:
    window_width = 222
    window_height = 600

window_top = 100
window_left = 100

# Resolve the ini file path — on Windows it sits next to the exe; on Linux/macOS it lives in ~
if sys.platform == 'win32':
    _ini_path = 'midiclock.ini'
else:
    _ini_path = os.path.expanduser('~/.midiclock.ini')

# Use Python lib configparser to read .ini file prior to app startup
parser = ConfigParser()
found = parser.read(_ini_path)  # created in main.py: build_config()
if found:
    Config.set('graphics', 'width', parser['Window']['width'])
    Config.set('graphics', 'height', parser['Window']['height'])
    Config.set('graphics', 'position', 'custom')
    Config.set('graphics', 'top', parser['Window']['top'])  # find top and left
    Config.set('graphics', 'left', parser['Window']['left'])
else:
    Config.set('graphics', 'width', window_width)  # default value match default values in main.py: build_config, on_start
    Config.set('graphics', 'height', window_height)
    Config.set('graphics', 'position', 'custom')
    Config.set('graphics', 'top', window_top)
    Config.set('graphics', 'left', window_left)
Config.set('kivy', 'exit_on_escape', 0)
Config.set('input', 'mouse', 'mouse,disable_multitouch')
Config.set('kivy', 'window_icon','images/quarter note.png' )

