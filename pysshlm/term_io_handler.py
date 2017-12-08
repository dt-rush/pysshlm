import sys
import threading


class TermIOHandler():

    def __init__ (self, pty):

        # used to write to the pty
        self._pty = pty
        
        # used to prevent stdout writing contention / interleaving
        # thanks to Alex Martelli for suggesting this pattern
        # https://stackoverflow.com/a/3030755/4785602
        self._stdout_lock = threading.RLock()
        self._lock_nesting = 0

        # used to block processing keypresses while notifier active
        self.can_process_keypress_flag = threading.Event()
        self.can_process_keypress_flag.set()
        # used to prevent race conditions in displaying / waiting / erasing a notifier (using threading.Timer)
        self._notifier_write_lock = threading.Lock()
        # the currently-displayed notifier string
        self._current_notifier_str = ""

    def pty_write (self, s):
        self._pty.write (s)

    def screen_write (self, s):
        self._get_stdout_lock()
        sys.stdout.write (s)
        sys.stdout.flush()
        self._drop_stdout_lock()

    # clear n characters backward (can't go past line-breaks)
    def backspace (self, n):
        self.screen_write ('\b' * n + ' ' * n + '\b' * n)

    def wait_enter_noecho_password (self, password):
        self._pty.waitnoecho()
        self._pty.write (password + '\r')

    # used to notify the user of various things by temporarily displaying a message
    # there is some dank lock / flag / thread logic here, so be careful to read good
    def display_notifier (self, msg, duration=0.5):
        self._notifier_write_lock.acquire()
        # clear if existing notifier is displayed
        if len (self._current_notifier_str) != 0:
            self.backspace (len (self._current_notifier_str))
        # set the current notifier str and write it
        self._current_notifier_str = msg
        self.screen_write (self._current_notifier_str)
        self.can_process_keypress_flag.clear()
        self._notifier_write_lock.release()
        
        # to be run after a delay
        def remove_active_notifier():
            self._notifier_write_lock.acquire()
            if len (self._current_notifier_str) != 0:
                self.backspace (len (self._current_notifier_str))
                self._current_notifier_str = ""
            self._notifier_write_lock.release()
            self.can_process_keypress_flag.set()
        threading.Timer (duration, remove_active_notifier).start()

    # used to support screen_write
    def _get_stdout_lock (self):
        self._stdout_lock.acquire()
        self._lock_nesting += 1

    # used to support screen_write
    def _drop_stdout_lock(self):
        nesting = self._lock_nesting
        self._lock_nesting = 0
        for i in range (nesting):
            self._stdout_lock.release()
