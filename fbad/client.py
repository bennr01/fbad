"""the client protocol."""
import hashlib
import json

from twisted.internet import defer, threads
from twisted.protocols.basic import IntNStringReceiver

from fbad import constants, errors


class FBADClientProtocol(IntNStringReceiver):
    """
    The protocol for the FBAD client.
    :param password: password for the server
    :type password: str or None
    :param d: Deferred to call back
    :type d: Deferred or None
    :param out: output to write build messages to
    :type out: file-like object
    """
    structFormat = constants.MESSAGE_LENGTH_PREFIX
    prefixLength = constants.MESSAGE_LENGTH_PREFIX_LENGTH
    MAX_LENGTH = constants.MAX_MESSAGE_LENGTH

    STATE_IGNORE = -2
    STATE_ERROR = -1
    STATE_WAIT_VERSION_RESPONSE = 0
    STATE_WAIT_AUTH_RESPONSE = 1
    STATE_READY = 2
    STATE_BUILDING = 3

    def __init__(self, password=None, d=None, out=None):
        self.password = password
        self.d = d
        self.out = out

    def connectionMade(self):
        """
        Called when the connection to the server was established.
        """
        self.send_version()
        self.state = self.STATE_WAIT_VERSION_RESPONSE

    def send_version(self):
        """
        Send the version to the server.
        """
        self.sendString(constants.COM_VERSION)

    def stringReceived(self, msg):
        """
        Called when a string was received.
        :param msg: the received string
        :type msg: str
        """

        if self.state == self.STATE_IGNORE:
            # ignore message
            pass

        elif self.state == self.STATE_WAIT_VERSION_RESPONSE:
            self.handle_version_response(msg)

        elif self.state == self.STATE_WAIT_AUTH_RESPONSE:
            self.handle_auth_response(msg)

        elif self.state == self.STATE_BUILDING:
            self.handle_build_message(msg)

        else:
            self.handle_protocol_violation(msg)

    def handle_version_response(self, msg):
        """
        Handle a version response.
        :param msg: the version response from the server.
        :type msg: str
        """
        if msg == "E":
            self.handle_version_mismatch()
        elif msg == "O":
            self.handle_ready()
        elif msg.startswith("A"):
            if len(msg) < 2:
                self.handle_protocol_violation()
            else:
                challenge = msg[1:]
                self.handle_auth_challenge(challenge)

    def handle_ready(self):
        """
        Called when the server is ready.
        """
        self.state = self.STATE_READY
        if self.d is not None:
            self.d.callback(self)

    def handle_auth_challenge(self, challenge):
        """
        Handle a auth challenge.
        :param challenge: the challenge
        :type challenge: str
        """
        if self.password is not None:
            answer = hashlib.sha256(challenge + self.password).digest()
            self.state = self.STATE_WAIT_AUTH_RESPONSE
            self.sendString(answer)
        else:
            if self.d is not None:
                self.d.errback(errors.PasswordRequired("Password required, but None specified!"))

    def handle_auth_response(self, msg):
        """
        Handle the auth response.
        :param msg: the auth response
        :type msg: str
        """
        if msg == "O":
            self.state = self.STATE_READY
            if self.d is not None:
                self.d.callback(self)
        elif msg == "F":
            self.state = self.STATE_ERROR
            self.transport.loseConnection()
            if self.d is not None:
                self.d.errback(errors.InvalidPassword("Password rejected!"))
        else:
            self.handle_protocol_violation(msg)

    def handle_protocol_violation(self, msg=None):
        """
        Called when a message violated the protocol.
        :param msg: the violating message or None.
        :type msg: str or None
        """
        self.transport.loseConnection()

    def handle_build_message(self, msg):
        """
        Handles a build message.
        :param msg: the build message
        :type msg: str
        """
        data = json.loads(msg)
        ty = data["type"]
        if ty == "msg":
            s = data.get("message", "<No message body received>")
            if self.out is not None:
                self.out.write(s)
        elif ty == "finish":
            exitcodes = data.get("exitcodes", [])
            self.build_d.callback(exitcodes)
        else:
            self.handle_protocol_violation(msg)

    def disconnect(self):
        """
        Disconnect from the server.
        """
        self.transport.loseConnection()

    @defer.inlineCallbacks
    def remote_build(self, project, zippath, only=None, push=False):
        """
        Run a remote build.
        :param project: project to build
        :type project: Project
        :param zippath: path of zip containg the project files
        :type zippath: str or unicode
        :param only: which images to built, specified by their name
        :type only: str or unicode or None
        :param push: if True, push images to the registry
        :type push: bool
        :return: a deferred which fires with the exitcodes of the build processes.
        :rtype: Deferred
        """
        if self.state != self.STATE_READY:
            raise RuntimeError("Protocol not yet ready!")

        self.state = self.STATE_BUILDING
        self.build_d = defer.Deferred()
        ser_project = project.dumps()
        self.sendString(
            json.dumps(
                {
                    "command": "build",
                    "project": ser_project,
                    "only": only,
                    "push": push,
                }
                ).encode(constants.ENCODING),
            )
        with open(zippath, "rb") as fin:
            yield self.send_file(fin)
        exitcodes = yield self.build_d
        self.state = self.STATE_READY
        defer.returnValue(exitcodes)

    @defer.inlineCallbacks
    def send_file(self, fin):
        """
        Send a file  to the server.
        :param fin: file to read
        :type fin: file-like object
        """
        while True:
            data = yield threads.deferToThread(fin.read, constants.READ_CHUNK_SIZE)
            if data:
                self.sendString(constants.MESSAGE_PREFIX_CONTINUE + data)
            else:
                self.sendString(constants.MESSAGE_PREFIX_END)
                break
