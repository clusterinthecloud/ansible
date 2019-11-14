import re
import subprocess
import time
from typing import Dict, Optional, Tuple
import logging
import yaml
import os
from pathlib import Path
import asyncio

import boto3

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


def get_node(client, log, hostname: str) -> Dict:
    
    instance = client.describe_instances(Filters=
            [
                {
                    "Name": "tag:Name",
                    "Values": [hostname],
                }
            ]
    )
    #TODO check for multiple returned matches
    if instance["Reservations"]:
        return instance["Reservations"][0]["Instances"][0]
    return None


def get_node_state(client, log, hostname: str) -> Optional[str]:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """

    item = get_node(client, log,  hostname)

    if item is not None:
        return item['State']["Name"]
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


def create_node_config(client, hostname: str, nodespace: Dict[str, str], ssh_keys: str):
    """
    Create the configuration needed to create ``hostname`` in ``nodespace`` with ``ssh_keys``
    """
    with open("/home/slurm/bootstrap.sh", "rb") as f:
        user_data = f.read().decode()

    config = {
        "ImageId": "ami-040ba9174949f6de4",
        "InstanceType": "t3.micro",
        "KeyName": "ec2-user",
        "MinCount": 1,
        "MaxCount": 1,
        #"SecurityGroupIds": ["sg-05c317d0abb0846b0"],
        #"SubnetId": "subnet-0d9dc7a152ebd0d63",
        "UserData": user_data,
        "TagSpecifications": [
            {
                "ResourceType": "instance",
                "Tags": [
                    {
                        "Key": "Name",
                        "Value": hostname
                    }
                ]
            }
        ],
        "NetworkInterfaces": [
            {
                "AssociatePublicIpAddress": True,
                "DeviceIndex": 0,
                "SubnetId": "subnet-0d9dc7a152ebd0d63",
                "Groups": ["sg-05c317d0abb0846b0"],
            },
        ],
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

def add_dns_record(client, zone_id: str, rrname: str, rrtype: str, value: str, ttl: int, action: str) -> None:
    response = client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch= {
            'Comment': 'add %s -> %s' % (rrname, value),
            'Changes': [
                {
                    'Action': action,
                    'ResourceRecordSet': {
                        'Name': rrname,
                        'Type': rrtype,
                        'TTL': ttl,
                        'ResourceRecords': [{'Value': value}]
                    }
                }
            ]
        }
    )

async def start_node(log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    region = nodespace["region"]

    log.info(f"Starting {host}")

    import configparser
    config = configparser.ConfigParser()
    config.read('/home/slurm/aws-credentials.csv')
    client = boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=config["default"]["aws_access_key_id"],
        aws_secret_access_key=config["default"]["aws_secret_access_key"]
    )

    while get_node_state(client, log, host) in ["shutting-down", "stopping"]:
        log.info(" host is currently being deleted. Waiting...")
        await asyncio.sleep(5)

    node_state = get_node_state(client, log, host)
    if node_state in ["pending", "running", "rebooting", "stopped"]:
        log.warning(f" host already exists with state {node_state}")
        return

    instance_details = create_node_config(client, host, nodespace, ssh_keys)

    loop = asyncio.get_event_loop()

    try:
        #instance_result = await loop.run_in_executor(None, client.run_instances, **instance_details)
        #TODO await
        instance_result = client.run_instances(**instance_details)
        instance = instance_result
    except Exception as e:
        log.error(f" problem launching instance: {e}")
        return

    vm_ip = instance["Instances"][0]["PrivateIpAddress"]

    log.info(f"  Private IP {vm_ip}")

    route53_client = boto3.client(
        "route53",
        aws_access_key_id=config["default"]["aws_access_key_id"],
        aws_secret_access_key=config["default"]["aws_secret_access_key"]
    )

    domain = "cluster.citc.local"
    fqdn = f"{host}.{domain}"
    add_dns_record(route53_client, "Z081015635NMRHH9O1SXU", fqdn, "A", vm_ip, 300, "UPSERT")

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
