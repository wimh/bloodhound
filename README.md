# Apache Bloodhound

## vagrant deployment

The directory `installer/vagrant.puppet` contains a installation script for Apache Bloodhound which uses Vagrant and Puppet for deployment. To use it, first install [Vagrant](1) and [VirtualBox](2). You can also use the packages supplied by your distribution, For example on Debian you can use: 

    apt-get install virtualbox-qt virtualbox-dkms vagrant

Note that you don't need to install puppet. The deployment takes place on the virtual machine. In this case a base box from [Ubuntu Cloud Images](3) is used, this includes a pre-installed version of puppet.

If you use Windows, you have to disable the core.autocrlf first. In particular the PostgreSQL module for puppet will fail with strange errors if you don't. 

    git config --global core.autocrlf false

Don't forget to initialize and update the git submodules. All modules used by puppet are included in this repo as a submodule;

    git submodule init
    git submodule update

To start change to the vagrant.puppet and start vagrant:

    cd installer/vagrant.puppet
    vagrant up

After the provisioning has been finished, you can access the Bloodhound installation in your webbrowser at [http://localhost:8080/](http://localhost:8080/).

 [1]: https://www.vagrantup.com/downloads
 [2]: https://www.virtualbox.org/wiki/Downloads
 [3]: https://cloud-images.ubuntu.com/

