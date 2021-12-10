import asyncio
import base64
import re
import subprocess
import time
from typing import Dict, Optional, Tuple, List

import yaml  # type: ignore
import os
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient

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


#def get_node_state(oci_config, log, compartment_id: str, hostname: str, cluster_id: str) -> str:
def get_node_state(compute_client, log, hostname: str, resource_group: str) -> str:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """
    #matches = compute_client.virtual_machines.list(resource_group)
    #print(matches)
    #matches = oci.core.ComputeClient(oci_config).list_instances(compartment_id=compartment_id, display_name=hostname).data
    #matches = [i for i in matches if i.freeform_tags.get("cluster") == cluster_id]
    #still_exist = [i for i in matches if i.lifecycle_state != "TERMINATED"]
    #if not still_exist:
    #    return "TERMINATED"
    #if len(still_exist) > 1:
    #    log.error(f"{hostname}: Multiple matches found for {hostname}")
    #return still_exist[0].lifecycle_state
    return "node_state"


#def get_ip(hostname: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
def get_ip() -> str:
    #host_dns_match = re.match(r"(\d+\.){3}\d+", subprocess.run(["host", hostname], stdout=subprocess.PIPE).stdout.decode().split()[-1])
    #dns_ip = host_dns_match.group(0) if host_dns_match else None

    #slurm_dns_match = re.search(r"NodeAddr=((\d+\.){3}\d+)", subprocess.run(["scontrol", "show", "node", hostname], stdout=subprocess.PIPE).stdout.decode())
    #slurm_ip = slurm_dns_match.group(1) if slurm_dns_match else None

    #ip = dns_ip or slurm_ip

    #return ip, dns_ip, slurm_ip
    return "ip"


async def start_node(log, host: str, nodespace: Dict[str, str], ssh_keys: str) -> None:
    log.info(f"{host}: Starting")
    credential = DefaultAzureCredential()
    nodespace = get_nodespace()
    subscription_id = nodespace["subscription"]
    resource_group = nodespace["resource_group"]
    region = nodespace["region"]
    subnet = nodespace["subnet"]
    dns_zone = "."+nodespace["dns_zone"]
    ip = "ip"
    resource_client = ResourceManagementClient(credential, subscription_id)
    network_client = NetworkManagementClient(credential, subscription_id)
    compute_client = ComputeManagementClient(credential, subscription_id)
    
    with open("/home/slurm/bootstrap.sh", "rb") as f:
        custom_data = base64.b64encode(f.read()).decode()

    while get_node_state(compute_client, log, host, resource_group) == "TERMINATING":
      log.info(f"{host}:  host is currently terminating. Waiting...")
      await asyncio.sleep(5)

    images = compute_client.images.list_by_resource_group(resource_group)
    for image in images:
        vm_image = str(image.id)

    poller = network_client.network_interfaces.begin_create_or_update(resource_group,host+"-nic", 
      {
        "location": region,
        "ip_configurations": [ {
          "name": host+"-nic",
          "subnet": { "id": subnet },
           }]
        }
    )

    nic_result = poller.result()

    print(f"Provisioning virtual machine {host}; this operation might take a few minutes.")

    poller = compute_client.virtual_machines.begin_create_or_update(resource_group, host, {
        "location": region,
        "storage_profile": {
          "image_reference": {
            "id": vm_image,
            }
          },
        "hardware_profile": {
          "vm_size": "Standard_D4s_v3"
          },
        "os_profile": {
          "computer_name": host,
          "admin_username": "centos",
          "linux_configuration": {
              "ssh": { 
                  "public_keys" : [ { 
                      "path": "/home/centos/.ssh/authorized_keys",
                      "key_data": ssh_keys 
                      } ]
                  }
              },
          "custom_data": custom_data,
          },
        "network_profile": {
          "network_interfaces": [{
            "id": nic_result.id,
            }]
          }
        })
    
    vm_result = poller.result()

    print(f"Provisioned virtual machine {vm_result.name}")

    log.info(f"{host}:  Started")
    return vm_result


def terminate_instance(log, hosts):

    credential = DefaultAzureCredential()
    nodespace = get_nodespace()
    subscription_id = nodespace["subscription"]
    resource_client = ResourceManagementClient(credential, subscription_id)
    compute_client = ComputeManagementClient(credential, subscription_id)

    for host in hosts:
      log.info(f"Stopping {host}")

      try:
        vm = compute_client.virtual_machines.get(resource_group, host, expand='instanceView')
        for stat in vm.instance_view.statuses:
          if stat.code == "PowerState/running":
            poller = compute_client.virtual_machines.begin_delete(resource_group, host)
            vm_result = poller.result()
            print(f"Deleted virtual machine {vm_result.name}")
      except:
        print("An exception occurred") 
      log.info(f" Stopped {host}")
