import os
import sys
import tty
import termios
import time
import threading
import signal
import unicodedata
import ast

from ptyprocess import PtyProcessUnicode

from pysshlm.config import pysshlm_config
from pysshlm.term_io_handler import TermIOHandler


# helper function
def get_term_dimensions():
    return tuple (map (int, os.popen('stty size', 'r').read().split()))


# Constants defining modes

# keys are passed directly through to the PTY
KEY_PASSTHROUGH = 0
# type into a line buffer which is sent with \r ("enter")
LINE_BUFFERED = 1
# prompt the user whether they want to quit
QUIT_PROMPT = 2


# wrapper class handling input buffering,
# managing the opening and closing of the PTY
class ThinWrapper():

    def __init__ (self, cmd):

        # read hotkey definitions from pysshlm.cfg
        # hotkeys are used to transition between modes
        raw_hotkeys_map = ast.literal_eval (pysshlm_config.get ("hotkeys"))
        # the cfg file defines a map of key -> mode_str, so we need
        # to convert that to key -> mode using the fact that globals()
        # returns a map of str -> value of var named by str
        self._hotkey_to_mode_map = dict (map (
            lambda tup: (tup[0], globals()[tup[1]]),
            raw_hotkeys_map.iteritems()))

        # we need to reverse the direction of the above map's
        # pointing to build the mode -> key map
        def reverse_tuple (tup):
            return tup[::-1]  # "idiomatic" way to reverse a tuple in python
        self._mode_to_hotkey_map = dict (map (reverse_tuple,
                        self._hotkey_to_mode_map.iteritems()))

        # which mode is the thinwrapper in?
        self._mode = KEY_PASSTHROUGH  # default to KEY_PASSTHROUGH initially
        # used to return to prior mode in some circumstances
        self._last_mode = self._mode

        # build a map of hotkeys active in each mode, and which modes they
        # will transition us to if received while in that mode
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

        # build a map of methods keyed by ThinWrapperModes with
        # which we'll respond to key presses
        self._keypress_processor_methods_by_mode = {
            KEY_PASSTHROUGH: self._process_keypress_key_passthrough,
            LINE_BUFFERED: self._process_keypress_line_buffered,
            QUIT_PROMPT: self._process_keypress_quit_prompt,
        }

        # a dictionary of methods keyed by an old mode, a new mode,
        # defining what code should run when transitioning from the
        # old mode to the new mode
        #
        # If the old mode key is None,
        # the method is used when entering the new mode
        # eg. self._mode_transition_react_methods (None, NEW_MODE)
        #
        # if the new mode key is None,
        # the method is used when leaving the old mode
        # eg. self._mode_transition_react_methods (OLD_MODE, None)
        #
        # NOTE: these methods will be called in the manner specified
        # in _transition_to_mode. They will be called in the order:
        # [mode_left, mode_transition, mode_entered]
        # but this is a purely semantic temporal ordering which does
        # not relate to the actual state of self._mode at any time.
        # By the time these are called, the new mode has already been
        # applied to self._mode
        self._mode_transition_react_methods = {}
        self._register_mode_transition_method (KEY_PASSTHROUGH,
                         LINE_BUFFERED,
                         self.mode_transition_key_passthrough_to_line_buffered)

        self._register_mode_transition_method (LINE_BUFFERED,
                         KEY_PASSTHROUGH,
                         self.mode_transition_line_buffered_to_key_passthrough)

        self._register_mode_entered_method (QUIT_PROMPT,
                        self._mode_entered_quit_prompt)

        self._register_mode_left_method (QUIT_PROMPT,
                        self._mode_left_quit_prompt)

        # used to hold the line buffer in line-editing mode
        self._line_buffer = ""

        # used to display a notifier when the line-mode is toggled
        self._notifier = pysshlm_config.get ("line_mode_notifier")
        self._line_buffered_mode_notifier_on = '[%s]' % (self._notifier,)
        self._line_buffered_mode_notifier_off = '[\%s]' % (self._notifier,)

        # used to display a prompt when entering quit mode
        self._quit_prompt_message = pysshlm_config.get ("quit_prompt_message")

        # save a reference to the cmd
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

        # two looping threads that will process input and
        # output to/from the user / pty
        # they are initialized and run in enter()
        self._flow_output_thread = None
        self._flow_input_thread = None

        # used to allow the flow_output thread to
        # end itself and flow_input if we get EOF
        self._session_over_flag = threading.Event()

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
        # check if the window has changed size
        def check_resize():
            while self._pty.isalive():
                time.sleep (1)
                if self._has_been_resized:
                    self._pty.setwinsize (*(get_term_dimensions()))
                    self._has_been_resized = False
        check_resize_thread = threading.Thread (target=check_resize)
        check_resize_thread.setDaemon (True)
        check_resize_thread.start()

    #
    #
    # hotkey and mode transition methods
    #
    #

    # transition to a given mode
    def _transition_to_mode (self, new_mode):
        if (self._mode == new_mode):
            return  # already in the mode
        else:
            # change the mode state
            old_mode = self._mode
            self._last_mode = old_mode
            self._mode = new_mode
            # run mode transition react methods
            self._on_mode_left (old_mode)
            self._on_mode_transition (old_mode, new_mode)
            self._on_mode_entered (new_mode)

    # react to a mode transition
    def _on_mode_transition (self, old_mode, new_mode):
        if (self._mode_transition_react_methods.get (old_mode)
                        is not None and
            self._mode_transition_react_methods [old_mode].get (new_mode)
                        is not None):
            # if we're here, we've confirmed the transition
            # react method exists, call it
            self._mode_transition_react_methods [old_mode] [new_mode] ()

    def _on_mode_left (self, old_mode):
        self._on_mode_transition (old_mode, None)

    def _on_mode_entered (self, new_mode):
        self._on_mode_transition (None, new_mode)

    # attach a method to the _mode_transition_react_methods map
    def _register_mode_transition_method (self, old_mode, new_mode, method):
        # build necessary map hierarchy
        if self._mode_transition_react_methods.get (old_mode) is None:
            self._mode_transition_react_methods [old_mode] = {}
        # attach the method to the map
        self._mode_transition_react_methods [old_mode] [new_mode] = method

    def _register_mode_left_method (self, old_mode, method):
        self._register_mode_transition_method (old_mode, None, method)

    def _register_mode_entered_method (self, new_mode, method):
        self._register_mode_transition_method (None, new_mode, method)

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
    def mode_transition_key_passthrough_to_line_buffered (self):
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
            self.close()
        elif (key == 'n' or
                key == 'N'):
            self._transition_to_mode (self._last_mode)

    #
    #
    # key_passthrough mode methods
    #
    #

    # run on entering KEY_PASSTHROUGH from LINE_BUFFERED
    def mode_transition_line_buffered_to_key_passthrough (self):
        self._cancel_current_line_edits()
        self._io.display_notifier (self._line_buffered_mode_notifier_off)

    def _process_keypress_key_passthrough (self, key):
        self._pty.write (key)

    #
    #
    # input processing functions
    #
    #

    # react to a keypress - main entrypoint for every keypress,
    # regardless of mode or whether key is hotkey
    def _on_press (self, key):

        # block keypress processing while a notifier active
        self._io.can_process_keypress_flag.wait()

        # check if key pressed is a mode transition hotkey for the current mode
        if (key in self._hotkey_mode_transition_map [self._mode].keys()):
            # if it's active, act on it
            new_mode = self._hotkey_mode_transition_map [self._mode] [key]
            self._transition_to_mode (new_mode)

        # else process the keypress according to the current mode
        else:
            # process key press according to current mode
            self._keypress_processor_methods_by_mode [self._mode] (key)

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
                # break, since this will only come if the pty is dead
                break
            except UnicodeDecodeError as e:
                self._io.screen_writeln ("[pysshlm]: %s." % (str (e),))
                self._io.screen_writeln ("[pysshlm]: Possibly stdout of \
                        session tried to send binary data, such as when \
                        running \"cat\" on a binary file?")

    def _flow_input (self):
        while not self._session_over_flag.is_set():
            c = sys.stdin.read (1)
            self._on_press (c)

    #
    #
    # publicly-exposed functions
    #
    #

    def exit (self):
        self._session_over_flag.set()
        termios.tcsetattr (sys.stdin.fileno(),
                termios.TCSADRAIN,
                self._old_tty_settings)

    # begin actually acting as a thin layer -
    # start flowing input and output to/from the pty
    def enter (self):

        # kick into raw mode
        self._old_tty_settings = termios.tcgetattr (sys.stdin.fileno())
        tty.setraw (sys.stdin.fileno())

        self._flow_output_thread = threading.Thread (target=self._flow_output)
        self._flow_output_thread.setDaemon (True)
        self._flow_output_thread.start()

        self._flow_input_thread = threading.Thread (target=self._flow_input)
        self._flow_input_thread.setDaemon (True)
        self._flow_input_thread.start()

        self._session_over_flag.wait()
        self.exit()
