#! /bin/bash
set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 1 ]]; then
    echo "Call with:"
    echo "    ${0} <user name>"
    exit 1
fi

USER=${1}
usermod -a -G distrac ${USER}
