import os
import sys
import time
import tty
import termios
import threading
import signal

from blessed import Terminal
from blessed.keyboard import Keystroke

from ptyprocess import PtyProcessUnicode

from pysshlm.config import pysshlm_config

# helper function
def get_term_dimensions():
    return tuple (map (lambda (x): int(x), os.popen('stty size', 'r').read().split()))

# wrapper class handling input buffering, managing the opening and closing of the PTY 
class ThinWrapper():

    def __init__ (self, cmd):
        # god bless the author of blessed for their work in setting up sequence handling
        self.t = Terminal()
        # are we editing in line mode or single-char-send mode
        self.line_mode = False
        # hotkey to enter line-editing mode (raw key value)
        # read hotkey definition from pysshlm.cfg
        # (hotkey will determine if we're popping into or out of line-editing mode)
        self.hotkey = pysshlm_config.get ("hotkey")
        # used to hold the line buffer in line-editing mode
        self.line_buffer = ""

        # used to notify the user of popping into / out of line-mode
        self.notifier = pysshlm_config.get ("notifier")
        self.notifier_on = '[%s]' % (self.notifier,)
        self.notifier_off = '[\%s]' % (self.notifier,)
        # used to block processing keypresses while notifier active
        self.can_process_keypress_flag = threading.Event()
        self.can_process_keypress_flag.set()
        # used to prevent race conditions in displaying / waiting / erasing a notifier (using threading.Timer)
        self.notifier_write_lock = threading.Lock()
        # the currently-displayed notifier string
        self.current_notifier_str = ""

        # save a reference to the cmd
        self.cmd = cmd
        # spawn the PTY (get dimensions from current tty)
        self.pty = PtyProcessUnicode.spawn (cmd, dimensions=get_term_dimensions())
        
        # used to prevent stdout writing contention / interleaving
        self.stdout_lock = threading.RLock()
        self.lock_nesting = 0
        
        # set-up handling for terminal window resize
        self.setup_SIGWINCH_handler()
        self.has_been_resized = False
        

        

    # attach a listener for window change signal to propagate the change to the PTY
    def setup_SIGWINCH_handler (self):
        # handler for the signal
        def handler (signum, stackframe):
            self.has_been_resized = True
        # listen for the signal
        signal.signal (signal.SIGWINCH, handler)
        # create a thread that every 1000 milliseconds will check if the window has changed size
        def check_resize():
            while self.pty.isalive():
                time.sleep (1)
                if self.has_been_resized:
                    self.pty.setwinsize (*(get_term_dimensions()))
                    self.has_been_resized = False
        check_resize_thread = threading.Thread (target=check_resize)
        check_resize_thread.setDaemon (True)
        check_resize_thread.start()

    # thanks to Alex Martelli for suggesting this pattern
    # https://stackoverflow.com/a/3030755/4785602
    
    def get_stdout_lock (self):
        self.stdout_lock.acquire()
        self.lock_nesting += 1
        
    def drop_stdout_lock(self):
        nesting = self.lock_nesting
        self.lock_nesting = 0
        for i in range (nesting):
            self.stdout_lock.release()

    def locked_stdout_write (self, s):
        self.get_stdout_lock()
        sys.stdout.write (s)
        sys.stdout.flush()
        self.drop_stdout_lock()



    def notice_pty_dead (self):
        print "[pysshlm]: %s session died" % (self.cmd[0])
        # needed since the stdin read will want a char before the loop can end in enter(),
        # even though the session is dead
        print "[pysshlm]: (press any key)"

            
        
    # toggle whether we're in line-entry mode
    def toggle_line_mode (self):
        self.line_mode = not self.line_mode


    # there is some dank lock / flag / thread logic here, so be careful to read good
    def display_notifier (self, msg):
        self.notifier_write_lock.acquire()
        # clear if existing notifier is displayed
        if len (self.current_notifier_str) != 0:
            self.backspace (len (self.current_notifier_str))
        # set the current notifier str and write it
        self.current_notifier_str = msg
        self.locked_stdout_write (self.current_notifier_str)
        self.can_process_keypress_flag.clear()
        self.notifier_write_lock.release()
        
        # to be run after a delay
        def remove_active_notifier():
            self.notifier_write_lock.acquire()
            if len (self.current_notifier_str) != 0:
                self.backspace (len (self.current_notifier_str))
                self.current_notifier_str = ""
                self.can_process_keypress_flag.set()
            self.notifier_write_lock.release()
        threading.Timer (0.5, remove_active_notifier).start()
        
        
    # delete the current line buffer from the screen and clear it in memory
    def cancel_current_line_edits (self):
        self.backspace (len (self.line_buffer))
        self.clear_line_buffer()

    # clear the current line buffer
    # TODO: access stack properly when line history is implemented
    def clear_line_buffer (self):
        self.line_buffer = ""

    # clear n characters backward (can't go past line-breaks)
    def backspace (self, n):
        self.locked_stdout_write ('\b' * n + ' ' * n + '\b' * n)

    # add a string to the line buffer
    def add_to_line_buffer (self, s):
        self.locked_stdout_write (s)
        # TODO: after implementation of arrow keys in line-mode, tracking of position,
        # insert at the position rather than append
        self.line_buffer += s

        

    # either store in line-buffer or send directly
    def process_keypress (self, key):

        # block keypress processing while a notifier active
        self.can_process_keypress_flag.wait()

        if not self.line_mode:
            # if not in line mode, simply send the key
            self.pty.write (key)
            
        else:

            # if we ARE in line mode...

            # handle direct key passthrough (as in the case of CTRL-C)
            if type (key) == unicode:
                if key == '\x03':
                    # CTRL-C in line-mode cancels edits
                    self.cancel_current_line_edits()
                    self.display_notifier ("[cleared line]")

            else:
                # if the above is not true, we are handling an instance of blessed.keyboard.Keystroke
                # we *should* crash here otherwise, as it means someone has edited the code to provide
                # more types of keys. This is really just to aid readability more than it is "defensive"
                assert (type (key) is Keystroke)    

                # handle special key codes

                # enter submits the current line buffer
                if key.code == self.t.KEY_ENTER:
                    self.backspace (len (self.line_buffer))
                    self.pty.write (self.line_buffer + '\r')
                    self.clear_line_buffer()

                # NOTE: delete / backspace both get mapped to KEY_DELETE by blessed
                # backspace a char
                elif key.code == self.t.KEY_DELETE:
                        # a bit of a hack, since \b only moves the cursor back,
                        # we want to move it back, write a space, then move it back again
                        if len (self.line_buffer) != 0:
                            self.locked_stdout_write ('\b \b')
                        # if printed char was backspace, strip 1 char from linebuffer
                        self.line_buffer = self.line_buffer[:-1]


                # elif IS MOVEMENT KEY?
                # TODO: implement position tracking (left, right) in where we write / backspace
                # TODO: make sure that CTRL-left, CTRL-right work properly
                # TODO: implement "up"/"down" via a stack of past lines, with [0] == current line_buffer
                # until the above is implemented, ignore all sequences, they should not be added to the buffer
                elif key.is_sequence:
                    pass # do nothing

                # handle all other key presses (AKA those not detected above) in line-mode by appending to buffer
                
                else:
                    # add to buffer and print to screen so we know what we're typing
                    self.add_to_line_buffer (key)

                    

    # react to a keypress
    def on_press (self, key):
        # if hotkey, toggle line-mode
        if repr (key) == self.hotkey:
            self.toggle_line_mode()
            if not self.line_mode:
                self.cancel_current_line_edits()
            self.display_notifier (self.notifier_on if self.line_mode else self.notifier_off)
        # else process char 
        else:
            self.process_keypress (key)


            
    # begin actually acting as a thing layer - start flowing input and output
    def enter (self):
        
        self.line_mode = False
        
        # read from the pty output and forawrd to stdout
        def flow_output ():
            while self.pty.isalive():
                time.sleep (0.005)
                try:
                    s = self.pty.read (size=1024)
                    self.locked_stdout_write (s)
                except EOFError:
                    break # break, since this will only come if the pty is dead
            self.notice_pty_dead()

        flow_output_thread = threading.Thread (target=flow_output)
        flow_output_thread.setDaemon (True)
        flow_output_thread.start()

        # not written to be called as a thread because otherwise this whole function will pass through,
        # and running pty.wait() to hold up will set up waitpid on a child process, which will explode
        # the universe when SIGWINCH arrives (among other signals, I'm sure)
        def flow_input ():
            while self.pty.isalive():
                time.sleep (0.005)
                # c = sys.stdin.read (1)
                with self.t.cbreak():
                    try:
                        c = self.t.inkey()
                        self.on_press (c)
                    except KeyboardInterrupt:
                        # catch keyboard interrupt and pass through as a unicode string directly
                        self.on_press (u'\x03')
                    

        flow_input()


