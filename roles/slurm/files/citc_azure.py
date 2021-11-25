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


#def get_subnet(oci_config, compartment_id: str, vcn_id: str, cluster_id: str) -> str:
def get_subnet() -> str:
    """
    Get the relevant cluster subnet for a given compartment, VCN and AD
    """
    #return [s.id for s in oci.core.VirtualNetworkClient(oci_config).list_subnets(compartment_id, vcn_id=vcn_id).data if s.freeform_tags.get("cluster") == cluster_id][0]
    return "subnet"


#def get_node_state(oci_config, log, compartment_id: str, hostname: str, cluster_id: str) -> str:
def get_node_state() -> str:
    """
    Get the current node state of the VM for the given hostname
    If there is no such VM, return "TERMINATED"
    """
    #matches = oci.core.ComputeClient(oci_config).list_instances(compartment_id=compartment_id, display_name=hostname).data
    #matches = [i for i in matches if i.freeform_tags.get("cluster") == cluster_id]
    #still_exist = [i for i in matches if i.lifecycle_state != "TERMINATED"]
    #if not still_exist:
    #    return "TERMINATED"
    #if len(still_exist) > 1:
    #    log.error(f"{hostname}: Multiple matches found for {hostname}")
    #return still_exist[0].lifecycle_state
    return "node_state"


#def get_image(oci_config, compartment_id: str, cluster_id: str) -> oci.core.models.Image:
def get_image() -> str:
    #all_images = oci.pagination.list_call_get_all_results_generator(oci.core.ComputeClient(oci_config).list_images, 'record', compartment_id, operating_system="Oracle Linux")
    #our_images: List[oci.core.models.Image] = [i for i in all_images if i.freeform_tags.get("cluster") == cluster_id]
    try:
        #return [i for i in our_images if "GPU" not in i.display_name][0]
        return "image"
    except IndexError:
        raise RuntimeError("Could not locate the image for the compute node")


