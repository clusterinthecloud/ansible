#! /usr/bin/env python2

from __future__ import (absolute_import, division, print_function)
import glob
import os
import subprocess

finished_nodes = set(os.path.basename(file) for file in glob.glob('/mnt/shared/finalised/*'))

all_nodes = {'mgmt'}

unfinished_nodes = all_nodes - finished_nodes

if unfinished_nodes:
    print('Error: The following nodes have not reported finishing their setup:')
    for node in sorted(unfinished_nodes):
        print(' ', node)
    print('Please allow them to finish before continuing.')
    print('For information about why they have not finished, SSH to that machine and check the file /root/ansible-pull.log')
    exit(1)

if not os.path.exists('limits.yaml'):
    print('Error: Could not find limits.yaml in this directory')
    print('Please create the file and rerun this script.')
    print('See https://cluster-in-the-cloud.readthedocs.io/en/latest/finalise.html#setting-service-limits for details.')
    exit(1)

subprocess.call(['sudo', '/usr/local/bin/update_config'])
subprocess.call(['sudo', 'systemctl', 'restart', 'slurmctld'])
