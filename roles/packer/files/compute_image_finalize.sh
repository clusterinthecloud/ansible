#! /bin/bash

/usr/sbin/waagent -force -deprovision && export HISTSIZE=0 && sync
