#! /bin/bash
set -euo pipefail

# TODO Use python-citc

if [[ $# -ne 1 || "${1}" != "--force" ]]; then
    read -p "Are you sure you want to kill all running compute nodes [y/N]? " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]
    then
        echo Exiting without killing nodes
        exit 1
    fi
    echo
fi

echo Terminating any remaining compute nodes
if systemctl status slurmctld >> /dev/null; then
    sudo -u slurm /usr/local/bin/stopnode "$(sinfo --noheader --Format=nodelist:10000 | tr -d '[:space:]')" || true
fi
sleep 5
echo Node termination request completed
