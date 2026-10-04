from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import pytest
from make_examples import base_case, write_case

@pytest.fixture
def bundle(tmp_path):
    case, data = base_case()
    write_case(tmp_path, case, data)
    return tmp_path, case, data
