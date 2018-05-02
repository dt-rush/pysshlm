import sys
import tty
import termios
import time
import threading
import signal
import unicodedata
import ast

from blessed import Terminal

from ptyprocess import PtyProcessUnicode

from pysshlm.term_io_handler import TermIOHandler
from pysshlm.modes import (
        KEY_PASSTHROUGH,
        LINE_BUFFERED,
        QUIT_PROMPT
)
from pysshlm.config import pysshlm_config
from pysshlm.utils import get_term_dimensions
from pysshlm.mode_controller import ModeController


# wrapper class handling input buffering,
# managing the opening and closing of the PTY
class ThinWrapper():

    def __init__ (self, cmd):
        # blessings to the author of blessed for this
        self._t = Terminal()
        # used to transition between modes
        self._setup_mode_controller()
        # used to control the wrapper
        self._setup_hotkeys()
        # used to hold the line buffer in line-editing mode
        self._line_buffer = ""
        # used to display a notifier when the line-mode is toggled
        self._notifier = pysshlm_config.get ("line_mode_notifier")
        self._line_buffered_mode_notifier_on = '[%s]' % (self._notifier,)
        self._line_buffered_mode_notifier_off = '[\%s]' % (self._notifier,)
        # used to display a prompt when entering quit mode
        self._quit_prompt_message = pysshlm_config.get ("quit_prompt_message")
        # save a reference to the cmd we will spawn
        self._cmd = cmd
        # spawn the PTY (get dimensions from current tty)
        self._pty = PtyProcessUnicode.spawn (cmd,
                        dimensions=get_term_dimensions())
        # for handling reading/writing to/from pty and writing
        # to the user's terminal
        self._io = TermIOHandler (self._pty)
        # set-up handling for terminal window resize
        self._setup_SIGWINCH_handler()
        self._has_been_resized = False
        # set when the session ends
        self._session_over_flag = threading.Event()

    def _setup_mode_controller (self):
        # which mode is the thinwrapper in?
        # default to key passthrough initially
        self._mode_controller = ModeController (initial_mode=KEY_PASSTHROUGH)
        # build a map of methods keyed by modes with
        # which we'll respond to key presses
        self._keypress_processor_methods_by_mode = {
            KEY_PASSTHROUGH: self._process_keypress_key_passthrough,
            LINE_BUFFERED: self._process_keypress_line_buffered,
            QUIT_PROMPT: self._process_keypress_quit_prompt,
        }
        # register callbacks for mode transitions
        self._mode_controller._on_transition (
                KEY_PASSTHROUGH,
                LINE_BUFFERED,
                self._transition_key_passthrough_to_line_buffered)
        self._mode_controller._on_transition (
                LINE_BUFFERED,
                KEY_PASSTHROUGH,
                self._transition_line_buffered_to_key_passthrough)
        self._mode_controller._on_enter (
                QUIT_PROMPT,
                self._mode_entered_quit_prompt)
        self._mode_controller._on_leave (
                QUIT_PROMPT,
                self._mode_left_quit_prompt)

    def _setup_hotkeys (self):
        # read hotkey definitions from pysshlm.cfg
        # hotkeys are used to transition between modes
        raw_hotkeys_map = ast.literal_eval (pysshlm_config.get ("hotkeys"))
        # the cfg file defines a map of key -> mode_str, so we need
        # to convert that to key -> mode using the fact that globals()
        # returns a map of str -> value of var named by str
        self._hotkey_to_mode_map = dict (map (
            lambda tup: (tup[0], globals()[tup[1]]),
            raw_hotkeys_map.iteritems()))
        # we need to reverse the direction of the above map
        # to build the mode -> key map
        self._mode_to_hotkey_map = dict (map (lambda tup: tup[::-1],
                        self._hotkey_to_mode_map.iteritems()))
        # build a map of hotkeys active in each mode, and which modes they
        # will transition us to if received while in that mode
        # (for help in understanding how this map is used,
        # see the definition of _get_mode_for_hotkey() below
        self._hotkey_mode_transition_map = {
            KEY_PASSTHROUGH: {
                self._mode_to_hotkey_map [LINE_BUFFERED]: LINE_BUFFERED
            },
            LINE_BUFFERED: {
                self._mode_to_hotkey_map [LINE_BUFFERED]: KEY_PASSTHROUGH,
                self._mode_to_hotkey_map [QUIT_PROMPT]: QUIT_PROMPT
            },
            # no hotkeys active in quit prompt
            # we merely prompt and: quit, or, return to prior mode
            QUIT_PROMPT: {}
        }

    #
    #
    # terminal handling functions
    #
    #

    # attach a listener for window change signal to propagate
    # the change to the PTY
    def _setup_SIGWINCH_handler (self):
        # handler for the signal
        def handler (signum, stackframe):
            self._has_been_resized = True
        # listen for the signal
        signal.signal (signal.SIGWINCH, handler)

        # create a thread that every 1000 milliseconds will
        # check if the window has changed size, and propagate
        # the sigwinch with self._pty.setwinsize() if so
        def check_resize():
            while self._pty.isalive():
                time.sleep (1)
                if self._has_been_resized:
                    self._pty.setwinsize (*(get_term_dimensions()))
                    self._has_been_resized = False
        check_resize_thread = threading.Thread (target=check_resize)
        check_resize_thread.start()

    #
    #
    # line_buffered mode methods
    #
    #

    # delete the current line buffer from the screen and clear it in memory
    def _cancel_current_line_edits (self):
        self._io.backspace (len (self._line_buffer))
        self._clear_line_buffer()

    # clear the current line buffer
    # TODO: access stack properly when line history is implemented
    def _clear_line_buffer (self):
        self._line_buffer = ""

    # add a string to the line buffer
    def _add_to_line_buffer (self, s):
        self._io.screen_write (s)
        # TODO: after implementation of arrow keys in line-mode,
        # tracking of position, insert at the position rather than append
        self._line_buffer += s

    # run on entering LINE_BUFFERED from KEY_PASSTHROUGH
    def _transition_key_passthrough_to_line_buffered (self):
        self._io.display_notifier (self._line_buffered_mode_notifier_on)

    # process a kepress in LINE_BUFFERED mode
    def _process_keypress_line_buffered (self, key):
        # CTRL-C in line-mode cancels edits
        if key == '\x03':
            self._cancel_current_line_edits()
            self._io.display_notifier ("[cleared line]")
        # ENTER submits the current line buffer
        if key == '\x0d':
            self._io.backspace (len (self._line_buffer))
            self._io.pty_write (self._line_buffer + '\r')
            self._clear_line_buffer()
        # NOTE: delete / backspace both get mapped to KEY_DELETE by blessed
        # backspace a char
        elif key.code == self._t.KEY_DELETE:
            if len (self._line_buffer) != 0:
                # note that \b only moves cursor left, we have to
                # overwrite it and come back
                self._io.screen_write ('\b \b')
                # strip 1 char from linebuffer
                self._line_buffer = self._line_buffer[:-1]
        # elif IS MOVEMENT KEY?
        # TODO: implement position tracking (left, right) on write / backspace
        # TODO: make sure that CTRL-left, CTRL-right work properly
        # TODO: implement "up"/"down" via a stack, where [0] == current line
        # until the above is implemented, ignore all sequences,
        # they should not be added to the buffer
        elif key.is_sequence:
            pass
        # handle control sequence chars
        # (which are best compared with their direct char values)
        elif unicodedata.category (key) == "Cc":
            # handle ctrl + D (remember we're in line-mode)
            if key == u'\x04':
                self._io.display_notifier ("[exit line-mode to send CTRL-D]",
                                0.8)
            # ignore all control chars not handled above
            else:
                self._io.display_notifier ("[line-mode ignores control chars]",
                                0.8)
        # handle all other key presses (AKA those not detected above)
        # in line-mode by appending to buffer
        else:
            self._add_to_line_buffer (key)

    #
    #
    # quit_prompt mode methods
    #
    #

    def _mode_entered_quit_prompt (self):
        self._io.screen_write (self._quit_prompt_message)

    def _mode_left_quit_prompt (self):
        self._io.backspace (len (self._quit_prompt_message))

    def _process_keypress_quit_prompt (self, key):
        if (key == '\x0d' or  # (0d == ENTER)
                key == 'y' or
                key == 'Y'):
            self.end_session()
        elif (key == 'n' or
                key == 'N'):
            self._transition_to_mode (self._last_mode)

    #
    #
    # key_passthrough mode methods
    #
    #

    # run on entering KEY_PASSTHROUGH from LINE_BUFFERED
    def _transition_line_buffered_to_key_passthrough (self):
        self._cancel_current_line_edits()
        self._io.display_notifier (self._line_buffered_mode_notifier_off)

    def _process_keypress_key_passthrough (self, key):
        self._pty.write (key)

    #
    #
    # input processing functions
    #
    #

    # determine if a key is a hotkey
    def _key_is_hotkey (self, key):
        hotkeys = self._hotkey_mode_transition_map \
                        [self._mode_controller.mode].keys()
        return key in hotkeys

    # use the mode hotkey map to find the mode a given hotkey triggers,
    # in the mode we're currently in
    def _get_mode_for_hotkey (self, hotkey):
        current_mode = self._mode_controller.mode
        return self._hotkey_mode_transition_map [current_mode] [hotkey]

    # get the keypress processor method given our current mode
    def _get_keypress_processor_method (self):
        return self._keypress_processor_methods_by_mode \
                [self._mode_controller.mode]

    # react to a keypress - main entrypoint for every keypress,
    # regardless of mode or whether key is hotkey
    def _on_press (self, key):
        # block keypress processing while a notifier active
        self._io.can_process_keypress_flag.wait()
        # check if key pressed is a mode transition hotkey for the current mode
        if self._key_is_hotkey (key):
            # if it's active, act on it
            new_mode = self._get_mode_for_hotkey (key)
            self._mode_controller.transition_to (new_mode)
        # else process the keypress according to the current mode
        else:
            key_processor = self._get_keypress_processor_method()
            key_processor (key)

    #
    #
    # functions to process input and output to / from pty, run as threads
    #
    #

    def _flow_output (self):
        # read from the pty output and forward to stdout
        while not self._session_over_flag.is_set():
            time.sleep (0.005)
            try:
                s = self._pty.read (size=1024)
                self._io.screen_write (s)
            except EOFError:
                self._io.screen_writeln ('[pysshlm] EOF')
                self.end_session()
            except UnicodeDecodeError as e:
                self._io.screen_writeln ("[pysshlm]: %s." % (str (e),))
                self._io.screen_writeln ("[pysshlm]: Possibly stdout of \
                        session tried to send binary data, such as when \
                        running \"cat\" on a binary file?")
                self.end_session()

    def _flow_input (self):
        while not self._session_over_flag.is_set():
            c = self._t.inkey(timeout=0.3)
            if c != '':  # timeout returns ''
                self._on_press (c)

    #
    #
    # publicly-exposed functions
    #
    #

    def end_session (self):
        self._session_over_flag.set()
        self._pty.terminate()

    def exit (self):
        termios.tcsetattr (sys.stdin.fileno(),
                termios.TCSAFLUSH,
                self._old_tty_settings)

    # begin actually acting as a thin layer -
    # start flowing input and output to/from the pty
    def enter (self):
        # kick into raw mode
        self._old_tty_settings = termios.tcgetattr (sys.stdin.fileno())
        tty.setraw (sys.stdin.fileno())
        # start the input and ouput threads
        self._flow_output_thread = threading.Thread (target=self._flow_output)
        self._flow_output_thread.start()
        self._flow_input_thread = threading.Thread (target=self._flow_input)
        self._flow_input_thread.start()
        # wait for session over
        self._session_over_flag.wait()
        self.exit()
