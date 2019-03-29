import oci

import citc_oci

# TODO mock using requests.Session.request http://docs.python-requests.org/en/master/api/#requests.Session.request


def test_get_subnet(mocker):
    VirtualNetworkClient = mocker.Mock(spec=oci.core.VirtualNetworkClient)

    subnet1_id = "ocid0..subnet1"
    subnet2_id = "ocid0..subnet2"
    subnet3_id = "ocid0..subnet3"

    subnets = [
        oci.core.models.Subnet(id=subnet1_id, display_name="SubnetAD1"),
        oci.core.models.Subnet(id=subnet2_id, display_name="SubnetAD2"),
        oci.core.models.Subnet(id=subnet3_id, display_name="SubnetAD3"),
    ]
    r = oci.response.Response(status=200, headers=None, data=subnets, request=None)
    VirtualNetworkClient(oci.config.from_file()).list_subnets.return_value = r
    mocker.patch("oci.core.VirtualNetworkClient", VirtualNetworkClient)

    assert citc_oci.get_subnet(None, None, None, "1") == subnet1_id
    assert citc_oci.get_subnet(None, None, None, "2") == subnet2_id
    assert citc_oci.get_subnet(None, None, None, "3") == subnet3_id


def test_get_node_state(mocker):
    ComputeClient = mocker.Mock(spec=oci.core.ComputeClient)
    instances = [
    ]
    r = oci.response.Response(status=200, headers=None, data=instances, request=None)
    ComputeClient(oci.config.from_file()).list_instances.return_value = r
    mocker.patch("oci.core.ComputeClient", ComputeClient)

    #assert citc_oci.get_node_state(None, None, None, "1") == subnet1_id
