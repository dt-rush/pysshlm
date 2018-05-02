import os


def get_term_dimensions():
    return tuple (map (int, os.popen('stty size', 'r').read().split()))
