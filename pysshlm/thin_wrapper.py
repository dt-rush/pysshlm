import os
import time
import tty
import termios
import threading
import signal
import unicodedata

from blessed import Terminal
from blessed.keyboard import Keystroke

from ptyprocess import PtyProcessUnicode

from pysshlm.config import pysshlm_config
from pysshlm.term_io_handler import TermIOHandler

# helper function
def get_term_dimensions():
    return tuple (map (lambda (x): int(x), os.popen('stty size', 'r').read().split()))



# wrapper class handling input buffering, managing the opening and closing of the PTY 
class ThinWrapper():

    def __init__ (self, cmd, password=None):

        # hotkey to enter line-editing mode (raw key value)
        # read hotkey definition from pysshlm.cfg
        # (hotkey will determine if we're popping into or out of line-editing mode)
        self._hotkey = pysshlm_config.get ("hotkey")

        # are we editing in line mode or single-char-send mode? default to no
        self._line_mode = False

        # used to hold the line buffer in line-editing mode
        self._line_buffer = ""

        # used to display a notifier when the line-mode is toggled
        self._notifier = pysshlm_config.get ("notifier")
        self._line_mode_notifier_on = '[%s]' % (self._notifier,)
        self._line_mode_notifier_off = '[\%s]' % (self._notifier,)

        # god bless the author of blessed for their work in setting up sequence handling
        self._t = Terminal()

        # save a reference to the cmd and password for future use
        self._cmd = cmd
        # it's up to you to ensure that there aren't programs on your machine reading memory for passwords,
        # and if they can do that, they can also read private keys GG
        self._password = password
        # spawn the PTY (get dimensions from current tty)
        self._pty = PtyProcessUnicode.spawn (cmd, dimensions=get_term_dimensions())

        # for handling reading/writing to/from pty and writing to the user's terminal
        self._io = TermIOHandler (self._pty)

         # set-up handling for terminal window resize
        self._setup_SIGWINCH_handler()
        self._has_been_resized = False
        
        # two looping threads that will process input and output to/from the user / pty
        # they are initialized and run in enter()
        self._flow_output_thread = None
        self._flow_input_thread = None

        

    #
    #
    # terminal handling functions
    #
    #

    # attach a listener for window change signal to propagate the change to the PTY
    def _setup_SIGWINCH_handler (self):
        # handler for the signal
        def handler (signum, stackframe):
            self._has_been_resized = True
        # listen for the signal
        signal.signal (signal.SIGWINCH, handler)
        # create a thread that every 1000 milliseconds will check if the window has changed size
        def check_resize():
            while self._pty.isalive():
                time.sleep (1)
                if self._has_been_resized:
                    self._pty.setwinsize (*(get_term_dimensions()))
                    self._has_been_resized = False
        check_resize_thread = threading.Thread (target=check_resize)
        check_resize_thread.setDaemon (True)
        check_resize_thread.start()

    def _notice_pty_dead (self):
        self._io.screen_write ("[pysshlm]: %s session died" % (self._cmd[0]))


        
    #
    #
    # line-mode functions
    #
    #

    # toggle whether we're in line-entry mode
    def _toggle_line_mode (self):
        self._line_mode = not self._line_mode

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
        # TODO: after implementation of arrow keys in line-mode, tracking of position,
        # insert at the position rather than append
        self._line_buffer += s


        
    #
    #
    # input processing functions
    #
    #
    
    def _process_keypress_normal (self, key):
        self._pty.write (key)

    def _process_keypress_line_mode (self, key):

        # handle blessed.Keystroke values
        if type (key) is Keystroke:
            self._process_blessed_keystroke (key)
            
        # handle direct key value passthrough (as in the case of CTRL-C)            
        elif type (key) is unicode:
            self._process_raw_keyval (key)
            
    def _process_raw_keyval (key):
        # CTRL-C in line-mode cancels edits
        if key == '\x03':
            self._cancel_current_line_edits()
            self._io.display_notifier ("[cleared line]")

    def _process_blessed_keystroke (self, key):
        # enter submits the current line buffer
        if key.code == self._t.KEY_ENTER:
            self._io.backspace (len (self._line_buffer))
            self._io.pty_write (self._line_buffer + '\r')
            self._clear_line_buffer()

        # NOTE: delete / backspace both get mapped to KEY_DELETE by blessed
        # backspace a char
        elif key.code == self._t.KEY_DELETE:
            if len (self._line_buffer) != 0:
                # note that \b only moves cursor left, we have to overwrite it and come back
                self._io.screen_write ('\b \b')
                # strip 1 char from linebuffer
                self._line_buffer = self._line_buffer[:-1]

        # elif IS MOVEMENT KEY?
        # TODO: implement position tracking (left, right) in where we write / backspace
        # TODO: make sure that CTRL-left, CTRL-right work properly
        # TODO: implement "up"/"down" via a stack of past lines, with [0] == current line_buffer

        # until the above is implemented, ignore all sequences, they should not be added to the buffer
        elif key.is_sequence:
            pass

        # handle control sequence chars (which are best compared with their direct char values)
        elif unicodedata.category (key) == "Cc":
            # handle ctrl + D (remember we're in line-mode)
            if key == u'\x04':
                self._io.display_notifier ("[exit line-mode to send CTRL-D]", 0.8)
            # ignore all control chars not handled above
            else:
                self._io.display_notifier ("[line-mode ignores control chars]", 0.8)

        # handle all other key presses (AKA those not detected above) in line-mode by appending to buffer
        else:
            self._add_to_line_buffer (key)

    # either store in line-buffer or send directly
    def _process_keypress (self, key):

        # block keypress processing while a notifier active
        self._io.can_process_keypress_flag.wait()

        if not self._line_mode:
            self._process_keypress_normal (key)
        else:
            self._process_keypress_line_mode (key)

    # react to a keypress
    def _on_press (self, key):
        # if hotkey, toggle line-mode (and display notifier)
        if repr (key) == self._hotkey:
            self._toggle_line_mode()
            if not self._line_mode:
                # if we turned it off, erase the line so far written
                self._cancel_current_line_edits()
                self._io.display_notifier (self._line_mode_notifier_off)
            else:
                self._io.display_notifier (self._line_mode_notifier_on)
        # else process char 
        else:
            self._process_keypress (key)



    #
    #
    # publicly-exposed functions
    #
    #
            
    # begin actually acting as a thin layer - start flowing input and output to/from the pty
    def enter (self):

        # provide a password to the pty if one was given, once it
        # enters/is in noecho, before proceeding
        if self._password is not None:
            self._io.wait_enter_noecho_password (self._password)

        # used to allow the flow_output thread to end itself and flow_input if we get EOF
        session_over_flag = threading.Event()
        
        # read from the pty output and forward to stdout
        def flow_output ():
            while not session_over_flag.is_set():
                time.sleep (0.005)
                try:
                    s = self._pty.read (size=1024)
                    self._io.screen_write (s)
                except EOFError:
                    break # break, since this will only come if the pty is dead
                except UnicodeDecodeError as e:
                    self._io.screen_write ("\n[pysshlm]: %s.\n" % (str (e),))
                    self._io.screen_write ("[pysshlm]: Possibly stdout of session tried to send binary data, such as when running \"cat\" on a binary file?\n")
            # if we're here, the pty died or sent EOF
            self._notice_pty_dead()
            session_over_flag.set()

        self._flow_output_thread = threading.Thread (target=flow_output)
        self._flow_output_thread.setDaemon (True)
        self._flow_output_thread.start()

        
        # read from user stdin (in cbreak mode) and pass to processing functions
        input_loop_finished_flag = threading.Event()
        def flow_input ():
            # in practice, the thread running tihs loop can also be
            # terminated by flow_output getting EOFError
            while not session_over_flag.is_set():
                # read a single char
                with self._t.cbreak():
                    try:
                        # wait at most 200ms for a keypress to process before continuing
                        c = self._t.inkey (timeout=0.2)
                        if str(c) != u'': # timeout returns u''
                            self._on_press (c)
                    except KeyboardInterrupt:
                        # catch keyboard interrupt and pass through as a unicode string directly
                        self._on_press (u'\x03')
                    # NOTE / TODO: if the terminal receives a control character
                    # in the time between each of these tight loops, it will
                    # usually default to displaying it, like "^L", as in the case
                    # of spamming the hotkey (meaning the backspace will be off,
                    # and two characters will be left hanging there)
                    # improving the backspace function to backspace *to* a specific point
                    # would be good, but would require a slight reworking of the notifier
                    # logic in term_io_handler.py to remember the position that
                    # remove_active_notifier() should know to backspace *to*

            # if we're here, the input loop has terminated
            input_loop_finished_flag.set()

        self._flow_input_thread = threading.Thread (target=flow_input)
        self._flow_input_thread.setDaemon (True)
        self._flow_input_thread.start()

        # wait here to avoid falling through since all we did above was spawn threads
        # we specifically wait for the input thread to finish since if it dies while waiting
        # for a char in cbreak mode, the terminal will be stuck in cbreak mode
        input_loop_finished_flag.wait()