#def create_node_config(oci_config, hostname: str, ip: Optional[str], nodespace: Dict[str, str], ssh_keys: str) -> oci.core.models.LaunchInstanceDetails:
def create_node_config() -> str:
    """
    Create the configuration needed to create ``hostname`` in ``nodespace`` with ``ssh_keys``
    """
    #features = subprocess.run(["sinfo", "--Format=features:200", "--noheader", f"--nodes={hostname}"], stdout=subprocess.PIPE).stdout.decode().split(',')
    #ad_number = [f for f in features if f.startswith("ad=")][0].split("=")[1].strip()
    #ad = f"{nodespace['ad_root']}{ad_number}"
    #shape = [f for f in features if f.startswith("shape=")][0].split("=")[1].strip()
    #subnet = get_subnet(oci_config, nodespace["compartment_id"], nodespace["vcn_id"], nodespace["cluster_id"])
    #image = get_image(oci_config, nodespace["compartment_id"], nodespace["cluster_id"])

    #with open("/home/slurm/bootstrap.sh", "rb") as f:
    #    user_data = base64.b64encode(f.read()).decode()

    #instance_details = oci.core.models.LaunchInstanceDetails(
    #    compartment_id=nodespace["compartment_id"],
    #    availability_domain=ad,
    #    shape=shape,
    #    subnet_id=subnet,
    #    image_id=image.id,
    #    display_name=hostname,
    #    hostname_label=hostname,
    #    create_vnic_details=oci.core.models.CreateVnicDetails(private_ip=ip, subnet_id=subnet) if ip else None,
    #    metadata={
    #        "ssh_authorized_keys": ssh_keys.strip(),
    #        "user_data": user_data,
    #    },
    #    freeform_tags={
    #        "type": "compute",
    #        "cluster": nodespace["cluster_id"],
    #    },
    #)

    #return instance_details
    return "instance_details"


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
    #oci_config = oci.config.from_file()
    credential = DefaultAzureCredential()
    nodespace = get_nodespace()
    subscription_id = nodespace["subscription"]
    resource_group = nodespace["resource_group"]
    region = nodespace["region"]
    subnet = nodespace["subnet"]
    resource_client = ResourceManagementClient(credential, subscription_id)
    network_client = NetworkManagementClient(credential, subscription_id)
    compute_client = ComputeManagementClient(credential, subscription_id)
    
    poller = network_client.network_interfaces.begin_create_or_update(RESOURCE_GROUP_NAME,NIC_NAME, 
      {
        "location": region,
        "ip_configurations": [ {
          "name": "mynic",
          "subnet": { "id": subnet },
           }]
        }
    )

    nic_result = poller.result()

    VM_NAME = "ExampleVM"
    USERNAME = "azureuser"
    PASSWORD = "ChangePa$$w0rd24"

    print(f"Provisioning virtual machine {VM_NAME}; this operation might take a few minutes.")

    poller = compute_client.virtual_machines.begin_create_or_update(resource_group, VM_NAME,
      {
        "location": region,
        "storage_profile": {
          "image_reference": {
            "publisher": 'Canonical',
            "offer": "UbuntuServer",
            "sku": "16.04.0-LTS",
            "version": "latest"
            }
          },
        "hardware_profile": {
          "vm_size": "Standard_DS1_v2"
          },
        "os_profile": {
          "computer_name": VM_NAME,
          "admin_username": USERNAME,
          "admin_password": PASSWORD
          },
        "network_profile": {
          "network_interfaces": [{
            "id": nic_result.id,
            }]
          }        
        }
    )
    vm_result = poller.result()

    print(f"Provisioned virtual machine {vm_result.name}")

    log.info(f"{host}:  Started")
    return vm_result

    #while get_node_state(oci_config, log, nodespace["compartment_id"], host, nodespace["cluster_id"]) == "TERMINATING":
    #    log.info(f"{host}:  host is currently terminating. Waiting...")
    #    await asyncio.sleep(5)

    #node_state = get_node_state(oci_config, log, nodespace["compartment_id"], host, nodespace["cluster_id"])
    #if node_state != "TERMINATED":
    #    log.warning(f"{host}:  host is already running with state {node_state}")
    #    return

    #ip, _dns_ip, slurm_ip = get_ip(host)

    #instance_details = create_node_config(oci_config, host, ip, nodespace, ssh_keys)

    #loop = asyncio.get_event_loop()
    #retry_strategy_builder = oci.retry.RetryStrategyBuilder()
    #retry_strategy_builder.add_max_attempts(max_attempts=10).add_total_elapsed_time(total_elapsed_time_seconds=600)
    #retry_strategy = retry_strategy_builder.get_retry_strategy()
    #client = oci.core.ComputeClient(oci_config, retry_strategy=retry_strategy)

    #try:
    #    instance_result = await loop.run_in_executor(None, client.launch_instance, instance_details)
    #    instance = instance_result.data
    #except oci.exceptions.ServiceError as e:
    #    log.error(f"{host}:  problem launching instance: {e}")
    #    return

    #if not slurm_ip:
    #    node_id = instance.id
    #    while not oci.core.ComputeClient(oci_config).list_vnic_attachments(instance_details.compartment_id, instance_id=node_id).data:
    #        log.info(f"{host}:  No VNIC attachment yet. Waiting...")
    #        await asyncio.sleep(5)

    #    vnic_id = oci.core.ComputeClient(oci_config).list_vnic_attachments(instance_details.compartment_id, instance_id=node_id).data[0].vnic_id
    #    private_ip = oci.core.VirtualNetworkClient(oci_config).get_vnic(vnic_id).data.private_ip

    #    log.info(f"{host}:   Private IP {private_ip}")
    #    subprocess.run(["scontrol", "update", f"NodeName={host}", f"NodeAddr={private_ip}"])

    #log.info(f"{host}:  Started")
    #return instance

def terminate_instance(log, hosts):

    #config = oci.config.from_file()
    credential = DefaultAzureCredential()
    nodespace = get_nodespace()
    subscription_id = nodespace["subscription"]
    resource_client = ResourceManagementClient(credential, subscription_id)
    compute_client = ComputeManagementClient(credential, subscription_id)

    #for host in hosts:
    #    log.info(f"Stopping {host}")
#
#        try:
#            matching_nodes = oci.core.ComputeClient(config).list_instances(nodespace["compartment_id"], display_name=host).data
#            node_id = [n.id for n in matching_nodes if n.lifecycle_state not in {"TERMINATED", "TERMINATING"}][0]
#
#            oci.core.ComputeClient(config).terminate_instance(node_id)
#        except Exception as e:
#            log.error(f" problem while stopping: {e}")
#            continue

    log.info(f" Stopped {host}")
