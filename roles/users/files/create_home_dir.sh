#! /bin/bash
set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 1 ]]; then
    echo "Call with:"
    echo "    ${0} <user name>"
    exit 1
fi

HOMEROOT=/mnt/shared/home

USER=${1}

mkdir ${HOMEROOT}/${USER}
chmod 700 ${HOMEROOT}/${USER}
cp -r /etc/skel/. /mnt/shared/home/${USER}/
timeout 30s bash -c "until sudo chown -R ${USER}:users ${HOMEROOT}/${USER}; do sleep 1; done"
