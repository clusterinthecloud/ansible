#! /opt/cloud_sdk/bin/python

import logging
import subprocess
import sys

import citc_cloud


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    log.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception

log = logging.getLogger("stopnode")
log.setLevel(logging.INFO)
handler = logging.FileHandler('/var/log/slurm/elastic.log')
formatter = logging.Formatter('%(asctime)s %(name)-10s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
log.addHandler(handler)

hosts = subprocess.run(["scontrol", "show", "hostnames", sys.argv[1]], stdout=subprocess.PIPE).stdout.decode().split()

citc_cloud.terminate_instance(log, hosts)
