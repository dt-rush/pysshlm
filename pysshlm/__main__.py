#!/usr/bin/env python
# coding: utf8

import sys


from pysshlm.argparser import argparser
from pysshlm.thin_wrapper import ThinWrapper

banner = """
┌─┐┬ ┬┌─┐┌─┐┬ ┬┬  ┌┬┐
├─┘└┬┘└─┐└─┐├─┤│  │││
┴   ┴ └─┘└─┘┴ ┴┴─┘┴ ┴
"""


def main(args=None):

    if args is None:
        args = sys.argv[1:]

    args = argparser.parse_args (args)

    ssharg = args.ssharg

    print (banner)

    # build the wrapper
    w = ThinWrapper (['ssh', '-t', ssharg])
    # enter the wrapper (spawns 2 threads to flow input and
    # output, so is non-blocking)
    w.enter()


if __name__ == "__main__":
    main()
