#! /bin/bash
set -euo pipefail
IFS=$'\n\t'

SLURM_CONF=/mnt/shared/etc/slurm/slurm.conf

FORMAT='nodelist,statelong:12,reason:30,cpus:5,socketcorethread:8,memory:10,features:40,gres:20,nodeaddr,timestamp'

sinfo --Format="${FORMAT}" | head -n1
grep -o -E 'NodeName=([a-zA-Z0-9][a-zA-Z0-9\-]*)' "${SLURM_CONF}" | cut -c10- | while read -r node
do
        sinfo --nodes "${node}" --Format="${FORMAT}" -h
done
