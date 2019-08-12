import re
import subprocess
import time
from typing import Dict, Optional, Tuple
from google.oauth2 import service_account  # type: ignore
import googleapiclient.discovery  # type: ignore
import logging
import yaml
import os
from pathlib import Path
import asyncio

__all__ = ["get_nodespace", "start_node"]


def load_yaml(filename: str) -> dict:
    with open(filename, "r") as f:
        return yaml.safe_load(f)


def get_nodespace(file="/etc/citc/startnode.yaml") -> Dict[str, str]:
    """
    Get the information about the space into which we were creating nodes
    This will be static for all nodes in this cluster
    """
    return load_yaml(file)


def get_node(gce_compute, log, compartment_id: str, zone: str, hostname: str) -> Dict:
    filter_clause = f'(name={hostname})'

    result = gce_compute.instances().list(project=compartment_id, zone=zone, filter=filter_clause).execute()
    item = result['items'][0] if 'items' in result else None
    log.debug(f'get items {item}')
    return item


def get_node_state(gce_compute, log, compartment_id: str, zone: str, hostname: str) -> Optional[str]:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """

    item = get_node(gce_compute, log, compartment_id, zone, hostname)

    if item:
        return item['status']
    return None


def get_ip_for_vm(gce_compute, log, compartment_id: str, zone: str, hostname: str) -> str:
    item = get_node(gce_compute, log, compartment_id, zone, hostname)

    network = item['networkInterfaces'][0]
    log.debug(f'network {network}')
    ip = network['networkIP']
    return ip


def get_shape(hostname):
    features = subprocess.run(["sinfo", "--Format=features:200", "--noheader", f"--nodes={hostname}"], stdout=subprocess.PIPE).stdout.decode().split(',')
    shape = [f for f in features if f.startswith("shape=")][0].split("=")[1].strip()
    return shape


def create_node_config(gce_compute, hostname: str, ip: Optional[str], nodespace: Dict[str, str], ssh_keys: str):
    """
    Create the configuration needed to create ``hostname`` in ``nodespace`` with ``ssh_keys``
    """
    shape = get_shape(hostname)
    subnet = nodespace["subnet"]
    zone = nodespace["zone"]

    with open("/home/slurm/bootstrap.sh", "rb") as f:
        user_data = f.read().decode()

    machine_type = f"zones/{zone}/machineTypes/{shape}"

    image_response = gce_compute.images().getFromFamily(project='gce-uefi-images', family='centos-7').execute()
    source_disk_image = image_response['selfLink']

    config = {
        'name': hostname,
        'machineType': machine_type,

        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': source_disk_image,
                }
            }
        ],
        'networkInterfaces': [
            {
                'subnetwork': subnet,
                'addressType': 'INTERNAL',  # Can't find this in the docs...
                'address': ip,  # should be networkIP?
                'accessConfigs': [
                    {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
                ]
            }
        ],
        'minCpuPlatform': 'Intel Skylake',
        'metadata': {
            'items': [{
                'key': 'startup-script',
                'value': user_data
            }]
        },
        'tags': {
            "items": [
                "compute",
            ],
        },
    }

    return config


def get_ip(hostname: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    host_dns_match = re.match(r"(\d+\.){3}\d+", subprocess.run(["host", hostname], stdout=subprocess.PIPE).stdout.decode().split()[-1])
    dns_ip = host_dns_match.group(0) if host_dns_match else None

    slurm_dns_match = re.search(r"NodeAddr=((\d+\.){3}\d+)", subprocess.run(["scontrol", "show", "node", hostname], stdout=subprocess.PIPE).stdout.decode())
    slurm_ip = slurm_dns_match.group(1) if slurm_dns_match else None

    ip = dns_ip or slurm_ip

    return ip, dns_ip, slurm_ip


def get_credentials():
    service_account_file = Path(os.environ.get('SA_LOCATION', '/home/slurm/mgmt-sa-credentials.json'))
    if service_account_file.exists():
        return service_account.Credentials.from_service_account_file(service_account_file)
    return None


def get_build():
    credentials = get_credentials()

    compute = googleapiclient.discovery.build('compute', 'v1', credentials=credentials, cache_discovery=False)

    return compute


async def start_node(log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    project = nodespace["compartment_id"]
    zone = nodespace["zone"]

    log.info(f"Starting {host} in {project} {zone}")

    gce_compute = get_build()

    while get_node_state(gce_compute, log, project, zone, host) in ["STOPPING", "TERMINATED"]:
        log.info(" host is currently being deleted. Waiting...")
        await asyncio.sleep(5)

    node_state = get_node_state(gce_compute, log, project, zone, host)
    if node_state is not None:
        log.warning(f" host is already running with state {node_state}")
        return

    ip, _dns_ip, slurm_ip = get_ip(host)

    instance_details = create_node_config(gce_compute, host, ip, nodespace, ssh_keys)

    loop = asyncio.get_event_loop()

    try:
        inserter = gce_compute.instances().insert(project=project, zone=zone, body=instance_details)
        instance = await loop.run_in_executor(None, inserter.execute)
    except Exception as e:
        log.error(f" problem launching instance: {e}")
        return

    if not slurm_ip:
        while not get_node(gce_compute, log, project, zone, host)['networkInterfaces'][0].get("networkIP"):
            log.info(f"{host}:  No VNIC attachment yet. Waiting...")
            await asyncio.sleep(5)
        vm_ip = get_ip_for_vm(gce_compute, log, project, zone, host)

        log.info(f"  Private IP {vm_ip}")

        subprocess.run(["scontrol", "update", f"NodeName={host}", f"NodeAddr={vm_ip}"])

    log.info(f" Started {host}")

    return instance


def terminate_instance(log, hosts, nodespace=None):
    gce_compute = get_build()

    if not nodespace:
        nodespace = get_nodespace()

    project = nodespace["compartment_id"]
    zone = nodespace["zone"]

    for host in hosts:
        log.info(f"Stopping {host}")

        try:
            response = gce_compute.instances() \
                .delete(project=project,
                        zone=zone,
                        instance=host) \
                .execute()
        except Exception as e:
            log.error(f" problem while stopping: {e}")
            continue

    log.info(f" Stopped {host}")


# [START run]
async def do_create_instance():
    os.environ['SA_LOCATION'] = '/home/davidy/secrets/ex-eccoe-university-bristol-52b726c8a1f3.json'
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    log = logging.getLogger("startnode")

    hosts = ['dy-test-node1']

    log.info('Creating instance.')

    await asyncio.gather(*(
        start_node(log, host, get_nodespace('test_nodespace.yaml'), "")
        for host in hosts
    ))

    log.info(f'Instances in project done')

    log.info(f'Terminating')
    terminate_instance(log, hosts, nodespace=get_nodespace('test_nodespace.yaml'))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(do_create_instance())
    finally:
        loop.close()
