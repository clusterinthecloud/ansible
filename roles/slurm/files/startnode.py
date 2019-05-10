#! /opt/oci/bin/python

import logging
import subprocess
import sys

import citc_oci
import oci


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def main() -> None:

    oci_config = oci.config.from_file()

    nodespace = citc_oci.get_nodespace()

    keys_file = "/home/slurm/opc_authorized_keys"

    with open(keys_file) as kf:
        ssh_keys = kf.read()

    hosts = subprocess.run(["scontrol", "show", "hostnames", sys.argv[1]], stdout=subprocess.PIPE).stdout.decode().split()

    for host in hosts:
        citc_oci.start_node(oci_config, log, host, nodespace, ssh_keys)


sys.excepthook = handle_exception

if __name__ == "__main__":
    main()
    log = logging.getLogger("startnode")
    log.setLevel(logging.INFO)
    handler = logging.FileHandler('/var/log/slurm/elastic.log')
    formatter = logging.Formatter('%(asctime)s %(name)-10s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)