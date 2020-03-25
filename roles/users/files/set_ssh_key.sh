#! /bin/bash
set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 1 ]]; then
    echo "Call with:"
    echo "    ${0} <user name>"
    exit 1
fi

USER=${1}

HOMEROOT=/mnt/shared/home
USERHOME=${HOMEROOT}/${USER}
USERSSH=${USERHOME}/.ssh

mkdir -p ${USERSSH}
chmod 700 ${USERSSH}

rm -f ${USERSSH}/authorized_keys
while read LINE; do
   echo ${LINE} >> ${USERSSH}/authorized_keys
done
chmod 600 ${USERSSH}/authorized_keys

chown -R ${USER}:users ${USERHOME}
