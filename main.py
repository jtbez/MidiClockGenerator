from time import perf_counter, sleep, time
from multiprocessing import Process, Value, set_start_method, freeze_support
import mido
import mido.backends.rtmidi  # required for pyinstaller to create an exe


class MidiClockGen:
    def __init__(self):
        self.shared_bpm = Value('i', 60)
        self._run_code = Value('i', 1)  # used to stop midiClock from main process
        self.midi_process = None

    @staticmethod
    def _midi_clock_generator(out_port, bpm, run):
        midi_output = mido.open_output(out_port)
        clock_tick = mido.Message('clock')
        while run.value:
            pulse_rate = 60.0 / (bpm.value * 24)
            midi_output.send(clock_tick)
            t1 = perf_counter()
            if bpm.value <= 3000:
                sleep(pulse_rate * 0.8)
            t2 = perf_counter()
            while (t2 - t1) < pulse_rate:
                t2 = perf_counter()

    def launch_process(self, out_port):
        if self.midi_process:  # if the process exists, close prior to creating a new one
            self.end_process()
        else:
            app = App.get_running_app()
            if not app._led_started:
                app._led_started = True
                app.flash_led_on(None)
        self._run_code.value = 1
        self.midi_process = Process(target=self._midi_clock_generator,
                                    args=(out_port, self.shared_bpm, self._run_code),
                                    name='midi-background')
        self.midi_process.start()

    def end_process(self):
        self._run_code.value = 0
        self.midi_process.join()
        self.midi_process.close()
        self.midi_process = None


