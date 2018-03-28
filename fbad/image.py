"""this module defines the Image class which defines build options for an image."""
import os
import json
import subprocess
import platform

from twisted.internet import defer, reactor

from fbad import constants


class Image(object):
    """
    This class represents an Image to build.
    It is mainly used as an argument for the Project() class.
    :param path: the path of this image, relative to the directory containing the project file.
    :type path: str or unicode
    :param name: the name of this image (defaults to the final segment of path)
    :type name: str or unicode
    :param tag: tag to give to the image (defaults to the name)
    :type tag: str or unicode
    :param dockerfile: name of the dockerfile, relative to path (defaults to "Dockerfile")
    :type dockerfile: str or unicode
    :param buildpath: path from which the build of this image will be started,
        relative to the path of the project file (defaults to path).
        This can be used to include other files (if, for example, the dockerfile requires
        access to a shared package defined in a parent directory)
    :type buildpath: str or unicode
    :param preexec_command: command to execute first (format: [prog_path, ARG1, ARG2, ...]
    :type preexec_command: list:
    """
    def __init__(
        self,
        path,
        name=None,
        tag=None,
        dockerfile="Dockerfile",
        buildpath=None,
        preexec_command=None,
        ):
            self.path = path
            # remove trailing slashes
            while self.path.endswith("/"):
                self.path = self.path[:-1]

            if name is not None:
                self.name = name
            else:
                self.name = os.path.basename(self.path)
            if tag is not None:
                self.tag = tag
            else:
                self.tag = self.name
            self.dockerfile = dockerfile
            if buildpath is None:
                self.buildpath = self.path
            else:
                self.buildpath = buildpath
            self.preexec_command = preexec_command

    @defer.inlineCallbacks
    def build(self, path, protocolfactory=None):
        """
        Build the image.
        :param path: path of the project files
        :type path: str or unicode
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the project was built
        :rtype: Deferred
        """
        bp = os.path.join(path, self.buildpath)
        df = os.path.join(self.path, self.dockerfile)
        tag = self.format_tag(self.tag)
        command = ["docker", "build", "-t", tag, "-f", df, "."]
        if self.preexec_command is not None:
            pec = yield self._run_command(
                path=bp,
                executable=self.preexec_command[0],
                command=self.preexec_command,
                protocolfactory=protocolfactory,
                )
            if pec != 0:
                # error running command
                defer.returnValue(pec)

        cec = yield self._run_command(
            path=bp,
            executable=constants.DOCKER_EXECUTABLE,
            command=command,
            protocolfactory=protocolfactory,
            )
        defer.returnValue(cec)

    def _run_command(self, path, executable, command, protocolfactory=None):
        """
        :param path: path to run command in
        :type path: str or unicode
        :param executable: executable to run.
        :type executable: str or unicode
        :param command: command to execute
        :type command: list
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the command executed successfully
        :rtype: Deferred
        """
        if protocolfactory is None:
            c = subprocess.call(command, cwd=path, executable=executable)
            return defer.succeed(c)
        else:
            protocol = protocolfactory()
            d = protocol.d
            reactor.spawnProcess(protocol, executable, args=command, path=path)
            return d

    def format_tag(self, s):
        """
        Format a tag (or another string) with buildserver-specific information.
        :param s: string to format
        :type s: str or unicode
        :return: the formated string
        :rtype: str or unicode
        """
        system, node, release, version, arch, processor = platform.uname()
        info = {
            "system": system,
            "node": node,
            "release": release,
            "arch": arch,
            }
        return s.format(**info)

    @defer.inlineCallbacks
    def push(self, protocolfactory=None):
        """
        Push this Image to a docker registry.
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the command executed successfully
        :rtype: Deferred
        """
        tag = self.format_tag(self.tag)
        command = ["docker", "push", tag]
        exitcode = yield self._run_command(
            path=".",
            executable=constants.DOCKER_EXECUTABLE,
            command=command,
            protocolfactory=protocolfactory,
            )
        defer.returnValue(exitcode)

    def dumpus(self):
        """
        Return a serialized version of this Image() instance as a unicode string.
        :return: the serialized data
        :rtype: unicode
        """
        jdata = {
            "path": self.path,
            "name": self.name,
            "tag": self.tag,
            "dockerfile": self.dockerfile,
            "buildpath": self.buildpath,
            "preexec_command": self.preexec_command,
            }
        return json.dumps(jdata)

    @classmethod
    def loadus(cls, us):
        """
        Load an Image() from a unicode string returned by dumpus()
        :param us: unicode string to load from
        :type us: unicode
        :return: the loaded Image()
        :rtype: Image
        """
        jdata = json.loads(us)
        return cls(**jdata)
