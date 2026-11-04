import importlib
import socket

import httpx
import pytest
from pytest_socket import SocketBlockedError

SUBPACKAGES = ["sources", "llm", "store", "report", "ui", "stages"]
DEPENDENCIES = ["pydantic", "httpx", "yaml", "pypdf"]


@pytest.mark.parametrize("name", ["job_radar", *(f"job_radar.{p}" for p in SUBPACKAGES)])
def test_package_imports(name):
    importlib.import_module(name)


@pytest.mark.parametrize("name", DEPENDENCIES)
def test_dependency_imports(name):
    importlib.import_module(name)


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_tests_run_offline():
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(SocketBlockedError):
        httpx.get("https://example.com")
