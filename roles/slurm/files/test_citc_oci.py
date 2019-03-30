from collections import namedtuple
import json
import subprocess

import oci
import pytest
import requests_mock

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
        "tenancy": "ocid1.tenancy.oc1..aaaaa",
        "region": "here",
    }

    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    kf = tmp_path / config["key_file"]
    kf.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return config


@pytest.fixture
def requests_mocker(mocker):
    adapter = requests_mock.Adapter()
    mocker.patch("oci._vendor.requests.Session.get_adapter", return_value=adapter)
    return adapter


def serialize(data):
    """
    Turn any OCI model into its JSON equivalent
    """
    if isinstance(data, list):
        return [serialize(d) for d in data]

    return {
        data.attribute_map[attr]: getattr(data, attr, None)
        for attr in data.swagger_types
    }


def test_get_subnet(requests_mocker, oci_config):
    subnet1_id = "ocid0..subnet1"
    subnet2_id = "ocid0..subnet2"
    subnet3_id = "ocid0..subnet3"

    data = [
        oci.core.models.Subnet(id="blah", display_name="Subnet3"),
        oci.core.models.Subnet(id="blah", display_name="SubnetAD3X"),
        oci.core.models.Subnet(id=subnet1_id, display_name="SubnetAD1"),
        oci.core.models.Subnet(id=subnet2_id, display_name="SubnetAD2"),
        oci.core.models.Subnet(id=subnet3_id, display_name="SubnetAD3"),
    ]

    requests_mocker.register_uri(
        "GET",
        "/20160918/subnets?compartmentId=&vcnId=",
        text=json.dumps(serialize(data)),
    )

    assert citc_oci.get_subnet(oci_config, "", "", "1") == subnet1_id
    assert citc_oci.get_subnet(oci_config, "", "", "2") == subnet2_id
    assert citc_oci.get_subnet(oci_config, "", "", "3") == subnet3_id


@pytest.mark.parametrize(
    "states,expected",
    [
        (["TERMINATED", "RUNNING", "TERMINATED"], "RUNNING"),
        (["TERMINATED"], "TERMINATED"),
        ([], "TERMINATED"),
    ],
)
def test_get_node_state(states, expected, mocker, requests_mocker, oci_config):
    data = [oci.core.models.Instance(lifecycle_state=state) for state in states]
    requests_mocker.register_uri(
        "GET",
        "/20160918/instances/?compartmentId=ocid0..compartment&displayName=foo",
        text=json.dumps(serialize(data)),
    )

    assert (
        citc_oci.get_node_state(oci_config, mocker.Mock(), "ocid0..compartment", "foo")
        == expected
    )


def test_create_node_config(mocker, requests_mocker, oci_config):
    subnets = [oci.core.models.Subnet(id="ocid0..subnet1", display_name="SubnetAD1")]
    requests_mocker.register_uri(
        "GET",
        "/20160918/subnets?compartmentId=&vcnId=",
        text=json.dumps(serialize(subnets)),
    )

    mocker.patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="", returncode=0, stdout=b"ad=1,shape=shapeA"
        ),
    )
    mocker.patch("citc_oci.open", mocker.mock_open(read_data=b"#! /bin/bash"))

    nodespace = {
        "ad_root": "HERE-AD-",
        "compartment_id": "ocid1.compartment.oc1..aaaaa",
        "vcn_id": "ocid1.vcn.oc1..aaaaa",
        "region": "uk-london-1",
    }

    node_config = citc_oci.create_node_config(oci_config, "foo1", None, nodespace, "")

    assert node_config.subnet_id == "ocid0..subnet1"
    assert node_config.availability_domain == "HERE-AD-1"
    assert node_config.shape == "shapeA"
