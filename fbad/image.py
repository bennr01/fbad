"""this module defines the Image class which defines build options for an image."""
import os
import json
import subprocess

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
    """
    def __init__(
        self,
        path,
        name=None,
        tag=None,
        dockerfile="Dockerfile",
        buildpath=None,
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
        command = ["docker", "build", "-t", self.tag, "-f", df, "."]
        if protocolfactory is None:
            c = subprocess.call(command, cwd=bp)
            return defer.succeed(c)
        else:
            protocol = protocolfactory()
            d = protocol.d
            reactor.spawnProcess(protocol, constants.DOCKER_EXECUTABLE, args=command, path=bp)
            return d

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
