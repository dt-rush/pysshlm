from os import path

from ConfigParser import SafeConfigParser

here = path.abspath (path.dirname (__file__))

configparser = SafeConfigParser()
configparser.read (path.join (here, "pysshlm.cfg"))
pysshlm_config = configparser._sections['pysshlm']


