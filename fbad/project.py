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
    def build_from_zip(self, zf, protocolfactory=None, only=None):
        """
        Build the project from a zipfile.
        :param zf: zipfile to build from
        :type zf: ZipFile
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :param only: which images to built, specified by their name
        :type only: str or unicode or None
        :return: a deferred which will fire when the project was built
        :rtype: Deferred
        """
        exitcodes = []
        with self.get_temp_build_dir() as tbp:
            zf.extractall(tbp)
            for image in self.images:

                if only is not None:
                    if image.name not in only:
                        # skip image
                        continue

                ec = yield image.build(tbp, protocolfactory=protocolfactory)
                exitcodes.append(ec)

        defer.returnValue(exitcodes)

    @defer.inlineCallbacks
    def build_from_zip_path(self, path, protocolfactory=None, only=None):
        """
        Build the project from a zipfile at path.
        :param path: path to zipfile to build from
        :type path: str or unicode
        :param protocolfactory: a callable which returns a protocol to communicate with the child process
        :type protocolfactory: callable
        :param only: which images to built, specified by their name
        :type only: str or unicode or None
        :return: a deferred which will fire when the project was built
        :rtype: Deferred
        """
        with zipfile.ZipFile(path, "r", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            res = yield self.build_from_zip(zf, protocolfactory=protocolfactory, only=only)
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

    @defer.inlineCallbacks
    def push(self, only=None, protocolfactory=None):
        """
        Push all Images to a docker registry.
        If only is not None, only push images whose name is in only.
        :param only: names of images to push
        :type only: list or None
        :param protocolfactory: a callable which returns a protocol to communicate with the push child process
        :type protocolfactory: callable
        :return: a deferred which will fire when the command executed successfully
        :rtype: Deferred
        """
        for image in self.images:
            if only is not None:
                if image.name not in only:
                    # skip image
                    continue
            yield image.push(protocolfactory=protocolfactory)

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
        parser_build.add_argument("-s", "--buildserver", action="append", help="build project on target server. Mulitple servers may be specified.", default=None)
        parser_build.add_argument("-m", "--buildmode", action="store", choices=("parallel", "multi"), default="parallel", help="How to build images if more then one buildserver is specified")
        parser_build.add_argument("-p", "--port", action="store", type=int, help="Connect to this port.", default=constants.DEFAULT_PORT)
        parser_build.add_argument("-P", "--password", action="store", help="password for the buildserver", default=None)
        parser_build.add_argument("-o", "--only", action="store", help="only build images with this name", default=None)
        parser_build.add_argument("--push", action="store_true", dest="do_push", help="push built images to registry")

        ns = parser.parse_args()

        if ns.verbose:
            log.startLogging(sys.stdout)

        if ns.command == "build":
            if ns.buildserver is None:
                from fbad import server  # import here so server can import project
                hosts = ["localhost"]
                factory = server.FBADServerFactory(ns.password)
                ep = endpoints.TCP4ServerEndpoint(reactor, port=ns.port, interface="localhost")
                ep.listen(factory)
            else:
                hosts = ns.buildserver
                factory = None

            if ns.only is None:
                only = None
            elif isinstance(ns.only, list):
                if len(list) == 0:
                    only = None
                else:
                    only = ns.only
            elif isinstance(ns.only, (str, unicode)):
                only = [ns.only]
            else:
                only = None

            if len(hosts) == 1:
                host = hosts[0]
                task.react(_run_single_build, (host, ns.port, self, only, sys.stdout, ns.password, ns.do_push))
            if ns.buildmode == "multi":
                task.react(_run_multi_build, (hosts, ns.port, self, only, sys.stdout, ns.password, ns.do_push))
            elif ns.buildmode == "parallel":
                task.react(_run_parallel_build, (hosts, ns.port, self, only, sys.stdout, ns.password, ns.do_push))


@defer.inlineCallbacks
def _run_single_build(reactor, host, port, project, only, out, password=None, push=False, noexit=False):
    """
    Run a remote build with a single buildserver.
    :param reactor: the twisted reactor
    :type reactor: IReactor
    :param host: host of the buildserver
    :type host: str
    :param port: port of the buildserver
    :type port: int
    :param only: which images to build
    :type only: list or None
    :param project: the project to build
    :type project: Project
    :param out: file to write output to
    :type out: file-like object
    :param password: password for the buildserver
    :type password: str
    :param push: whether to push built images to registry or not
    :type push: bool
    :param noexit: skip script exit
    :type noexit: boolean
    :return: a deferred which will fire with the exit codes.
    :rtype: Deferred
    """
    d = defer.Deferred()
    proto = client.FBADClientProtocol(password=password, d=d, out=out)
    ep = endpoints.TCP4ClientEndpoint(reactor, host, port)
    endpoints.connectProtocol(ep, proto)
    exitcodes = yield _run_remote_build(reactor, project, only, d, out=out, push=push)


    if noexit:
        defer.returnValue(exitcodes)

    if len(exitcodes) == 0:
        print "Error: no images built!"
        sys.exit(1)
    else:
        print "Exitcodes: " + repr(exitcodes)
        sys.exit(max(exitcodes))


@defer.inlineCallbacks
def _run_multi_build(reactor, hosts, port, project, only, out, password=None, push=False):
    """
    Run a remote build with on each buildserver.
    :param reactor: the twisted reactor
    :type reactor: IReactor
    :param hosts: hosts of the buildservers
    :type hosts: list of str
    :param port: port of the buildservers
    :type port: int
    :param only: which images to build
    :type only: list or None
    :param project: the project to build
    :type project: Project
    :param out: file to write output to
    :type out: file-like object
    :param password: password for the buildservers
    :type password: str
    :param push: whether to push built images to registry or not
    :type push: bool
    :return: a deferred which will fire with the exit codes.
    :rtype: Deferred
    """
    ds = []
    for host in hosts:
        d = _run_single_build(reactor, host, port, project, only=only, out=out, password=password, push=push, noexit=True)
        ds.append(d)
    exitcodeslists = yield defer.gatherResults(ds)
    exitcodes = []
    for ecl in exitcodeslists:
        exitcodes += ecl

    if len(exitcodes) == 0:
        print "Error: no images built!"
        sys.exit(1)
    else:
        print "Exitcodes: " + repr(exitcodes)
        sys.exit(max(exitcodes))


@defer.inlineCallbacks
def _run_parallel_build(reactor, hosts, port, project, only, out, password=None, push=False):
    """
    Run a remote build distributed between multiple buildservers.
    :param reactor: the twisted reactor
    :type reactor: IReactor
    :param hosts: hosts of the buildservers
    :type hosts: list of str
    :param port: port of the buildservers
    :type port: int
    :param only: which images to build
    :type only: list or None
    :param project: the project to build
    :type project: Project
    :param out: file to write output to
    :type out: file-like object
    :param password: password for the buildservers
    :type password: str
    :param push: whether to push built images to registry or not
    :type push: bool
    :return: a deferred which will fire with the exit codes.
    :rtype: Deferred
    """
    if only is None:
        names = [image.name for image in project.images]
    else:
        names = only
    ds = []
    i = 0
    while len(names) > 0:
        name = names.pop(0)
        host = hosts[i]
        i += 1
        if i >= len(hosts):
            i = 0
        d = _run_single_build(reactor, host, port, project, only=[name], out=out, password=password, push=push, noexit=True)
        ds.append(d)

    exitcodeslists = yield defer.gatherResults(ds)
    exitcodes = []
    for ecl in exitcodeslists:
        exitcodes += ecl

    if len(exitcodes) == 0:
        print "Error: no images built!"
        sys.exit(1)
    else:
        print "Exitcodes: " + repr(exitcodes)
        sys.exit(max(exitcodes))


@defer.inlineCallbacks
def _run_remote_build(reactor, project, only, d, out, push=False):
    """
    Run a remote build.
    :param reactor: the twisted reactor
    :type reactor: IReactor
    :param only: which images to build
    :type only: list or None
    :param project: the project to build
    :type project: Project
    :param d: deferred which will fire with the connected FBADClientProtocol
    :type d: Deferred
    :param out: file to write output to
    :type out: file-like object
    :param push: whether to push built images to registry or not
    :type push: bool
    :return: a deferred which will fire with the exit codes.
    :rtype: Deferred
    """
    client = yield d
    with project.get_temp_build_dir() as p:
        uzp = os.path.join(p, "up.zip")
        yield threads.deferToThread(project.create_zip, uzp)
        exitcodes = yield client.remote_build(project, uzp, only=only, push=push)
    yield client.disconnect()
    defer.returnValue(exitcodes)
