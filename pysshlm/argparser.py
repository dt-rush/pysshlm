import argparse

argparser = argparse.ArgumentParser()
argparser.add_argument ('ssharg',
                        help='the argument to give to ssh (could be a host or user@host)')

argparser.add_argument ('--password',
                        required=False,
                        help='the password to enter once the ssh connection goes noecho upon opening')
