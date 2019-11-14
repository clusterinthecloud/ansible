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

    shape = get_shape(hostname)

    config = {
        "ImageId": "ami-040ba9174949f6de4",
        "InstanceType": shape,
        "KeyName": "ec2-user",
        "MinCount": 1,
        "MaxCount": 1,
        "UserData": user_data,
        "IamInstanceProfile": {
            'Name': "describe_tags",
        },
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
                "SubnetId": nodespace["subnet"],
                "Groups": [nodespace["compute_security_group"]],
            },
        ],
    }

    return config


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
