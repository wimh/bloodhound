# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


# location of bloodhound source root directory
$bhsrc="/bloodhound"

# http port used
# note that vagrant forwards ports to other ports on the host
$httpport='8080'

# username and password to login to the bloodhound website (with admin rights)
$bhuser='admin'
$bhpass='admin'

# default environment and default product prefix 
$mainenvironment='main'
$defaultproductprefix='@'

# database engine, choose between sqlite and postgres
# $dbtype='sqlite'
$dbtype='postgres'

# database name, user and password for postgres
$dbname='bloodhound'
$dbuser='bloodhound'
$dbpass='bloodhound'

# where to install
$bhroot="/opt/bloodhound"
$bhenvironments="${bhroot}/environments"
$bhvirtualenv="${bhroot}/python-virtualenv"
$bhwww="${bhroot}/www"

# linux user used to run website
$linuxuser='bloodhound'

# where the bloodhound installer is stored
$bhinstaller="${bhsrc}/installer"

# which requirements file is used (dev or normal)
# $requirementstxt='requirements-dev.txt'
$requirementstxt='requirements.txt'

# we use a generated requirements file, this filename will be used
$tempreqfile="${bhinstaller}/.requirements.txt.tmp"

# apt-get update only if required, but before any package is installed
exec { 'apt-get update':
  path => '/usr/bin',
  onlyif => "/bin/sh -c '[ ! -f /var/cache/apt/pkgcache.bin ] || /usr/bin/find /etc/apt/* -cnewer /var/cache/apt/pkgcache.bin | /bin/grep . > /dev/null'",
}

Exec["apt-get update"] -> Package <| |>

# some default handy packages, not required
#package { ['vim', 'curl', 'nmap', 'subversion', 'apache2-utils', 'less', 'git']:
#  ensure => present,
#}

user { $linuxuser:
  ensure => present,
  shell => '/bin/false',
  managehome => true,
}

class {'apache':}

class { 'python':
  version    => 'system',
  dev        => ($dbtype != 'sqlite'),
  pip        => true,
  virtualenv => true,
}

file { $bhroot:
  ensure => directory,
  owner  => $linuxuser,
  group  => $apache::params::group,
  require => [User[$linuxuser], Group[$apache::params::group]],
}

concat { $tempreqfile:
  ensure => present,
  owner  => 'vagrant',
  group  => 'vagrant',
}

concat::fragment { 'requirements.txt':
  target => $tempreqfile,
  source => "${bhinstaller}/${requirementstxt}",
  order  => '10',
}

python::virtualenv { $bhvirtualenv:
  ensure       => present,
  venv_dir     => $bhvirtualenv,
  requirements => $tempreqfile,
  owner        => $linuxuser,
  group        => $apache::params::group,
  cwd          => $bhinstaller,
  require      => File[$bhroot],
}

if $dbtype == 'postgres' {

  class { 'postgresql::server': }

  class { 'postgresql::lib::devel': }

  postgresql::server::db { $dbname:
    user     => $dbuser,
    password => postgresql_password($dbuser, $dbpass),
    encoding => 'UTF8',
  }

  # don't execute bloodhound_setup.py before the database is created
  Postgresql::Server::Db [ $dbname ] -> Exec['bloodhound_setup.py']

  # for postgres also use pgrequirements.txt which currently only contains psycopg2
  # note that psycopg2 requires the dev packages of postgres and python
  concat::fragment { 'pgrequirements.txt':
    target  => $tempreqfile,
    source  => "${bhinstaller}/pgrequirements.txt",
    order   => '20',
    require => [
                 Package[$postgresql::lib::devel::package_name],
                 Package[$python::install::pythondev],
    ],
  }
}

# be sure the prerequisites are met before running this command. 
# bloodhound_setup.py does not always set the exit code properly if something went wrong
exec { 'bloodhound_setup.py':
  command     => "python bloodhound_setup.py --environments_directory=${bhenvironments} --database-type=${dbtype} --project=${mainenvironment} --default-product-prefix=${defaultproductprefix} --user=${dbuser} --password=${dbpass} --admin-user=${bhuser} --admin-password=${bhpass}",
  returns     => [0],
  logoutput   => true,
  cwd         => $bhinstaller,
  path        => "${bhvirtualenv}/bin:/usr/bin:/usr/sbin:/bin",  # uses pg_dump which is stored in /usr/bin
  require     => Python::Virtualenv[$bhvirtualenv],
  creates     => "${bhenvironments}/$mainenvironment",
}

exec { 'trac-admin deploy':
  command     => "trac-admin ${bhenvironments}/$mainenvironment/ deploy ${bhwww}",
  cwd         => "${bhvirtualenv}/bin",
  path        => "${bhvirtualenv}/bin:/usr/bin:/usr/sbin:/bin",
  require     => Exec['bloodhound_setup.py'],
  creates     => $bhwww,
}

# set file permissions
file { $bhenvironments:
  mode    => 'ug+rw,o-w',
  owner   => $linuxuser,
  group   => $apache::params::group,
  recurse => true,
  require => [Exec['bloodhound_setup.py'], User[$linuxuser], Group[$apache::params::group]],
}

# set file permissions
file { $bhwww:
  mode    => 'ug+r,go-w',
  owner   => $linuxuser,
  group   => $apache::params::group,
  recurse => true,
  require => [Exec['trac-admin deploy'], User[$linuxuser], Group[$apache::params::group]],
}

apache::mod { 'auth_digest': }

include 'apache::mod::wsgi'

apache::listen { $httpport: }

apache::vhost { 'bloodhound':
  servername                  => 'localhost',
  port                        => $httpport,
  docroot                     => '/var/www', # docroot is a required parameter but we don't need it
  log_level                   => 'warn',
  wsgi_script_aliases         => { '/' => "${bhwww}/cgi-bin/trac.wsgi" },
  wsgi_daemon_process         => 'bh_tracker',
  wsgi_daemon_process_options => {
      user         => "${linuxuser}",
      python-path  => "${bhvirtualenv}/lib/python2.7/site-packages",
  },
  wsgi_process_group          => 'bh_tracker',
  wsgi_application_group      => '%{GLOBAL}',
  #directories => [
    #{ 
    #  provider           => 'locationmatch',
    #  path               => '^/login$',
    #  auth_type          => 'Digest',
    #  auth_name          => 'bloodhound',
    #  auth_digest_domain => '/',
    #  auth_user_file     => "${bhenvironments}/$mainenvironment/bloodhound.htdigest",
    #  auth_require       => 'valid-user'
    #},
  #],
  require => [File[$bhwww], User[$linuxuser]],
}


