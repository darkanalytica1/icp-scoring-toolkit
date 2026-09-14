import json
import os

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "icp_example.json")


@pytest.fixture(scope="session")
def config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
