#! /opt/cloud_sdk/bin/python

import re
from typing import Dict, Optional

import yaml


def load_yaml(filename) -> dict:
    with open(filename, "r") as f:
        return yaml.safe_load(f)


def get_limits() -> Dict[str, Dict[str, str]]:
    """
    Until OCI has an API to fetch service limits, we have to hard-code
    them in a file.
    """
    return load_yaml("limits.yaml")


def get_shapes() -> Dict[str, Dict[str, str]]:
    return load_yaml("/etc/citc/shapes.yaml")


def get_mgmt_info() -> Dict[str, str]:
    try:
        return load_yaml("/etc/citc/mgmt_shape.yaml")
    except FileNotFoundError:
        return {}


def encode_nodename(shape_name: str, node_number: int, ad: Optional[int] = None) -> str:
    if ad is not None:
        return "{}-ad{}-{:0>4}".format(shape_name.lower().replace(".", "-"), ad, node_number)
    else:
        return "{}-{:0>4}".format(shape_name.lower().replace(".", "-"), node_number)


def create_slurmconf_line(number: int, shape_info: Dict, shape: str, ad: Optional[int] = None):
    nodename = encode_nodename(shape, number, ad)
    features = "shape={shape},ad={ad}".format(shape=shape, ad=ad)
    config_template = 'NodeName={nodename:40} State={state:7} SocketsPerBoard={sockets:<1} CoresPerSocket={cores_per_socket:<3} ThreadsPerCore={threads_per_core:<1} RealMemory={memory:<10} Gres="{gres}" Features="{features}"'
    config = config_template.format(
        nodename=nodename,
        state="CLOUD",
        sockets=shape_info.get("sockets", 1),
        cores_per_socket=shape_info["cores_per_socket"],
        threads_per_core=shape_info.get("threads_per_core", 1),
        memory=shape_info["memory"],
        gres=shape_info.get("gres", ""),
        features=features,
    )
    return config


def get_node_configs(limits, shapes, mgmt_info):
    for shape, shape_counts in limits.items():
        try:
            shape_info = shapes[shape]
        except KeyError as e:
            print("Error: Could not find shape information for {}. \nPlease log a ticket at https://github.com/ACRC/oci-cluster-terraform/issues/new".format(e))
            continue

        if isinstance(shape_counts, int):
            for i in range(1, shape_counts+1):
                yield create_slurmconf_line(i, shape_info, shape)
        else:
            for ad, ad_count in shape_counts.items():
                if mgmt_info and shape == mgmt_info["mgmt_shape"] and ad == mgmt_info["mgmt_ad"]:
                    ad_count -= 1
                for i in range(1, ad_count+1):
                    yield create_slurmconf_line(i, shape_info, shape, ad)


# TODO Make sure that any nodes which are no longer managed due to service limit reductions are terminated.

slurm_conf_filename = "/mnt/shared/etc/slurm/slurm.conf"

node_config = "\n".join(get_node_configs(get_limits(), get_shapes(), get_mgmt_info()))

chop = re.compile('(?<=# STARTNODES\n)(.*?)(?=\n?# ENDNODES)', re.DOTALL)

with open(slurm_conf_filename) as f:
    all_config = f.read()

new_config = chop.sub('{}'.format(node_config), all_config)

with open(slurm_conf_filename, "w") as f:
    f.write(new_config)
