import json
import oci
import pytest
from collections import namedtuple

import citc_oci

Response = namedtuple("Response", ["status_code", "content", "headers"])




@pytest.fixture
def oci_config(tmp_path):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    config = {
        "user": "ocid1.user.oc1..aaaaa",
        "key_file": "/tmp/foo",
        "fingerprint": "6e:b9:17:06:13:37:b8:5e:b2:72:48:53:9e:3e:6b:01",
        "tenancy": "ocid1.user.oc1..aaaaa",
        "region": "here",
    }

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    kf = tmp_path / config["key_file"]
    kf.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

    return config


def serialize(data):
    if isinstance(data, list):
        return [serialize(d) for d in data]

    return {data.attribute_map[attr]: getattr(data, attr, None) for attr in data.swagger_types}


def test_get_subnet(mocker, oci_config):
    request = mocker.patch("oci._vendor.requests.Session.request")

    subnet1_id = "ocid0..subnet1"
    subnet2_id = "ocid0..subnet2"
    subnet3_id = "ocid0..subnet3"

    data = [
        oci.core.models.Subnet(id=subnet1_id, display_name="SubnetAD1"),
        oci.core.models.Subnet(id=subnet2_id, display_name="SubnetAD2"),
        oci.core.models.Subnet(id=subnet3_id, display_name="SubnetAD3"),
        oci.core.models.Subnet(id="blah", display_name="Subnet3"),
        oci.core.models.Subnet(id="blah", display_name="SubnetAD3X"),
    ]

    request.return_value = Response(
        200,
        json.dumps(serialize(data)).encode(),
        {},
    )

    assert citc_oci.get_subnet(oci_config, "", "", "1") == subnet1_id
    assert citc_oci.get_subnet(oci_config, "", "", "2") == subnet2_id
    assert citc_oci.get_subnet(oci_config, "", "", "3") == subnet3_id


@pytest.mark.parametrize("states,expected", [
    (["TERMINATED", "RUNNING", "TERMINATED"], "RUNNING"),
    (["TERMINATED"], "TERMINATED"),
    ([], "TERMINATED"),
])
def test_get_node_state(states, expected, mocker, oci_config):
    request = mocker.patch("oci._vendor.requests.Session.request")

    data = [
        oci.core.models.Instance(lifecycle_state=state) for state in states
    ]

    request.return_value = Response(
        200,
        json.dumps(serialize(data)).encode(),
        {},
    )

    assert citc_oci.get_node_state(oci_config, mocker.Mock(), "ocid0..compartment", "foo") == expected