if __name__ == '__main__':
    freeze_support()  # for pyinstaller on Windows
    import os
    import sys

    from configstartup import window_left, window_height, window_top, window_width
    from kivy.app import App
    from kivy.clock import Clock
    from kivy.core.window import Window
    from kivy.metrics import Metrics
    from kivy.properties import ListProperty, BooleanProperty, StringProperty
    from kivy.resources import resource_add_path
    from kivy.uix.textinput import TextInput
    from kivy.uix.spinner import Spinner
    from kivy.uix.button import Button
    from kivy.uix.popup import Popup
    from kivy.utils import platform
    import threading
    from pythonosc import dispatcher as osc_dispatcher
    from pythonosc.osc_server import ThreadingOSCUDPServer

    def _get_resource_path():
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                return sys._MEIPASS
            if sys.platform == 'darwin':
                exe_dir = os.path.dirname(sys.executable)
                resources_dir = os.path.abspath(os.path.join(exe_dir, '..', 'Resources'))
                if os.path.isdir(resources_dir):
                    return resources_dir
        return os.path.dirname(os.path.abspath(__file__))

    resource_path = _get_resource_path()
    resource_add_path(resource_path)
    resource_add_path(os.path.join(resource_path, 'images'))
    print(f'[RESOURCE] resource_path={resource_path}', file=sys.stderr)
    print(f'[RESOURCE] image_exists={os.path.exists(os.path.join(resource_path, "images", "meris_on.png"))}', file=sys.stderr)

    set_start_method('spawn', force=True)  # required for mac


    class OscServer:
        def __init__(self, app):
            self.app = app
            self._server = None
            self._thread = None

        def start(self, port):
            self.stop()
            d = osc_dispatcher.Dispatcher()
            d.set_default_handler(self._handle)
            try:
                self._server = ThreadingOSCUDPServer(('', port), d)
                self._thread = threading.Thread(
                    target=self._server.serve_forever, daemon=True)
                self._thread.start()
                print(f'OSC server listening on port {port}')
                return True, f'Listening on port {port}'
            except OSError as e:
                print(f'OSC server failed to start: {e}')
                return False, f'Error: {e}'

        def stop(self):
            if self._server:
                self._server.shutdown()
                self._server = None
                self._thread = None

        def _handle(self, address, *args):
            try:
                print(f'OSC {address}' + (f' {args[0]}' if args else ''))
                parts = address.strip('/').split('/')
                if not parts:
                    return
                ns = parts[0]

                if ns == 'bpm':
                    bpm_val = None
                    if len(parts) >= 2:
                        try:
                            bpm_val = int(float(parts[1]))
                        except ValueError:
                            pass
                    elif args:
                        try:
                            bpm_val = int(float(args[0]))
                        except (ValueError, TypeError):
                            pass
                    if bpm_val is not None:
                        bpm_val = max(47, min(6000, bpm_val))
                        Clock.schedule_once(
                            lambda dt, v=bpm_val:
                                setattr(self.app.root.ids.bpm_slider, 'value', v), 0)

                elif ns == 'range':
                    range_val = None
                    if len(parts) >= 2:
                        range_val = parts[1]
                    elif args:
                        range_val = str(args[0])
                    if range_val is not None:
                        def _update_range(dt, rv=range_val):
                            spinner = self.app.root.ids.slider_range
                            if rv in spinner.values:
                                spinner.text = rv
                                spinner.set_min_max()
                        Clock.schedule_once(_update_range, 0)

                elif ns == 'tap':
                    def _do_tap(dt):
                        app = self.app
                        app.root.ids.tap_btn.process_tap(
                            app.root.ids.bpm_slider,
                            app.root.ids.slider_range)
                    Clock.schedule_once(_do_tap, 0)

                elif ns == 'output':
                    cmd = parts[1] if len(parts) >= 2 else (str(args[0]).lower() if args else None)
                    if cmd == 'enable':
                        Clock.schedule_once(lambda dt: self.app.enable_midi_output(), 0)
                    elif cmd == 'disable':
                        Clock.schedule_once(lambda dt: self.app.disable_midi_output(), 0)
                    elif cmd == 'toggle':
                        Clock.schedule_once(lambda dt: self.app.toggle_midi_output(), 0)

            except Exception as e:
                print(f'OSC handler error: {e}')


    class IntegerInput(TextInput):
        def insert_text(self, substring, from_undo=False):
            s = substring if substring.isdigit() else ''
            return super().insert_text(s, from_undo=from_undo)

        def on_text_validate(self):
            if int(self.text) < 47:
                self.text = '47'
            if int(self.text) > 6000:
                self.text = '6000'
            app = App.get_running_app()
            app.root.ids.bpm_slider.value = int(self.text)
            return super().on_text_validate()


    class RangeSpinner(Spinner):
        range = {'47-500': (47, 500), '400-1000': (400, 1000), '1200': (47, 6000),
                 '1500': (47, 6000), '2000': (47, 6000), '3000': (47, 6000), '6000': (47, 6000)}

        def set_min_max(self):
            p = App.get_running_app().root.ids.bpm_slider
            p.min, p.max = self.range[self.text]
            if self.text in ['1200', '1500', '2000', '3000', '6000']:
                p.value = int(self.text)


    class TapButton(Button):
        def __init__(self, **kwargs):
            self.start_time = 0
            self.tap_num = 0
            self.beats = []
            self.timer = None
            self.time_limit = 1.5
            super().__init__(**kwargs)

        def process_tap(self, bpm, range_select):
            range_select.text = '47-500'
            if self.tap_num == 0:
                self.start_time = time()
                self.tap_num += 1
                self.timer = Clock.schedule_once(self.tap_time_out, self.time_limit)

            elif self.tap_num == 1:
                self.timer.cancel()
                t1 = time()
                self.beats.append(t1 - self.start_time)
                self.start_time = t1
                self.tap_num += 1
                bpm.value = int(60/self.beats[0])
                self.timer = Clock.schedule_once(self.tap_time_out, self.time_limit)

            elif self.tap_num == 2:
                self.timer.cancel()
                t1 = time()
                new_beat = t1 - self.start_time
                self.start_time = t1
                avg = sum(self.beats)/len(self.beats)
                if 1.2 < avg/new_beat > 0.8:
                    bpm.value = int(60 / new_beat)
                    self.beats.clear()
                    self.beats.append(new_beat)
                else:
                    self.beats.append(new_beat)
                    avg = sum(self.beats) / len(self.beats)
                    bpm.value = int(60/avg)
                self.timer = Clock.schedule_once(self.tap_time_out, self.time_limit)

        def tap_time_out(self, _):
            self.start_time = 0
            self.tap_num = 0
            self.beats.clear()


    class OscSettingsPopup(Popup):
        pass


    class MidiClockApp(App):
        midi_ports = ListProperty([])
        mcg = MidiClockGen()
        panel_led = BooleanProperty(False)
        osc_status = StringProperty('Stopped')
        midi_output_enabled = BooleanProperty(True)
        selected_midi_port = StringProperty('')
        images_dir = StringProperty('')

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.osc_port = 8000
            self._osc_server = OscServer(self)
            self._led_started = False

        def flash_led_off(self, _):
            if not self._led_started:
                self.panel_led = False
                return
            self.panel_led = self.root.ids.bpm_slider.value >= 667
            rate = (60 / int(self.root.ids.bpm_slider.value)) * .75
            Clock.schedule_once(self.flash_led_on, rate)

        def flash_led_on(self, _):
            if not self._led_started:
                self.panel_led = False
                return
            self.panel_led = True
            rate = (60 / int(self.root.ids.bpm_slider.value)) * .25
            Clock.schedule_once(self.flash_led_off, rate)

        def build_config(self, config):
            config.setdefaults('Window', {'width': window_width,
                                          'height': window_height})
            config.setdefaults('Window', {'top': window_top,
                                          'left': window_left})
            config.setdefaults('OSC', {'port': 8000})
            config.setdefaults('Midi', {
                'bpm': 60,
                'range': '47-500',
                'selected_port': '',
                'output_enabled': '1'
            })

        def open_settings(self, *largs):
            pass

        def get_application_config(self):
            if platform == 'win':
                s = '%(appdir)s/%(appname)s.ini'
            else:  # mac will not write into app folder
                s = '~/.%(appname)s.ini'
            return super().get_application_config(defaultpath=s)

        def build(self):
            self.title = 'MidiClock'
            self.images_dir = os.path.join(resource_path, 'images')
            self.icon = os.path.join(self.images_dir, 'quarter note.png')
            Window.minimum_width = window_width
            Window.minimum_height = window_height
            self.use_kivy_settings = False
            Window.bind(on_request_close=self.window_request_close)

        def window_request_close(self, win):
            # Window.size is automatically adjusted for density, must divide by density when saving size
            config = self.config
            config.set('Window', 'width', int(Window.size[0] / Metrics.density))
            config.set('Window', 'height', int(Window.size[1] / Metrics.density))
            config.set('Window', 'top', Window.top)
            config.set('Window', 'left', Window.left)
            if self.root:
                config.set('Midi', 'bpm', int(self.root.ids.bpm_slider.value))
                config.set('Midi', 'range', self.root.ids.slider_range.text)
                config.set('Midi', 'selected_port', self.selected_midi_port)
                config.set('Midi', 'output_enabled', int(self.midi_output_enabled))
            return False

        def on_port_selected(self, port):
            if port in ('** Disable Output **', '** Enable Output **'):
                self.toggle_midi_output()
                Clock.schedule_once(
                    lambda dt: setattr(
                        self.root.ids.port_1, 'text',
                        self.selected_midi_port or 'Select Midi Out'), 0)
                return
            if port == 'Select Midi Out' or port == self.selected_midi_port:
                return
            self.selected_midi_port = port
            if self.midi_output_enabled:
                self.mcg.launch_process(port)

        def enable_midi_output(self):
            if not self.midi_output_enabled:
                self.midi_output_enabled = True
                if self.selected_midi_port:
                    self._led_started = True
                    self.flash_led_on(None)
                    self.mcg.launch_process(self.selected_midi_port)

        def disable_midi_output(self):
            if self.midi_output_enabled:
                self.midi_output_enabled = False
                self._led_started = False
                if self.mcg.midi_process:
                    self.mcg.end_process()

        def toggle_midi_output(self):
            if self.midi_output_enabled:
                self.disable_midi_output()
            else:
                self.enable_midi_output()

        def show_osc_settings(self):
            OscSettingsPopup().open()

        def save_osc_settings(self, port):
            port = max(1, min(65535, port))
            self.osc_port = port
            self.config.set('OSC', 'port', port)
            self.config.write()
            ok, msg = self._osc_server.start(port)
            self.osc_status = msg

        def on_start(self):
            self.midi_ports = mido.get_output_names()
            config = self.config
            self.selected_midi_port = config.getdefault('Midi', 'selected_port', '')
            self.midi_output_enabled = config.getdefault('Midi', 'output_enabled', '1') in ('1', 'True', 'true', 'yes')
            bpm_value = int(config.getdefault('Midi', 'bpm', 60))
            range_text = config.getdefault('Midi', 'range', '47-500')

            width = config.getdefault('Window', 'width', window_width)
            height = config.getdefault('Window', 'height', window_height)
            Window.size = (int(width), int(height))
            Window.top = int(float(config.getdefault('Window', 'top', window_top)))
            Window.left = int(float(config.getdefault('Window', 'left', window_left)))

            if self.selected_midi_port not in self.midi_ports:
                self.selected_midi_port = ''

            if self.root:
                self.root.ids.bpm_slider.value = bpm_value
                self.root.ids.slider_range.text = range_text
                self.root.ids.slider_range.set_min_max()
                port_spinner = self.root.ids.port_1
                port_spinner.text = ('** Enable Output **' if not self.midi_output_enabled else
                                     self.selected_midi_port or 'Select Midi Out')

            self.osc_port = int(config.getdefault('OSC', 'port', 8000))
            ok, msg = self._osc_server.start(self.osc_port)
            self.osc_status = msg

            if self.midi_output_enabled and self.selected_midi_port:
                self._led_started = True
                self.flash_led_on(None)
                self.mcg.launch_process(self.selected_midi_port)

        def on_stop(self):
            if self.mcg.midi_process:
                self.mcg.end_process()
            self._osc_server.stop()
            self.config.write()


    MidiClockApp().run()
