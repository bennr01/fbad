"""shell and subprocess utilities."""
from twisted.internet import reactor


def run_command(path, executable, command, protocolfactory=None):
    """
    Run a command.
    If protocolfactory is not None, use it for subprocess communication.
    Otherwise, use subprocess.
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
