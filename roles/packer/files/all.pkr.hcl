variable "google_source_image_family" {}
variable "google_account_file" {}
variable "google_destination_image_family" {}
variable "google_project_id" {}
variable "google_zone" {}
variable "google_network" {}
variable "google_subnetwork" {}

variable "aws_region" {}
variable "aws_instance_type" {}
variable "aws_arch" {}

variable "oracle_availability_domain" {}
variable "oracle_base_image_ocid" {}
variable "oracle_compartment_ocid" {}
variable "oracle_subnet_ocid" {}
variable "oracle_shape" {}
variable "oracle_access_cfg_file" {}
variable "oracle_key_file" {}

variable "destination_image_name" {}
variable "cluster" {}
variable "ca_cert" {}
variable "ssh_username" {}

source "googlecompute" "google" {
    account_file = var.google_account_file
    source_image_family = var.google_source_image_family
    ssh_username = var.ssh_username
    project_id = var.google_project_id
    zone = var.google_zone
    network = var.google_network
    subnetwork = var.google_subnetwork
    use_internal_ip = true
    tags = ["compute-${var.cluster}"]
    image_name = "${var.destination_image_name}-${var.cluster}-v{{timestamp}}"
    image_family = "${var.google_destination_image_family}-${var.cluster}"
    labels = {
        cluster = var.cluster
    }
    image_labels = {
        cluster = var.cluster
    }
}

source "amazon-ebs" "aws" {
    ami_name = "${var.destination_image_name}-${var.cluster}-v{{timestamp}}"
    run_volume_tags = {
        cluster = var.cluster
    }
    tags = {
        cluster = var.cluster
    }
    snapshot_tags = {
        cluster = var.cluster
    }
    run_tags = {
        cluster = var.cluster
    }
    force_deregister = true
    force_delete_snapshot = true
    region = var.aws_region
    instance_type = var.aws_instance_type
    source_ami_filter {
        filters = {
            name = "Rocky-8*"
            architecture = var.aws_arch
        }
        owners = ["792107900819"] #Owner ID as stated from https://forums.rockylinux.org/t/rocky-linux-official-aws-ami/3049/25
        most_recent = true
    }
    ssh_username = var.ssh_username
    vpc_filter {
        filter {
            name = "tag:cluster"
            value = var.cluster
        }
    }
    subnet_filter {
        filter {
            name = "tag:cluster"
            value = var.cluster
        }
    }
    associate_public_ip_address = true

    launch_block_device_mappings {
        device_name = "/dev/sda1"
        volume_size =  20
        delete_on_termination = true
    }
}

source "oracle-oci" "oracle" {
    image_name = "${var.destination_image_name}-${var.cluster}-v{{timestamp}}"
    availability_domain = var.oracle_availability_domain
    base_image_ocid = var.oracle_base_image_ocid
    compartment_ocid = var.oracle_compartment_ocid
    shape = var.oracle_shape
    subnet_ocid = var.oracle_subnet_ocid
    access_cfg_file = var.oracle_access_cfg_file
    key_file = var.oracle_key_file
    tags = {
        cluster = var.cluster
    }
    ssh_username = var.ssh_username
}

build {
    sources = [
        "source.googlecompute.google",
        "source.amazon-ebs.aws",
        "source.oracle-oci.oracle",
    ]

    provisioner "file" {
        source = "/home/citc/.ssh/authorized_keys"
        destination = "/tmp/citc_authorized_keys"
    }

    provisioner "file" {
        source = var.ca_cert
        destination = "/tmp/CA.crt"
    }

    provisioner "file" {
        source = "/etc/munge/munge.key"
        destination = "/tmp/munge.key"
    }

    provisioner "file" {
        sources = [
          "/home/slurm/ssh_host_ecdsa_key",
          "/home/slurm/ssh_host_ecdsa_key.pub",
          "/home/slurm/ssh_host_rsa_key",
          "/home/slurm/ssh_host_rsa_key.pub",
          "/home/slurm/ssh_host_ed25519_key",
          "/home/slurm/ssh_host_ed25519_key.pub",
        ]
        destination = "/tmp/"
    }

    provisioner "shell" {
        inline = [
            "sudo mv /tmp/ssh_host_* /etc/ssh/",
            "sudo chmod 600 /etc/ssh/ssh_host_*",
            "sudo chmod 644 /etc/ssh/ssh_host_*.pub",
        ]
    }

    provisioner "shell" {
        script = "/etc/citc/packer/prepare_ansible.sh"
    }

    provisioner "ansible" {
        playbook_file = "/root/citc-ansible/compute.yml"
        groups = ["compute"]
        user = var.ssh_username
    }

    provisioner "shell" {
        script = "/home/citc/compute_image_extra.sh"
    }
}
