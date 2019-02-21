from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    vars: oci_shapes
    version_added: "2.6"
    short_description: In charge of creating the Slurm config for each compute instance
'''

from ansible.errors import AnsibleFileNotFound
from ansible.plugins.vars import BaseVarsPlugin

FOUND = {}


class VarsModule(BaseVarsPlugin):

    def get_vars(self, loader, path, entities, cache=True):
        ''' parses the inventory file '''

        super(VarsModule, self).get_vars(loader, path, entities)

        try:
            nodes = loader.load_from_file('/home/opc/nodes.yaml')
            shapes = loader.load_from_file('/home/opc/shapes.yaml')
        except AnsibleFileNotFound:
            return {}

        nodelist = {}
        for hostname, shape in zip(nodes['names'], nodes['shapes']):
            try:
                nodelist[hostname] = shapes[shape]
            except KeyError as e:
                print("Error: could not find shape information for {}. \nPlease log a ticket at https://github.com/ACRC/oci-cluster-terraform/issues/new".format(shape))

        data = {"slurm_compute_nodelists": nodelist}
        return data
