import math
import time
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from ks_includes.screen_panel import ScreenPanel


class Panel(ScreenPanel):

    MACRO = "gcode_macro KLICKYDOCK_CONFIG"

    def __init__(self, screen, title, **kwargs):
        title = "KlickyDock"
        super().__init__(screen, title, **kwargs)

        # ----------------------------------------------------
        # Local values
        # ----------------------------------------------------
        self.deploy_position = 0.0
        self.retract_position = 105.0
        self.current_position = 105.0
        self.servo_enabled = None
        self.enable_timeout = 20.0
        self._entry_display_values = {"timeout_entry": "20"}
        self._edited_entries = set()
        self._pending_entries = set()
        self._refreshing_entry = False
        self._status_timer = None
        self._status_pending = 0.0
        self._panel_active = False

        # ----------------------------------------------------
        # Main layout
        # ----------------------------------------------------
        grid = Gtk.Grid(
            column_spacing=6,
            row_spacing=6,
            column_homogeneous=True
        )

        grid.set_hexpand(True)
        grid.set_vexpand(True)


        # ====================================================
        # CURRENT POSITION
        # ====================================================

        self.position_value = Gtk.Label(label="Current Position: Unknown")
        self.position_value.set_halign(Gtk.Align.CENTER)

        self.servo_value = Gtk.Label(label="Servo: UNKNOWN")
        self.servo_value.set_halign(Gtk.Align.CENTER)

        grid.attach(self.position_value, 0, 0, 6, 1)
        grid.attach(self.servo_value, 0, 1, 6, 1)
        self.input_message = Gtk.Label(label="")
        self.input_message.set_line_wrap(True)
        self.input_message.set_halign(Gtk.Align.CENTER)
        grid.attach(self.input_message, 0, 2, 6, 1)

        # ====================================================
        # DEPLOY POSITION ENTRY
        # ====================================================

        deploy_label = Gtk.Label(label="Deploy Position")
        deploy_label.set_halign(Gtk.Align.START)

        self.deploy_entry = Gtk.Entry()
        self.deploy_entry.set_width_chars(5)
        self.deploy_entry.set_max_width_chars(7)
        self.deploy_entry.set_hexpand(True)
        self.deploy_entry.set_placeholder_text("0 - 180")
        self.deploy_entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.deploy_entry.set_alignment(0.5)

        self.deploy_entry.connect(
            "button-release-event",
            self.open_keyboard
        )

        grid.attach(deploy_label, 0, 4, 2, 1)
        grid.attach(self.deploy_entry, 2, 4, 2, 1)

        # ====================================================
        # RETRACT POSITION ENTRY
        # ====================================================

        retract_label = Gtk.Label(label="Retract Position")
        retract_label.set_halign(Gtk.Align.START)

        self.retract_entry = Gtk.Entry()
        self.retract_entry.set_width_chars(5)
        self.retract_entry.set_max_width_chars(7)
        self.retract_entry.set_hexpand(True)
        self.retract_entry.set_placeholder_text("0 - 180")
        self.retract_entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.retract_entry.set_alignment(0.5)

        self.retract_entry.connect(
            "button-release-event",
            self.open_keyboard
        )

        grid.attach(retract_label, 0, 5, 2, 1)
        grid.attach(self.retract_entry, 2, 5, 2, 1)

        # ====================================================
        # DEPLOY / RETRACT BUTTONS
        # ====================================================

        deploy_btn = self._gtk.Button(
            label="Deploy",
            style="color1"
        )

        deploy_btn.connect(
            "clicked",
            self.deploy
        )

        retract_btn = self._gtk.Button(
            label="Retract",
            style="color2"
        )

        retract_btn.connect(
            "clicked",
            self.retract
        )

        grid.attach(deploy_btn, 0, 8, 3, 1)
        grid.attach(retract_btn, 3, 8, 3, 1)

        # ====================================================
        # SAVE BUTTON
        # ====================================================

        save_btn = self._gtk.Button(
            label="Save",
            style="color4"
        )

        save_btn.connect(
            "clicked",
            self.save
        )

        grid.attach(save_btn, 4, 4, 2, 3)

        # ====================================================
        # ENABLE / DISABLE SERVO
        # ====================================================

        enable_btn = self._gtk.Button(
            label="Enable Servo",
            style="color1"
        )

        enable_btn.connect(
            "clicked",
            self.enable_servo
        )

        disable_btn = self._gtk.Button(
            label="Disable Servo",
            style="color2"
        )

        disable_btn.connect(
            "clicked",
            self.disable_servo
        )

        grid.attach(enable_btn, 0, 7, 3, 1)
        grid.attach(disable_btn, 3, 7, 3, 1)

        # Local styling: fill the button body while retaining its color strip.
        self._button_css = Gtk.CssProvider()
        self._button_css.load_from_data(b"""
            button {
                background-image: none;
                background-color: #30485c;
                border-top: 1px solid #7892a6;
                border-left: 1px solid #7892a6;
                border-right: 1px solid #7892a6;
                border-radius: 8px;
            }
            button:hover { background-color: #3b5870; }
            button:active { background-color: #203444; }
        """)
        for button in (deploy_btn, retract_btn, enable_btn, disable_btn, save_btn):
            button.get_style_context().add_provider(
                self._button_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
            )

        timeout_label = Gtk.Label(label="Timeout (s)\n0 = off")
        timeout_label.set_halign(Gtk.Align.START)
        self.timeout_entry = Gtk.Entry()
        self.timeout_entry.set_width_chars(5)
        self.timeout_entry.set_max_width_chars(7)
        self.timeout_entry.set_hexpand(True)
        self.timeout_entry.set_input_purpose(Gtk.InputPurpose.NUMBER)
        self.timeout_entry.set_alignment(0.5)
        self.timeout_entry.set_text("20")
        self.timeout_entry.connect("button-release-event", self.open_keyboard)
        grid.attach(timeout_label, 0, 6, 2, 1)
        grid.attach(self.timeout_entry, 2, 6, 2, 1)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.add(grid)
        self.content.add(scroller)
        for name in ("deploy_entry", "retract_entry", "timeout_entry"):
            entry = getattr(self, name)
            entry.connect("changed", self.entry_changed, name)
            entry.connect("activate", self.apply_entry, name)
            entry.connect("focus-out-event", self.entry_focus_out, name)

    # ========================================================
    # PANEL ACTIVATION
    # ========================================================

    def activate(self):
        self.refresh_status()
        self._panel_active = True
        self.poll_status()
        if self._status_timer is None:
            self._status_timer = GLib.timeout_add_seconds(1, self.poll_status)

    def deactivate(self):
        self._panel_active = False
        if self._status_timer is not None:
            GLib.source_remove(self._status_timer)
            self._status_timer = None

    def poll_status(self):
        if not self._panel_active:
            return False
        now = time.monotonic()
        if self._status_pending and now - self._status_pending < 5:
            return True
        if self._status_pending:
            self.servo_enabled = None
            self.update_display()
        self._status_pending = now
        sent = self._screen._ws.send_method(
            "printer.objects.query",
            {"objects": {self.MACRO: None, "servo klickydock": ["value"]}},
            self.status_response,
        )
        if not sent:
            self._status_pending = 0.0
            self.servo_enabled = None
            self.update_display()
        return True

    def status_response(self, response, *args):
        self._status_pending = 0.0
        if not self._panel_active:
            return
        status = response.get("result", {}).get("status", {})
        self.process_update("notify_status_update", status)
        # Read Klipper's output state, rather than assuming a command succeeded.
        value = status.get("servo klickydock", {}).get("value")
        try:
            value = float(value)
            self.servo_enabled = value > 0 if math.isfinite(value) else None
        except (TypeError, ValueError):
            self.servo_enabled = None
        self.update_display()

    # ========================================================
    # TOUCHSCREEN KEYBOARD
    # ========================================================

    def open_keyboard(self, entry, event):
        # Only an explicit tap opens the editor, not restored widget focus.
        self._screen.show_keyboard(entry)
        return False

    # ========================================================
    # READ CURRENT KLIPPER VALUES
    # ========================================================

    def read_servo_status(self, data):
        if isinstance(data, dict) and "enable_timeout" in data:
            try:
                timeout = float(data["enable_timeout"])
                if math.isfinite(timeout) and timeout >= 0:
                    self.enable_timeout = timeout
            except (TypeError, ValueError):
                pass
        # Report macro state; never assume a button press succeeded.
        if isinstance(data, dict) and "servo_enabled" in data:
            value = data["servo_enabled"]
            self.servo_enabled = (
                bool(value) if value in (0, 1) else None
            )

    def refresh_status(self):

        data = self._printer.get_stat(self.MACRO)
        self.read_servo_status(data)

        if not isinstance(data, dict):
            return

        try:
            if "deploy_position" in data:
                self.deploy_position = float(data["deploy_position"])

            if "retract_position" in data:
                self.retract_position = float(data["retract_position"])

            if "current_position" in data:
                self.current_position = float(data["current_position"])

        except (TypeError, ValueError):
            return

        self.update_display()

    # ========================================================
    # UPDATE SCREEN
    # ========================================================

    def entry_focus_out(self, entry, event, name):
        self.apply_entry(entry, name)
        return False

    def apply_entry(self, entry, name):
        if name not in self._pending_entries:
            return True
        self.input_message.set_text("")
        try:
            value = float(entry.get_text().strip())
        except ValueError:
            value = float("nan")
        valid = math.isfinite(value) and value >= 0
        if name != "timeout_entry":
            valid = valid and value <= 180
        if not valid:
            self.show_input_message(
                "Enter a timeout of 0 or greater." if name == "timeout_entry"
                else "Enter a position between 0 and 180 degrees."
            )
            return False
        commands = {
            "deploy_entry": "KLICKYMOVED POSITION=",
            "retract_entry": "KLICKYMOVER POSITION=",
            "timeout_entry": "KLICKYDOCK_SET_TIMEOUT SECONDS=",
        }
        sent = self._screen._ws.api.gcode_script(commands[name] + f"{value:g}")
        if sent is False:
            self.show_input_message("Unable to send value. Check the printer connection.")
            return False
        self._pending_entries.discard(name)
        return True

    def entry_changed(self, entry, name):
        if not self._refreshing_entry:
            self._edited_entries.add(name)
            self._pending_entries.add(name)

    def refresh_entry(self, name, value):
        entry = getattr(self, name)
        desired = f"{value:g}"
        # These are calibration inputs. Once edited, retain the user's target
        # even if an old status reply arrives after a Set button is pressed.
        if entry.has_focus() or name in self._edited_entries:
            return
        self._refreshing_entry = True
        try:
            entry.set_text(desired)
        finally:
            self._refreshing_entry = False

    def update_display(self):
    
        # ------------------------------------------------
        # Don't overwrite an entry while the user is
        # typing a new position.
        # ------------------------------------------------
    
        self.refresh_entry("deploy_entry", self.deploy_position)
        self.refresh_entry("retract_entry", self.retract_position)

        # ------------------------------------------------
        # Determine current dock position
        # ------------------------------------------------
    
        if abs(
            self.current_position - self.deploy_position
        ) < 0.01:
    
            position = "DEPLOYED"
    
        elif abs(
            self.current_position - self.retract_position
        ) < 0.01:
    
            position = "RETRACTED"
    
        else:
    
            position = f"{self.current_position:g}°"
    
        self.position_value.set_text(f"Current Position: {position}")
        state = "UNKNOWN" if self.servo_enabled is None else (
            "ENABLED" if self.servo_enabled else "DISABLED"
        )
        self.servo_value.set_text(f"Servo: {state}")
        self.refresh_entry("timeout_entry", self.enable_timeout)

    # ========================================================
    # VALIDATE ENTRY
    # ========================================================

    def show_input_message(self, message):
        self.input_message.set_text(message)

    def get_position(self, entry, name):
        self.input_message.set_text("")

        value = entry.get_text().strip()

        if not value:
            self.show_input_message(
                f"Enter a {name} position."
            )
            return None

        try:
            position = float(value)

        except ValueError:
            self.show_input_message(
                f"{name} position must be a number."
            )
            return None

        if not math.isfinite(position) or position < 0 or position > 180:
            self.show_input_message(
                f"{name} position must be between 0 and 180."
            )
            return None

        return position

    # ========================================================
    # SET DEPLOY POSITION
    #
    # Sends:
    # KLICKYMOVED POSITION=xx
    # ========================================================

    def set_deploy(self, widget):

        position = self.get_position(
            self.deploy_entry,
            "Deploy"
        )

        if position is None:
            return

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            f"KLICKYMOVED POSITION={position:g}"
        )

        # The status query confirms the new position before updating the display.

    # ========================================================
    # SET RETRACT POSITION
    #
    # Sends:
    # KLICKYMOVER POSITION=xx
    # ========================================================

    def set_retract(self, widget):

        position = self.get_position(
            self.retract_entry,
            "Retract"
        )

        if position is None:
            return

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            f"KLICKYMOVER POSITION={position:g}"
        )

        # The status query confirms the new position before updating the display.

    # ========================================================
    # DEPLOY
    # ========================================================

    def deploy(self, widget):

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            "KLICKYDOCK_DEPLOY"
        )

        self.current_position = self.deploy_position

        self.update_display()

    # ========================================================
    # RETRACT
    # ========================================================

    def retract(self, widget):

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            "KLICKYDOCK_RETRACT"
        )

        self.current_position = self.retract_position

        self.update_display()

    # ========================================================
    # SAVE CURRENT DEPLOY + RETRACT
    # ========================================================

    def save(self, widget):
        # Apply pending edits before the save command, on the same connection.
        for name in ("deploy_entry", "retract_entry", "timeout_entry"):
            if not self.apply_entry(getattr(self, name), name):
                return
        widget.grab_focus()
        self._screen.remove_keyboard()
        self._screen._ws.api.gcode_script("KLICKYDOCK_SAVE")
        # The macro reports completion; avoid a second focus-changing popup.

    # ========================================================
    # ENABLE SERVO
    # ========================================================

    def set_timeout(self, widget):
        self.input_message.set_text("")
        try:
            timeout = float(self.timeout_entry.get_text().strip())
        except ValueError:
            timeout = -1
        if not math.isfinite(timeout) or timeout < 0:
            self.show_input_message("Enter a timeout of 0 seconds or greater.")
            return
        self._screen.remove_keyboard()
        self._screen._ws.api.gcode_script(
            f"KLICKYDOCK_SET_TIMEOUT SECONDS={timeout:g}"
        )

    def enable_servo(self, widget):

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            "KLICKYDOCK_ENABLE"
        )

    # ========================================================
    # DISABLE SERVO
    # ========================================================

    def disable_servo(self, widget):

        self._screen.remove_keyboard()

        self._screen._ws.api.gcode_script(
            "KLICKYDOCK_DISABLE"
        )

    # ========================================================
    # KLIPPER STATUS UPDATE
    # ========================================================

    def process_update(self, action, data):

        if action != "notify_status_update":
            return

        if self.MACRO not in data:
            return

        macro_data = data[self.MACRO]
        self.read_servo_status(macro_data)

        try:
            if "deploy_position" in macro_data:
                self.deploy_position = float(
                    macro_data["deploy_position"]
                )

            if "retract_position" in macro_data:
                self.retract_position = float(
                    macro_data["retract_position"]
                )

            if "current_position" in macro_data:
                self.current_position = float(
                    macro_data["current_position"]
                )

        except (TypeError, ValueError):
            return

        self.update_display()
