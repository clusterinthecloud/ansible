#! /bin/bash
set -euo pipefail

# TODO Use python-citc

echo Terminating any remaining compute nodes
if systemctl status slurmctld >> /dev/null; then
    sudo -u slurm /usr/local/bin/stopnode "$(sinfo --noheader --Format=nodelist:10000 | tr -d '[:space:]')" || true
fi
sleep 5
echo Node termination request completed
