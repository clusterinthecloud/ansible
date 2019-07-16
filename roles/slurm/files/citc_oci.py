import asyncio
import base64
import re
import subprocess
import time
from typing import Dict, Optional, Tuple

import oci  # type: ignore
import yaml

__all__ = ["get_nodespace", "start_node"]


def load_yaml(filename: str) -> dict:
    with open(filename, "r") as f:
        return yaml.safe_load(f)


def get_nodespace() -> Dict[str, str]:
    """
    Get the information about the space into which we were creating nodes
    This will be static for all nodes in this cluster
    """
    return load_yaml("/etc/citc/startnode.yaml")


def get_subnet(oci_config, compartment_id: str, vcn_id: str, ad_number: str) -> str:
    """
    Get the relevant cluster subnet for a given compartment, VCN and AD
    """
    return [s.id for s in oci.core.VirtualNetworkClient(oci_config).list_subnets(compartment_id, vcn_id=vcn_id).data if s.display_name == f"SubnetAD{ad_number}"][0]

def get_node_state(oci_config, log, compartment_id: str, hostname: str) -> str:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """
    matches = oci.core.ComputeClient(oci_config).list_instances(compartment_id=compartment_id, display_name=hostname).data
    still_exist = [i for i in matches if i.lifecycle_state != "TERMINATED"]
    if not still_exist:
        return "TERMINATED"
    if len(still_exist) > 1:
        log.error(f"{hostname}: Multiple matches found for {hostname}")
    return still_exist[0].lifecycle_state


def create_node_config(oci_config, hostname: str, ip: Optional[str], nodespace: Dict[str, str], ssh_keys: str) -> oci.core.models.LaunchInstanceDetails:
    """
    Create the configuration needed to create ``hostname`` in ``nodespace`` with ``ssh_keys``
    """
    features = subprocess.run(["sinfo", "--Format=features:200", "--noheader", f"--nodes={hostname}"], stdout=subprocess.PIPE).stdout.decode().split(',')
    ad_number = [f for f in features if f.startswith("ad=")][0].split("=")[1].strip()
    ad = f"{nodespace['ad_root']}{ad_number}"
    shape = [f for f in features if f.startswith("shape=")][0].split("=")[1].strip()
    subnet = get_subnet(oci_config, nodespace["compartment_id"], nodespace["vcn_id"], ad_number)
    image_name = "Oracle-Linux-7.6-Gen2-GPU-2019.02.20-0" if "GPU" in shape else "Oracle-Linux-7.6-2019.02.20-0"
    image = get_images()[image_name][nodespace["region"]]

    with open("/home/slurm/bootstrap.sh", "rb") as f:
        user_data = base64.b64encode(f.read()).decode()

    instance_details = oci.core.models.LaunchInstanceDetails(
        compartment_id=nodespace["compartment_id"],
        availability_domain=ad,
        shape=shape,
        subnet_id=subnet,
        image_id=image,
        display_name=hostname,
        hostname_label=hostname,
        create_vnic_details=oci.core.models.CreateVnicDetails(private_ip=ip, subnet_id=subnet) if ip else None,
        metadata={
            "ssh_authorized_keys": ssh_keys,
            "user_data": user_data,
        }
    )

    return instance_details


def get_ip(hostname: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host_dns_match = re.match(r"(\d+\.){3}\d+", subprocess.run(["host", hostname], stdout=subprocess.PIPE).stdout.decode().split()[-1])
    dns_ip = host_dns_match.group(0) if host_dns_match else None

    slurm_dns_match = re.search(r"NodeAddr=((\d+\.){3}\d+)", subprocess.run(["scontrol", "show", "node", hostname], stdout=subprocess.PIPE).stdout.decode())
    slurm_ip = slurm_dns_match.group(1) if slurm_dns_match else None

    ip = dns_ip or slurm_ip

    return ip, dns_ip, slurm_ip


async def start_node(oci_config, log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    log.info(f"{host}: Starting")

    while get_node_state(oci_config, log, nodespace["compartment_id"], host) == "TERMINATING":
        log.info(f"{host}:  host is currently terminating. Waiting...")
        await asyncio.sleep(5)

    node_state = get_node_state(oci_config, log, nodespace["compartment_id"], host)
    if node_state != "TERMINATED":
        log.warning(f"{host}:  host is already running with state {node_state}")
        return

    ip, _dns_ip, slurm_ip = get_ip(host)

    instance_details = create_node_config(oci_config, host, ip, nodespace, ssh_keys)

    loop = asyncio.get_event_loop()
    retry_strategy_builder = oci.retry.RetryStrategyBuilder()
    retry_strategy_builder.add_max_attempts(max_attempts=10).add_total_elapsed_time(total_elapsed_time_seconds=600)
    retry_strategy = retry_strategy_builder.get_retry_strategy()
    client = oci.core.ComputeClient(oci_config, retry_strategy=retry_strategy)

    try:
        instance_result = await loop.run_in_executor(None, client.launch_instance, instance_details)
        instance = instance_result.data
    except oci.exceptions.ServiceError as e:
        log.error(f"{host}:  problem launching instance: {e}")
        return

    if not slurm_ip:
        node_id = instance.id
        while not oci.core.ComputeClient(oci_config).list_vnic_attachments(instance_details.compartment_id, instance_id=node_id).data:
            log.info(f"{host}:  No VNIC attachment yet. Waiting...")
            await asyncio.sleep(5)

        vnic_id = oci.core.ComputeClient(oci_config).list_vnic_attachments(instance_details.compartment_id, instance_id=node_id).data[0].vnic_id
        private_ip = oci.core.VirtualNetworkClient(oci_config).get_vnic(vnic_id).data.private_ip

        log.info(f"{host}:   Private IP {private_ip}")
        subprocess.run(["scontrol", "update", f"NodeName={host}", f"NodeAddr={private_ip}"])

    log.info(f"{host}:  Started")
    return instance


def get_images() -> Dict[str, Dict[str, str]]:
    """
    From https://docs.cloud.oracle.com/iaas/images/
    """
    return {
        "Oracle-Linux-7.6-Gen2-GPU-2019.02.20-0": {
            "ca-toronto-1": "ocid1.image.oc1.ca-toronto-1.aaaaaaaayeivcqwwqnuo6qkz2fwpmskhcwrlhxgwaibqbhwwkohepnlyxk5q",
            "eu-frankfurt-1": "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaayupoeyifqy7a6gyup3axhtnidjvfptj55e34bzgt7m7bv3gwv3wa",
            "uk-london-1": "ocid1.image.oc1.uk-london-1.aaaaaaaap5kk2lbo5lj3k5ff5tl755a4cszjwd6zii7jlcp6nz3gogh54wtq",
            "us-ashburn-1": "ocid1.image.oc1.iad.aaaaaaaab5l5wv7njknupfxvyynplhsygdz67uhfaz35nsnhsk3ufclqjaea",
            "us-phoenix-1": "ocid1.image.oc1.phx.aaaaaaaahu7hv6lqbdyncgwehipwsuh3htfuxcoxbl4arcetx6hzixft366a",
        },
        "Oracle-Linux-7.6-2019.02.20-0": {
            "ca-toronto-1": "ocid1.image.oc1.ca-toronto-1.aaaaaaaa7ac57wwwhputaufcbf633ojir6scqa4yv6iaqtn3u64wisqd3jjq",
            "eu-frankfurt-1": "ocid1.image.oc1.eu-frankfurt-1.aaaaaaaa527xpybx2azyhcz2oyk6f4lsvokyujajo73zuxnnhcnp7p24pgva",
            "uk-london-1": "ocid1.image.oc1.uk-london-1.aaaaaaaarruepdlahln5fah4lvm7tsf4was3wdx75vfs6vljdke65imbqnhq",
            "us-ashburn-1": "ocid1.image.oc1.iad.aaaaaaaannaquxy7rrbrbngpaqp427mv426rlalgihxwdjrz3fr2iiaxah5a",
            "us-phoenix-1": "ocid1.image.oc1.phx.aaaaaaaacss7qgb6vhojblgcklnmcbchhei6wgqisqmdciu3l4spmroipghq",
            "ap-tokyo-1": "ocid1.image.oc1.ap-tokyo-1.aaaaaaaairi7u3txkamxlw3kmw3dosbesrlm22vsh7yybhygzafd3awhlr5q",
        },
    }
