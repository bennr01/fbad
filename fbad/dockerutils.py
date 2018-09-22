"""utilities for interacting with docker."""
import subprocess


def in_swarm():
    """
    Check whether docker is running in swarm mode.
    :return: True when running in swarm mode, False otherwise.
    :rtype: bool
    """
    output = subprocess.check_output(["docker", "info"])
    swarm_enabled = ("Swarm: active" in output)
    return swarm_enabled

