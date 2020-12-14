#
# Script to install CernVM-FS on CentOS 8 host,
# and add configuration to access the  European Environment for Scientific Software Installations (EESSI)
# (see https://eessi.github.io/docs)
#

set -eu

# install CernVM-FS
if [[ $(arch) == "aarch64" ]]; then
    # no package available for CernVM-FS for CentOS 8 and aarch64 systems, so building from source...
    sudo dnf install -y cmake fuse-devel fuse3-devel fuse3-libs gcc-c++ libcap-devel libuuid-devel make openssl-devel patch python2 python3-devel unzip valgrind zlib-devel
    curl -OL https://github.com/cvmfs/cvmfs/archive/cvmfs-2.7.5.tar.gz
    tar xfz cvmfs-2.7.5.tar.gz
    cd cvmfs*2.7.5
    mkdir build
    cd build
    cmake ..
    make -j $(nproc)
    sudo make install

    sudo dnf install -y attr autofs
    sudo dnf install -y fuse

    # fuse3 must be around for building, but not at runtime (for CentOS 8);
    # causes failure to mount CernVM-FS filesystems (FUSE3 version is too old?)
    sudo dnf remove -y fuse3-libs fuse3-devel
else
    sudo dnf install -y https://ecsft.cern.ch/dist/cvmfs/cvmfs-release/cvmfs-release-latest.noarch.rpm
    sudo dnf install -y cvmfs
fi

# install CernVM-FS configuration for EESSI
sudo dnf install -y https://github.com/EESSI/filesystem-layer/releases/download/v0.2.3/cvmfs-config-eessi-0.2.3-1.noarch.rpm

# configure CernVM-FS (no proxy, 10GB quota for CernVM-FS cache)
sudo bash -c "echo 'CVMFS_HTTP_PROXY=DIRECT' > /etc/cvmfs/default.local"
sudo bash -c "echo 'CVMFS_QUOTA_LIMIT=10000' >> /etc/cvmfs/default.local"
sudo cvmfs_config setup
