#! /usr/bin/env python2

from __future__ import (absolute_import, division, print_function)
import glob
import os
import subprocess

finished_nodes = set(os.path.basename(file) for file in glob.glob('/mnt/shared/finalised/*'))

all_nodes = set()
with open('/home/opc/hosts') as all_node_config:
    for line in all_node_config:
        if not line.startswith('['):
            all_nodes.add(line.strip())

unfinished_nodes = all_nodes - finished_nodes

if unfinished_nodes:
    print('Error: The following nodes have not reported finishing their setup:')
    for node in sorted(unfinished_nodes):
        print(' ', node)
    print('Please allow them to finish before continuing.')
    print('For information about why they have not finished, SSH to that machine and check the file /home/opc/ansible-pull.log')
    exit(1)

if not os.path.exists('/home/opc/users.yml'):
    print('Error: Could not find users.yml')
    print('Please rename and edit users.yml.example to users.yml and rerun this script.')
    print('It should contain the users you want to have access to the system along with their SSH keys.')
    exit(1)

rc = subprocess.call(['ansible-playbook', '--inventory=/home/opc/hosts', '--extra-vars=@/home/opc/users.yml', 'finalise.yml'], cwd='/home/opc/slurm-ansible-playbook')

if rc != 0:
    print('Error: Ansible run did not complete correctly')
