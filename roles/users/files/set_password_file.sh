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
PASSWORD_FILE=${USERHOME}/.password

rm -f ${PASSWORD_FILE}
read PASSWORD
echo ${PASSWORD} > ${PASSWORD_FILE}
chmod 400 ${PASSWORD_FILE}
chown ${USER}:users ${PASSWORD_FILE}
