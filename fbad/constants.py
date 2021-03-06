"""various constants"""
import struct
import subprocess

ENCODING = "UTF-8"

TEMP_DIR_NAME = "fbad_build"

DEFAULT_PORT = 28847
MESSAGE_LENGTH_PREFIX = "!I"
MESSAGE_LENGTH_PREFIX_LENGTH = struct.calcsize(MESSAGE_LENGTH_PREFIX)
MAX_MESSAGE_LENGTH = 130 * 1024  # 130 KB
COM_VERSION = "0.2"

AUTH_SEED_LENGTH = 16

MESSAGE_PREFIX_CONTINUE = "\x00"
MESSAGE_PREFIX_END = "\x01"

READ_CHUNK_SIZE = 8192

try:
    DOCKER_EXECUTABLE = subprocess.check_output(["which", "docker"])[:-1]
except:
    DOCKER_EXCUTABLE = "/usr/bin/docker"

try:
    DOCKER_COMPOSE_EXECUTABLE = subprocess.check_output(["which", "docker-compose"])[:-1]
except:
    DOCKER_COMPOSE_EXECUTABLE = "/usr/bin/docker-compose"
