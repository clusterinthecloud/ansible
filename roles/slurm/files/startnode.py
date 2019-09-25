#! /opt/cloud_sdk/bin/python

import asyncio
import logging
import subprocess
import sys
import citc_cloud



def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


async def main() -> None:
    nodespace = citc_cloud.get_nodespace()

    keys_file = "/home/slurm/opc_authorized_keys"

    with open(keys_file) as kf:
        ssh_keys = kf.read()

    hosts = subprocess.run(["scontrol", "show", "hostnames", sys.argv[1]], stdout=subprocess.PIPE).stdout.decode().split()

    await asyncio.gather(*(
        citc_cloud.start_node( log, host, nodespace, ssh_keys)
        for host in hosts
    ))

sys.excepthook = handle_exception

if __name__ == "__main__":
    log = logging.getLogger("startnode")
    log.setLevel(logging.INFO)
    handler = logging.FileHandler('/var/log/slurm/elastic.log')
    formatter = logging.Formatter('%(asctime)s %(name)-10s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    log.addHandler(handler)

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
