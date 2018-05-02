#!/usr/bin/env python

import sys
import threading
import termios
import tty

from blessed import Terminal


class SimpleThinWrapperMock():

    def __init__ (self):
        self._input_loop_finished_flag = threading.Event()
        self._session_over_flag = threading.Event()
        self._special_key_map = {
            u'\x03': self._end_session
        }
        self._t = Terminal()

    def _is_special_key (self, c):
        return c in self._special_key_map.keys()

    def _act_on_special_key (self, c):
        self._special_key_map [c]()

    def _act_on_regular_key (self, c):
        sys.stdout.write ('%s\r\n' % (c.encode ('hex'),))
        sys.stdout.flush()

    def _on_press (self, c):
        if self._is_special_key (c):
            self._act_on_special_key (c)
        else:
            self._act_on_regular_key (c)

    def _end_session (self):
        self._session_over_flag.set()
        sys.stdout.write ('---SESSION OVER---\r\n')
        sys.stdout.flush()
        self._exit()

    def _flow_input (self):
        while not self._session_over_flag.is_set():
            # c = sys.stdin.read (1)
            c = self._t.inkey (timeout=0.3)
            if c != '':
                self._on_press (c)
        self._input_loop_finished_flag.set()

    def _exit (self):
        termios.tcsetattr (sys.stdin.fileno(),
                termios.TCSADRAIN,
                self._old_settings)

    def enter (self):
        self._old_settings = termios.tcgetattr (sys.stdin.fileno())
        tty.setraw (sys.stdin.fileno())
        self._flow_input_thread = threading.Thread (target=self._flow_input)
        self._flow_input_thread.start()
        self._input_loop_finished_flag.wait()


def main():
    wrapper = SimpleThinWrapperMock()
    wrapper.enter()


if __name__ == '__main__':
    main()
