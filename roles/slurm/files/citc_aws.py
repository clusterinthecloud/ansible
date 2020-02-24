import functools
import subprocess
from typing import Dict, Optional
import yaml
import asyncio

import boto3
#from mypy_boto3 import ec2, route53


def load_yaml(filename: str) -> dict:
    with open(filename, "r") as f:
        return yaml.safe_load(f)


def get_nodespace(file="/etc/citc/startnode.yaml") -> Dict[str, str]:
    """
    Get the information about the space into which we were creating nodes
    This will be static for all nodes in this cluster
    """
    return load_yaml(file)


def get_node(client, hostname: str, cluster_id: str):  # -> ec2.Instance?
    instance = client.describe_instances(Filters=[
        {
            "Name": "tag:Name",
            "Values": [hostname],
        },
        {
            "Name": "tag:cluster",
            "Values": [cluster_id],
        },
    ])
    # TODO check for multiple returned matches
    if instance["Reservations"]:
        return instance["Reservations"][0]["Instances"][0]
    return None


def get_node_state(client, hostname: str, cluster_id: str) -> Optional[str]:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """

    item = get_node(client,  hostname, cluster_id)

    if item is not None:
        return item['State']["Name"]
    return None


def get_shape(hostname):
    features = subprocess.run(
        ["sinfo", "--Format=features:200", "--noheader", f"--nodes={hostname}"],
        stdout=subprocess.PIPE
    ).stdout.decode().split(',')
    shape = [f for f in features if f.startswith("shape=")][0].split("=")[1].strip()
    return shape


def create_node_config(client, hostname: str, nodespace: Dict[str, str], ssh_keys: str):
    """
    Create the configuration needed to create ``hostname`` in ``nodespace`` with ``ssh_keys``
    """
    with open("/home/slurm/bootstrap.sh", "rb") as f:
        user_data = f.read().decode()

    shape = get_shape(hostname)
    images = client.describe_images(
        Filters=[
            {'Name': 'product-code', 'Values': ['aw0evgkw8e5c1q413zgy5pjce']},
            {'Name': 'architecture', 'Values': ['x86_64']},
            {'Name': 'root-device-type', 'Values': ['ebs']},
        ],
        Owners=['aws-marketplace'],
    )
    image = sorted(images['Images'], key=lambda x: x['CreationDate'], reverse=True)[0]['ImageId']

    config = {
        "ImageId": image,
        "InstanceType": shape,
        "KeyName": f"ec2-user-{nodespace['cluster_id']}",
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
                    },
                    {
                        "Key": "cluster",
                        "Value": nodespace["cluster_id"]
                    },
                    {
                        "Key": "type",
                        "Value": "compute"
                    },
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


def add_dns_record(
    client,
    zone_id: str,
    rrname: str,
    rrtype,
    value: str,
    ttl: int,
    action="UPSERT"
) -> None:
    client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            'Comment': f'add {rrname} -> {value}',
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


def delete_dns_record(
    client,
    zone_id: str,
    rrname: str,
    rrtype: str,
    value: str,
    ttl: int
) -> None:
    client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch={
            'Comment': f'delete {rrname}: {value}',
            'Changes': [
                {
                    'Action': "DELETE",
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


def ec2_client(region: str):
    import configparser
    config = configparser.ConfigParser()
    config.read('/home/slurm/aws-credentials.csv')
    client = boto3.client(
        "ec2",
        region_name=region,
        aws_access_key_id=config["default"]["aws_access_key_id"],
        aws_secret_access_key=config["default"]["aws_secret_access_key"]
    )
    return client


def route53_client():
    import configparser
    config = configparser.ConfigParser()
    config.read('/home/slurm/aws-credentials.csv')
    client = boto3.client(
        "route53",
        aws_access_key_id=config["default"]["aws_access_key_id"],
        aws_secret_access_key=config["default"]["aws_secret_access_key"]
    )
    return client


async def start_node(log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    region = nodespace["region"]

    log.info(f"Starting {host}")

    client = ec2_client(region)

    while get_node_state(client, host, nodespace["cluster_id"]) in ["shutting-down", "stopping"]:
        log.info(" host is currently being deleted. Waiting...")
        await asyncio.sleep(5)

    node_state = get_node_state(client, host, nodespace["cluster_id"])
    if node_state in ["pending", "running", "rebooting", "stopped"]:
        log.warning(f" host already exists with state {node_state}")
        return

    instance_details = create_node_config(client, host, nodespace, ssh_keys)

    loop = asyncio.get_event_loop()

    try:
        start_instance = functools.partial(client.run_instances, **instance_details)
        instance_result = await loop.run_in_executor(None, start_instance)
        instance = instance_result["Instances"][0]
    except Exception as e:
        log.error(f" problem launching instance: {e}")
        return

    vm_ip = instance["PrivateIpAddress"]

    log.info(f"  Private IP {vm_ip}")

    r53_client = route53_client()

    fqdn = f"{host}.{nodespace['dns_zone']}"
    add_dns_record(r53_client, nodespace["dns_zone_id"], fqdn, "A", vm_ip, 300)

    subprocess.run(["scontrol", "update", f"NodeName={host}", f"NodeAddr={vm_ip}"])

    log.info(f" Started {host}")


def terminate_instance(log, hosts, nodespace=None):
    if not nodespace:
        nodespace = get_nodespace()

    region = nodespace["region"]

    client = ec2_client(region)

    for host in hosts:
        log.info(f"Stopping {host}")

        try:
            instance = get_node(client, host, nodespace["cluster_id"])
            instance_id = instance["InstanceId"]
            vm_ip = instance["PrivateIpAddress"]
            fqdn = f"{host}.{nodespace['dns_zone']}"
            client.terminate_instances(InstanceIds=[instance_id])
            r53_client = route53_client()
            delete_dns_record(r53_client, nodespace["dns_zone_id"], fqdn, "A", vm_ip, 300)
        except Exception as e:
            log.error(f" problem while stopping: {e}")
            continue

        log.info(f" Stopped {host}")
