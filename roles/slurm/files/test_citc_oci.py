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


@pytest.fixture
def nodespace():
    return {
        "ad_root": "HERE-AD-",
        "compartment_id": "ocid1.compartment.oc1..aaaaa",
        "vcn_id": "ocid1.vcn.oc1..aaaaa",
        "region": "uk-london-1",
    }


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
    subnet_id = "ocid0..subnet"

    data = [
        oci.core.models.Subnet(id="blah", display_name="Subnetblah"),
        oci.core.models.Subnet(id="blah", display_name="Subnetfoo"),
        oci.core.models.Subnet(id=subnet_id, display_name="Subnet"),
    ]

    requests_mocker.register_uri(
        "GET",
        "/20160918/subnets?compartmentId=&vcnId=",
        text=json.dumps(serialize(data)),
    )

    assert citc_oci.get_subnet(oci_config, "", "") == subnet_id


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
        "/20160918/instances?compartmentId=ocid0..compartment&displayName=foo",
        text=json.dumps(serialize(data)),
    )

    assert (
        citc_oci.get_node_state(oci_config, mocker.Mock(), "ocid0..compartment", "foo")
        == expected
    )


def test_create_node_config(mocker, requests_mocker, oci_config, nodespace):
    subnets = [oci.core.models.Subnet(id="ocid0..subnet", display_name="Subnet")]
    requests_mocker.register_uri(
        "GET",
        "/20160918/subnets?compartmentId=ocid1.compartment.oc1..aaaaa&vcnId=ocid1.vcn.oc1..aaaaa",
        text=json.dumps(serialize(subnets)),
    )

    mocker.patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="", returncode=0, stdout=b"ad=1,shape=shapeA"
        ),
    )
    mocker.patch("citc_oci.open", mocker.mock_open(read_data=b"#! /bin/bash"))

    node_config = citc_oci.create_node_config(oci_config, "foo1", None, nodespace, "")

    assert node_config.subnet_id == "ocid0..subnet"
    assert node_config.availability_domain == "HERE-AD-1"
    assert node_config.shape == "shapeA"


@pytest.mark.parametrize(
    "host_good,scontrol_good,expected",
    [
        (True, True, ("10.1.0.2", "10.1.0.2", "10.1.0.2")),
        (True, False, ("10.1.0.2", "10.1.0.2", None)),
        (False, True, ("10.1.0.2", None, "10.1.0.2")),
        (False, False, (None, None, None)),
    ],
)
def test_get_ip(host_good, scontrol_good, expected, mocker):
    host_ret_good = b"foo has address 10.1.0.2"
    host_ret_bad = b"Host foo not found: 3(NXDOMAIN)"
    scontrol_ret_good = b"""NodeName=foo Arch=x86_64 CoresPerSocket=1
        CPUAlloc=0 CPUErr=0 CPUTot=2 CPULoad=0.00
        AvailableFeatures=shape=shapeA,ad=1
        ActiveFeatures=shape=shapeA,ad=1
        Gres=(null)
        NodeAddr=10.1.0.2 NodeHostName=foo Port=0 Version=17.11
        OS=Linux 4.14.35-1844.2.5.el7uek.x86_64 #2 SMP Mon Feb 4 18:24:45 PST 2019"""
    scontrol_ret_bad = b"Node foo not found"

    def run_mock(args, stdout):
        if args[0] == "host":
            if host_good:
                return subprocess.CompletedProcess(
                    args="", returncode=0, stdout=host_ret_good
                )
            else:
                return subprocess.CompletedProcess(
                    args="", returncode=1, stdout=host_ret_bad
                )
        if args[0] == "scontrol":
            if scontrol_good:
                return subprocess.CompletedProcess(
                    args="", returncode=0, stdout=scontrol_ret_good
                )
            else:
                return subprocess.CompletedProcess(
                    args="", returncode=1, stdout=scontrol_ret_bad
                )

    mocker.patch("subprocess.run", side_effect=run_mock)

    assert citc_oci.get_ip("foo") == expected


@pytest.mark.asyncio
async def test_start_node_fresh(oci_config, mocker, requests_mocker, nodespace):
    mocker.patch("oci.config.from_file", return_value=oci_config)

    requests_mocker.register_uri(
        "GET",
        "/20160918/instances?compartmentId=ocid1.compartment.oc1..aaaaa&displayName=foo",
        text=json.dumps(serialize([])),
    )

    mocker.patch("citc_oci.get_ip", return_value=(None, None, None))

    mocker.patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="", returncode=0, stdout=b"ad=1,shape=shapeA"
        ),
    )
    mocker.patch("citc_oci.open", mocker.mock_open(read_data=b"#! /bin/bash"))

    mocker.patch("citc_oci.get_subnet", return_value="ocid0..subnet1")

    new_instance_response = oci.core.models.Instance(id="ocid0..instance.foo")
    requests_mocker.register_uri(
        "POST",
        "/20160918/instances",
        text=json.dumps(serialize(new_instance_response)),
    )

    vnic_attachments = [oci.core.models.VnicAttachment(vnic_id="ocid0..vnic")]
    requests_mocker.register_uri(
        "GET",
        "/20160918/vnicAttachments?compartmentId=ocid1.compartment.oc1..aaaaa&instanceId=ocid0..instance.foo",
        text=json.dumps(serialize(vnic_attachments)),
    )

    vnic = oci.core.models.Vnic(private_ip="10.0.1.2")
    requests_mocker.register_uri(
        "GET",
        "/20160918/vnics/ocid0..vnic",
        text=json.dumps(serialize(vnic)),
    )

    instance = await citc_oci.start_node(mocker.Mock(), "foo", nodespace, "")

    assert instance.id == "ocid0..instance.foo"
