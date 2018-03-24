"""runner functions for entry points"""
import argparse
import sys

from twisted.internet import reactor
from twisted.python import log
from twisted.internet.endpoints import TCP4ServerEndpoint

from fbad import constants
from fbad.server import FBADServerFactory


def server_main():
    """entry point for the server"""
    parser = argparse.ArgumentParser(description="The FBAD Server")
    parser.add_argument("-i", "--interface", action="store", help="interface to listen on", default="0.0.0.0")
    parser.add_argument("-p", "--port", action="store", type=int, default=constants.DEFAULT_PORT, help="port to listen on")
    parser.add_argument("-P", "--password", action="store", default=None, help="protect this server using this password")
    parser.add_argument("-v", "--verbose", action="store_true", help="be more verbose")
    ns = parser.parse_args()

    if ns.verbose:
        log.startLogging(sys.stdout)

    factory = FBADServerFactory(ns.password)
    ep = TCP4ServerEndpoint(reactor, port=ns.port, interface=ns.interface)
    ep.listen(factory)

    reactor.run()
