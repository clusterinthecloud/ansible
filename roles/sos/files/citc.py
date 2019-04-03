# This file is part of the sos project: https://github.com/sosreport/sos
#
# This copyrighted material is made available to anyone wishing to use,
# modify, copy, or redistribute it subject to the terms and conditions of
# version 2 of the GNU General Public License.
#
# See the LICENSE file in the source distribution for further information.

from sos.plugins import Plugin, RedHatPlugin, DebianPlugin


class Citc(Plugin, RedHatPlugin, DebianPlugin):
    '''Cluster in the Cloud information
    '''

    plugin_name = 'citc'
    profiles = ('system',)

    def setup(self):

        self.add_cmd_output([
            'sinfo',
            'sinfo -R',
            'scontrol show nodes'
        ])

        self.add_copy_spec([
            '/home/opc/config',
            '/home/opc/limits.yaml',
            '/home/opc/startnode.yaml',
            '/mnt/shared/etc/slurm/slurm.conf',
            '/var/log/slurm/elastic.log',
            '/var/log/slurm/slurmctld.log',
            '/etc/citc/mgmt_shape.yaml',
            '/etc/citc/shapes.yaml',
            '/etc/citc/startnode.yaml',
        ])
