import pytest
import requests_mock
import yaml

import update_config


@pytest.mark.parametrize(
    "data",
    [
       ("""
        VM.Standard2.1:
          1: 1
          2: 1
          3: 1
        VM.Standard2.2:
          1: 1
          2: 1
          3: 1
        """),
    ]
)
def test_get_limits(mocker, data):
    mocker.patch("update_config.load_yaml", return_value=yaml.safe_load(data))
    assert isinstance(update_config.get_limits(), dict)


@pytest.mark.parametrize(
    "data,error",
    [
       ("""
        VM.Standard2.1:
        1: 1
        2: 1
        3: 1
        VM.Standard2.2:
        1: 1
        2: 1
        3: 1
        """,
        SyntaxError),
    ]
)
def test_get_limits_errors(mocker, data, error):
    mocker.patch("update_config.load_yaml", return_value=yaml.safe_load(data))
    with pytest.raises(error):
        update_config.get_limits()
