#
# Script to install CernVM-FS on CentOS 8 host,
# and add configuration to access the  European Environment for Scientific Software Installations (EESSI)
# (see https://eessi.github.io/docs)
#

set -eu

# install CernVM-FS
sudo dnf install -y  https://ecsft.cern.ch/dist/cvmfs/cvmfs-release/cvmfs-release-latest.noarch.rpm
sudo dnf install -y cvmfs

# install CernVM-FS configuration for EESSI
sudo dnf install -y https://github.com/EESSI/filesystem-layer/releases/download/v0.2.3/cvmfs-config-eessi-0.2.3-1.noarch.rpm

# configure CernVM-FS (no proxy, 10GB quota for CernVM-FS cache)
sudo bash -c "echo 'CVMFS_HTTP_PROXY=DIRECT' > /etc/cvmfs/default.local"
sudo bash -c "echo 'CVMFS_QUOTA_LIMIT=10000' >> /etc/cvmfs/default.local"
sudo cvmfs_config setup
