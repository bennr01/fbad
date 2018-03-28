"""the server protocol."""
import os
import hashlib
import json

from twisted.internet import defer, error
from twisted.protocols.basic import IntNStringReceiver
from twisted.internet.protocol import Factory, ProcessProtocol

from fbad import constants
from fbad.project import Project


class FBADServerProtocol(IntNStringReceiver):
    """The protocol for the FBAD server."""
    structFormat = constants.MESSAGE_LENGTH_PREFIX
    prefixLength = constants.MESSAGE_LENGTH_PREFIX_LENGTH
    MAX_LENGTH = constants.MAX_MESSAGE_LENGTH

    STATE_IGNORE = -1
    STATE_WAIT_VERSION = 0
    STATE_AUTH = 1
    STATE_READY = 2
    STATE_FILE_RECEIVE = 4
    STATE_BUILDING = 5

    def connectionMade(self):
        """
        Called when the connection to a client was established.
        """
        self.state = self.STATE_WAIT_VERSION
        self.project = None  # current project
        self.outf = None  # file to write received data to
        self.recv_d = None  # deferred to callback when a file was received.

    def stringReceived(self, msg):
        """
        Called when a string was received.
        :param msg: the received string
        :type msg: str
        """

        if self.state == self.STATE_IGNORE:
            # ignore message
            pass

        elif self.state == self.STATE_WAIT_VERSION:
            self.handle_version(msg)

        elif self.state == self.STATE_AUTH:
            self.handle_auth(msg)

        elif self.state == self.STATE_READY:
            self.handle_command(msg)

        elif self.state == self.STATE_FILE_RECEIVE:
            self.handle_file_data(msg)

        else:
            self.handle_protocol_violation(msg)

    def handle_version(self, msg):
        """
        Handle a version message.
        :param msg: the version message from the client.
        :type msg: str
        """
        if msg != constants.COM_VERSION:
            self.sendString("E")  # version mismatch
            self.state = self.STATE_IGNORE
            self.transport.loseConnection()
        else:
            if self.factory.password is not None:
                self.challenge = self.get_random_bytes(constants.AUTH_SEED_LENGTH)
                self.sendString("A" + self.challenge)  # version ok; Auth required
                self.state = self.STATE_AUTH
            else:
                self.sendString("O")  # version ok; no auth required
                self.state = self.STATE_READY

    def handle_auth(self, msg):
        """
        Handle an auth message.
        :param msg: the auth message
        :type msg: str
        """
        res = hashlib.sha256(self.challenge + self.factory.password).digest()
        if res == msg:
            # auth ok
            self.sendString("O")
            self.state = self.STATE_READY
        else:
            # auth fail
            self.sendString("F")
            self.state = self.STATE_IGNORE
            self.transport.loseConnection()

    @defer.inlineCallbacks
    def handle_command(self, msg):
        """
        Handle a command.
        :param msg: the command
        :type msg: str
        """
        info = json.loads(msg.decode(constants.ENCODING))
        if info["command"] == "build":
            self.state = self.STATE_BUILDING
            projectdata = info["project"]
            only = info.get("only", None)
            do_push = info.get("push", False)
            self.project = Project.loads(projectdata)

            # receive project data
            self.recv_d = defer.Deferred()
            with self.project.get_temp_build_dir() as tp:
                zp = os.path.join(tp, "projectdata.zip")
                self.outf = open(zp, "wb")
                self.state = self.STATE_FILE_RECEIVE
                yield self.recv_d
                self.srare = self.STATE_BUILDING
                self.outf.flush()
                self.outf.close()
                protofactory = lambda self=self: OutputRelayProtocol(self, d=defer.Deferred())
                exitcodes = yield self.project.build_from_zip_path(zp, protocolfactory=protofactory, only=only)
                if do_push:
                    yield self.project.push(only=only, protocolfactory=protofactory)
                self.send_exitcodes(exitcodes)

            self.state = self.STATE_READY

        else:
            self.handle_protocol_violation(msg)

    def handle_file_data(self, msg):
        """
        Handle a message containing file data.
        :param msg: the data with a prefix
        :type msg: str
        """
        if len(msg) == 0:
            return
        prefix = msg[0]
        data = msg[1:]
        if prefix == constants.MESSAGE_PREFIX_CONTINUE:
            self.outf.write(data)
        elif prefix == constants.MESSAGE_PREFIX_END:
            if len(data) > 0:
                self.outf.write(data)
            self.recv_d.callback(None)
        else:
            self.handle_protocol_violation(msg)

    def handle_protocol_violation(self, msg=None):
        """
        Called when a message violated the protocol.
        :param msg: the violating message or None.
        :type msg: str or None
        """
        self.transport.loseConnection()

    def get_random_bytes(self, n):
        """
        Return n random bytes.
        :param n: number of random bytes to return
        :type n: int
        :return: random bytes
        :rtype: str
        """
        return os.urandom(n)

    def send_message(self, msg):
        """
        Sends a console message to the client.
        :param msg: message the client should print
        :type msg: str or unicode
        """
        jdata = {
            "type": "msg",
            "message": msg,
            }
        tosend = json.dumps(jdata).encode(constants.ENCODING)
        self.sendString(tosend)

    def send_exitcodes(self, exitcodes):
        """
        Sends the exitcodes to the client.
        :param exitcodes: list of the exitcodes of the process.
        :type exitcodes: list of ints
        """
        jdata = {
            "type": "finish",
            "exitcodes": exitcodes,
            }
        tosend = json.dumps(jdata).encode(constants.ENCODING)
        self.sendString(tosend)


class FBADServerFactory(Factory):
    """
    The Factory for the fbad server.
    :param password: password for the authentification
    :type password: str or None
    """
    protocol = FBADServerProtocol

    def __init__(self, password=None):
        self.password = password


class OutputRelayProtocol(ProcessProtocol):
    """
    A protocol for relaying subprocess outputs and exit codes.
    :param client: protocol connected with the client
    :type client: FBADServerProtocol
    :param d: deferred which will be fired with the exit code of the process
    :type d: Deferred
    """
    def __init__(self, client, d):
        self.client = client
        self.d = d

    def outReceived(self, data):
        """
        Called when data was received on stdout.
        :param data: received data
        :type data: str or unicode
        """
        self.on_data_received(data)

    def errReceived(self, data):
        """
        Called when data was received on stderr.
        :param data: received data
        :type data: str or unicode
        """
        self.on_data_received(data)

    def on_data_received(self, data):
        """
        Called when data was received on std*.
        :param data: received data
        :type data: str or unicode
        """
        self.client.send_message(data)

    def processEnded(self, status):
        """
        Called when the process ended.
        :param status: the exit status of the process
        :type status: Failure
        """
        sv = status.value
        if isinstance(sv, error.ProcessDone):
            exitcode = 0
        elif isinstance(sv, error.ProcessTerminated):
            exitcode = sv.exitCode
        else:
            raise Exception("Unexpected status result of process!")
        self.d.callback(exitcode)
