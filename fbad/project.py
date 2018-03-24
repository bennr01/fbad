"""this module defines the Project class which is the main interface for each project."""
import os
import shutil
import zipfile
import tempfile
import contextlib
import json
import uuid
import argparse
import sys

from twisted.internet import reactor, endpoints, task, defer, threads
from twisted.python import log

from fbad import constants, client
from fbad.image import Image

try:
    import __main__
except ImportError:
    __main__ = None


class Project(object):
    """
    This class represents a project.
    :param name: name of the project
    :type name: str or unicode
    :param images: list of Images the project contains.
    :type images: list of Image()
    """
    def __init__(
        self,
        name,
        images=[],
        ):
            self.name = name
            self.images = images
            self._project_path = None

    @property
    def images(self):
        """A list containing all images for the project"""
        return self._images

    @images.setter
    def images(self, value):
        if not isinstance(value, list):
            raise ValueError("Expected list!")
        for element in value:
            if not isinstance(element, Image):
                raise ValueError("image list contains non-image value")
        self._images = value

    @property
    def project_path(self):
        """the path of the project."""
        if self._project_path is None:
            if __main__ is None:
                raise Exception("Could not detect project path. Please set project_path manually.")
            else:
                mp = __main__.__file__
                p = os.path.dirname(mp)
                if p == "":
                    return os.path.abspath(".")
                return p
        else:
            return self._project_path

    @project_path.setter
    def project_path(self, value):
        self._project_path = None

    def create_zip(self, dest):
        """
        Collect all files of the project and write them to a zip stored at dest.
        :param dest: path to write to
        :type dest: str or unicode
        """
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            self._rec_zip_write(zf, self.project_path)

    def _rec_zip_write(self, zf, path, relpath=""):
        """
        Write the content of path to zf.
        :param zf: zipfile to write to
        :type zf: zipfile.ZipFile
        :param path: path to write
        :type path: str or unicode
        :param relpath: path inside the zipfile
        :type relpath: str or unicode
        """
        for fn in os.listdir(path):
            lp = os.path.join(path, fn)
            zp = os.path.join(relpath, fn)
            if os.path.isdir(lp):
                self._rec_zip_write(zf, lp, zp)
            else:
                zf.write(lp, zp)

    @defer.inlineCallbacks
    def build_from_zip(self, zf, protocolfactory=None):
        """
        Build the project from a zipfile.
        :param zf: zipfile to build from
        :type zf: ZipFile
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the project was built
        :rtype: Deferred
        """
        exitcodes = []
        with self.get_temp_build_dir() as tbp:
            zf.extractall(tbp)
            for image in self.images:
                ec = yield image.build(tbp, protocolfactory=protocolfactory)
                exitcodes.append(ec)
        defer.returnValue(exitcodes)

    @defer.inlineCallbacks
    def build_from_zip_path(self, path, protocolfactory=None):
        """
        Build the project from a zipfile at path.
        :param path: path to zipfile to build from
        :type path: str or unicode
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the project was built
        :rtype: Deferred
        """
        with zipfile.ZipFile(path, "r", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            res = yield self.build_from_zip(zf, protocolfactory=protocolfactory)
        defer.returnValue(res)

    def get_temp_build_dir_path(self):
        """
        Return a path to a temporary build directory.
        :return: path to a temporary dir
        :rtype: str
        """
        return os.path.join(
            tempfile.gettempdir(),
            constants.TEMP_DIR_NAME,
            uuid.uuid4().hex,
            )

    @contextlib.contextmanager
    def get_temp_build_dir(self):
        """
        A contextmanager for working with a temporary build directory.
        The directory will be created before the body of the 'with'-statement
        is executed and will be removed when the body is left.
        """
        tp = self.get_temp_build_dir_path()
        os.makedirs(tp)
        try:
            yield tp
        finally:
            shutil.rmtree(tp)

    def dumps(self):
        """
        Return a serialized version of this Project() instance.
        :return: the serialized data
        :rtype: str
        """
        imd = [i.dumpus() for i in self._images]
        jdata = {
            "name": self.name,
            "images": imd,
            }
        return json.dumps(jdata).encode(constants.ENCODING)

    @classmethod
    def loads(cls, s):
        """
        Load a Project() from a string returned by dumps()
        :param s: string to load from
        :type s: str
        :return: the loaded Project()
        :rtype: Project
        """
        jdata = json.loads(s)
        jdata["images"] = [Image.loadus(us) for us in jdata["images"]]
        return cls(**jdata)

    def main(self):
        """
        Parse command line arguments and behave according to them.
        """
        parser = argparse.ArgumentParser(description="Build script for this project")
        parser.add_argument("-v", "--verbose", help="be more verbose", action="store_true")
        subparsers = parser.add_subparsers(dest="command", help="subcommand to execute")


        parser_build = subparsers.add_parser("build", help="build this project")
        parser_build.add_argument("-s", "--buildserver", action="store", help="build project on target server", default=None)
        parser_build.add_argument("-p", "--port", action="store", type=int, help="Connect to this port.", default=constants.DEFAULT_PORT)
        parser_build.add_argument("-P", "--password", action="store", help="password for the buildserver", default=None)

        ns = parser.parse_args()

        if ns.verbose:
            log.startLogging(sys.stdout)

        if ns.command == "build":
            if ns.buildserver is None:
                from fbad import server  # import here so server can import project
                host = "localhost"
                factory = server.FBADServerFactory(ns.password)
                ep = endpoints.TCP4ServerEndpoint(reactor, port=ns.port, interface="localhost")
                ep.listen(factory)
            else:
                host = ns.buildserver
                factory = None
            d = defer.Deferred()
            proto = client.FBADClientProtocol(password=ns.password, d=d, out=sys.stdout)
            ep = endpoints.TCP4ClientEndpoint(reactor, host, ns.port)
            endpoints.connectProtocol(ep, proto)
            task.react(_run_remote_build, (ns, self, d))


@defer.inlineCallbacks
def _run_remote_build(reactor, ns, project, d):
    """
    Run a remote build.
    :param reactor: the twisted reactor
    :param reactor: IReactor
    :param ns: namespace from argument parser
    :type ns: Namespace
    :param project: the project to build
    :type project: Project
    :param d: deferred which will fire with the connected FBADClientProtocol
    :type d: Deferred
    :return: a deferred which will fire once the remote build finished.
    :rtype: Deferred
    """
    client = yield d
    with project.get_temp_build_dir() as p:
        uzp = os.path.join(p, "up.zip")
        yield threads.deferToThread(project.create_zip, uzp)
        exitcodes = yield client.remote_build(project, uzp)
    yield client.disconnect()
    if len(exitcodes) == 0:
        print "Error: no images built!"
        sys.exit(1)
    else:
        print "Exitcodes: " + repr(exitcodes)
        sys.exit(max(exitcodes))
