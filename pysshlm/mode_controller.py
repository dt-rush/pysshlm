class ModeController():

    def __init__ (self, initial_mode=None):
        # basic state
        self.mode = initial_mode
        self._last_mode = self.mode
        # _mode_transition_react_methods is a dictionary of methods
        # keyed by an old mode and then a new mode,
        # defining what code should run when transitioning from the
        # old mode to the new mode
        #
        # If the old mode key is None,
        # the method is used whenever entering the new mode
        # eg. self._mode_transition_react_methods (None, NEW_MODE)
        #
        # if the new mode key is None,
        # the method is used whenever leaving the old mode
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

    # transition to a given mode
    def transition_to (self, new_mode):
        if (self.mode == new_mode):
            return  # already in the mode
        else:
            # change the mode state
            old_mode = self.mode
            self._last_mode = old_mode
            self.mode = new_mode
            # run mode transition react methods
            self._mode_left (old_mode)
            self._mode_transitioned (old_mode, new_mode)
            self._mode_entered (new_mode)

    # react to a mode transition
    def _mode_transitioned (self, old_mode, new_mode):
        if (self._mode_transition_react_methods.get (old_mode)
                        is not None and
            self._mode_transition_react_methods [old_mode].get (new_mode)
                        is not None):
            # if we're here, we've confirmed the transition
            # react method exists, call it
            self._mode_transition_react_methods [old_mode] [new_mode] ()

    def _mode_left (self, old_mode):
        self._mode_transitioned (old_mode, None)

    def _mode_entered (self, new_mode):
        self._mode_transitioned (None, new_mode)

    # attach a method to the _mode_transition_react_methods map
    def _on_transition (self, old_mode, new_mode, method):
        # build necessary map hierarchy
        if self._mode_transition_react_methods.get (old_mode) is None:
            self._mode_transition_react_methods [old_mode] = {}
        # attach the method to the map
        self._mode_transition_react_methods [old_mode] [new_mode] = method

    def _on_leave (self, old_mode, method):
        self._on_transition (old_mode, None, method)

    def _on_enter (self, new_mode, method):
        self._on_transition (None, new_mode, method)
