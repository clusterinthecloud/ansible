import httplib2
import json
import subprocess
from urllib.parse import urlparse

from google.auth.credentials import Credentials
import pytest
import requests_mock

import citc_gcp


@pytest.fixture
def gcp_config(tmp_path):
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    config = {
        "client_email": "foo@example.com",
        "token_uri": "http://foo",
    }

    key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )

    config["private_key"] = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
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
        "zone": "europe-west4-a",
        "compartment_id": "myproj-123456",
        "subnet": "regions/europe-west4/subnetworks/citc-subnet",
    }


@pytest.mark.asyncio
async def test_start_node_fresh(gcp_config, mocker, requests_mocker, nodespace):

    class MockCredentials(Credentials):
        def refresh(self, request):
            pass

        def before_request(self, request, method, url, headers):
            pass
    mocker.patch("citc_gcp.get_credentials", return_value=MockCredentials())

    # TODO: Use googleapiclient.http.HttpMock or similar?
    def request_mock(http, num_retries, req_type, sleep, rand, uri, method, *args, **kwargs):
        url = urlparse(uri)
        if url.path == "/compute/v1/projects/myproj-123456/zones/europe-west4-a/instances" and url.query == "filter=%28name%3Dfoo%29&alt=json" and method == "GET":
            return httplib2.Response({'status': 200, 'reason': 'OK'}), json.dumps({})
        if url.path == "/compute/v1/projects/gce-uefi-images/global/images/family/centos-7" and url.query == "alt=json" and method == "GET":
            return httplib2.Response({'status': 200, 'reason': 'OK'}), json.dumps({"selfLink": "foo"})
        if url.path == "/compute/v1/projects/myproj-123456/zones/europe-west4-a/instances" and method == "POST":
            return httplib2.Response({'status': 200, 'reason': 'OK'}), json.dumps({"id": "id-foo"})

    mocker.patch("googleapiclient.http._retry_request", side_effect=request_mock)

    mocker.patch("citc_gcp.get_ip", return_value=(None, None, "0.0.0.0"))

    mocker.patch(
        "subprocess.run",
        return_value=subprocess.CompletedProcess(
            args="", returncode=0, stdout=b"shape=shapeA"
        ),
    )

    mocker.patch("citc_gcp.open", mocker.mock_open(read_data=b"#! /bin/bash"))

    instance = await citc_gcp.start_node(mocker.Mock(), "foo", nodespace, "")

    assert instance["id"] == "id-foo"
