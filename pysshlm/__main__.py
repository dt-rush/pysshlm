#!/usr/bin/env python
# coding: utf8

import sys
import logging



from pysshlm.argparser import argparser
from pysshlm.funcs import run_session


banner="""
┌─┐┬ ┬┌─┐┌─┐┬ ┬┬  ┌┬┐
├─┘└┬┘└─┐└─┐├─┤│  │││
┴   ┴ └─┘└─┘┴ ┴┴─┘┴ ┴
"""


def main(args=None):

    if args is None:
        args = sys.argv[1:]
        
    args = argparser.parse_args (args)

    ssharg = args.ssharg
    password = args.password

    print banner
    run_session (ssharg, password)

    
    
if __name__ == "__main__":
    main()
