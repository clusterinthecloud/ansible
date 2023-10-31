import asyncio
import base64
import re
import subprocess
from typing import Dict, Optional, Tuple

import openstack  # type: ignore
import yaml  # type: ignore


def load_yaml(filename: str) -> dict:
    with open(filename, "r") as f:
        return yaml.safe_load(f)


def get_nodespace() -> Dict[str, str]:
    """
    Get the information about the space into which we were creating nodes
    This will be static for all nodes in this cluster
    """
    return load_yaml("/etc/citc/startnode.yaml")


def get_node_state(conn, log, hostname: str, cluster_id: str) -> str:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "DELETED"

    See https://docs.openstack.org/api-guide/compute/server_concepts.html#server-status
    s["metadata"].get("cluster") == nodespace["cluster_id"]
    """
    matches = (s for s in conn.compute.servers(name=hostname, tags=["compute"]))
    matches = (i for i in matches if i["metadata"].get("cluster") == cluster_id)
    still_exist = [i for i in matches if i.status != "DELETED"]
    if not still_exist:
        return "DELETED"
    if len(still_exist) > 1:
        log.error(f"{hostname}: Multiple matches found for {hostname}")
    return still_exist[0].status


def get_ip(hostname: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host_dns_match = re.match(r"(\d+\.){3}\d+", subprocess.run(["host", hostname], stdout=subprocess.PIPE).stdout.decode().split()[-1])
    dns_ip = host_dns_match.group(0) if host_dns_match else None

    slurm_dns_match = re.search(r"NodeAddr=((\d+\.){3}\d+)", subprocess.run(["scontrol", "show", "node", hostname], stdout=subprocess.PIPE).stdout.decode())
    slurm_ip = slurm_dns_match.group(1) if slurm_dns_match else None
    slurm_ip = None

    ip = dns_ip or slurm_ip

    return ip, dns_ip, slurm_ip


def get_shape_name(hostname):
    features = subprocess.run(["sinfo", "--Format=features:200", "--noheader", f"--nodes={hostname}"], stdout=subprocess.PIPE).stdout.decode().split(',')
    shape = [f for f in features if f.startswith("shape=")][0].split("=")[1].strip()
    return shape


def get_image(conn, cluster_id: str):
    # TODO sort images by newest
    all_images = conn.image.images(tag="compute")
    our_images = (i for i in all_images if i["properties"].get("cluster") == cluster_id)
    return next(our_images)


def create_node_config(conn, hostname: str, ip: Optional[str], nodespace: Dict[str, str], ssh_keys: str) -> dict:
    image = get_image(conn, nodespace["cluster_id"])
    flavor = conn.compute.find_flavor(get_shape_name(hostname))

    with open("/home/slurm/bootstrap.sh", "rb") as f:
        user_data = base64.b64encode(f.read()).decode()

    block_device_mapping_v2 = [
        {
            'uuid': image.id,
            'source_type': 'image',
            'volume_size': 40,
            'boot_index': 0,
            'destination_type': 'volume',
            'delete_on_termination': True,
        }
    ]

    return {
        "name": hostname,
        "image_id": image.id,
        "flavor_id": flavor.id,
        "networks": [{"uuid": nodespace["network_id"]}, {"uuid": nodespace["ceph_network"]}],
        "user_data": user_data,
        "security_groups": [{"name": nodespace["security_group"]}],
        "block_device_mapping_v2": block_device_mapping_v2,
        "tags": ["compute"],
        "metadata": {"cluster": nodespace["cluster_id"]},
    }


async def start_node(log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    log.info(f"{host}: Starting")
    conn = openstack.connect()

    node_state = get_node_state(conn, log, host, nodespace["cluster_id"])
    if node_state != "DELETED":
        log.warning(f"{host}:  host is already running with state {node_state}")
        return

    ip, _dns_ip, slurm_ip = get_ip(host)

    instance_details = create_node_config(conn, host, ip, nodespace, ssh_keys)

    try:
        instance = await asyncio.get_event_loop().run_in_executor(None, lambda: conn.compute.create_server(**instance_details))
    except openstack.exceptions.SDKException as e:
        log.error(f"{host}:  problem launching instance: {e}")
        return

    if not slurm_ip:
        instance = await asyncio.get_event_loop().run_in_executor(None, lambda: conn.compute.wait_for_server(instance))
        private_ip = instance.addresses[nodespace["network_name"]][0]["addr"]
        log.info(f"{host}:   Private IP {private_ip}")
        subprocess.run(["scontrol", "update", f"NodeName={host}", f"NodeAddr={private_ip}"])

    log.info(f"{host}:  Started")
    return instance


def terminate_instance(log, hosts):
    nodespace = get_nodespace()

    conn = openstack.connect()
    for host in hosts:
        log.info(f"Stopping {host}")

        instances = [s for s in conn.compute.servers(name=host, tags=["compute"]) if s["metadata"].get("cluster") == nodespace["cluster_id"]]
        if not instances:
            log.info(f"No instance found for {host}")
        for instance in instances:
            conn.compute.delete_server(instance)
            log.info(f" Stopped {host}")
