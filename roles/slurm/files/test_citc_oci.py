import oci

import citc_oci


def test_get_subnet(mocker):
    VirtualNetworkClient = mocker.Mock(spec=oci.core.VirtualNetworkClient)

    subnet_id = "ocid0..subnet1"

    subnets = [
        oci.core.models.Subnet(id=subnet_id, display_name="SubnetAD1"),
        oci.core.models.Subnet(id="ocid0..subnet2", display_name="SubnetAD2"),
        oci.core.models.Subnet(id="ocid0..subnet3", display_name="SubnetAD3"),
    ]
    r = oci.response.Response(status=200, headers=None, data=subnets, request=None)
    VirtualNetworkClient(oci.config.from_file()).list_subnets.return_value = r
    mocker.patch("oci.core.VirtualNetworkClient", VirtualNetworkClient)

    assert citc_oci.get_subnet(None, None, None, "1") == subnet_id
