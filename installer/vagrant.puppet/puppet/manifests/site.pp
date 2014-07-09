# location of bloodhound source root directory
$bhsrc="/bloodhound"

$bhroot="/opt/bloodhound"
$bhenvironments="${bhroot}/environments"
$bhvirtualenv="${bhroot}/python-virtualenv"
$bhwww="${bhroot}/www"

$username='bloodhound'

$mainenvironment='main'
$defaultproductprefix='@'

exec { 'apt-get update':
  path => '/usr/bin',
  onlyif => "/bin/sh -c '[ ! -f /var/cache/apt/pkgcache.bin ] || /usr/bin/find /etc/apt/* -cnewer /var/cache/apt/pkgcache.bin | /bin/grep . > /dev/null'",
}

Exec["apt-get update"] -> Package <| |>

package { ['vim', 'curl', 'nmap', 'python-psycopg2', 'subversion', 'libapache2-mod-wsgi', 'apache2-utils', 'less', 'git']:
  ensure => present,
}


# avoid owner changing to root causing rerun of pip each time it is provisioned
file { "${bhsrc}/installer/requirements.txt":
  ensure  => present,
  replace => false,
}

class { 'python':
  version    => 'system',
  virtualenv => true,
}

python::virtualenv { "${bhvirtualenv}":
  ensure       => present,
  requirements => "${bhsrc}/installer/requirements.txt",
  venv_dir     => "${bhvirtualenv}",
  cwd          => "${bhsrc}/installer",
}

exec { 'create bloodhound env':
  command     => "python bloodhound_setup.py --environments_directory=${bhenvironments} -d sqlite --project=${mainenvironment} --default-product-prefix=${defaultproductprefix} --admin-user=admin --admin-password=admin",
  cwd         => "${bhsrc}/installer",
  path        => "${bhvirtualenv}/bin",
  require     => Python::Virtualenv["${bhvirtualenv}"],
  creates     => "${bhenvironments}",
}

exec { 'create bloodhound deploy':
  command     => "trac-admin ${bhenvironments}/$mainenvironment/ deploy ${bhwww}",
  cwd         => "${bhvirtualenv}/bin",
  path        => "${bhvirtualenv}/bin",
  require     => Exec['create bloodhound env'],
  creates     => "${bhwww}",
}

user { "${username}":
  ensure => present,
  shell => '/bin/false',
  managehome => true,
}

file { "${bhenvironments}":
  mode => 775,
  recurse => true,
  require => Exec['create bloodhound env'],
}

exec { 'chown.www':
  command => "chown -R ${username}.www-data ${bhenvironments} ${bhwww} ${bhvirtualenv}",
  path    => "/usr/bin:/usr/sbin:/bin",
  require => [Exec['create bloodhound deploy'], User["${username}"]],
}

exec { 'chmod.www':
  command => "chmod -R ug+r ${bhenvironments} ${bhwww} ${bhvirtualenv}",
  path    => "/usr/bin:/usr/sbin:/bin",
  require => Exec['chown.www'],
}


class {'apache':}

apache::mod { 'auth_digest': }
include 'apache::mod::wsgi'

apache::listen { '8080': }

apache::vhost { 'bloodhound8080':
  servername                  => 'localhost',
  port                        => '8080',
  docroot                     => '/var/www', # docroot is a required parameter but we don't need it
  log_level                   => 'warn',
  wsgi_script_aliases         => { '/' => "${bhwww}/cgi-bin/trac.wsgi" },
  wsgi_daemon_process         => 'bh_tracker8080',
  wsgi_daemon_process_options => {
      user         => "${username}",
      python-path  => "${bhvirtualenv}/lib/python2.7/site-packages",
  },
  wsgi_process_group          => 'bh_tracker8080',
  wsgi_application_group      => '%{GLOBAL}',
  directories => [
    { 
      path                   => "${bhwww}/cgi-bin",
      #wsgi_process_group     => 'bh_tracker8080',
      #wsgi_application_group => '%{GLOBAL}',
      order                  => 'deny,allow', 
      allow                  => 'from all', 
    },
    #{ 
    #  provider           => 'locationmatch',
    #  path               => '^/login$',
    #  auth_type          => 'Digest',
    #  auth_name          => 'bloodhound',
    #  auth_digest_domain => '/',
    #  auth_user_file     => "${bhenvironments}/$mainenvironment/bloodhound.htdigest",
    #  auth_require       => 'valid-user'
    #},
  ],
  require => Exec['chmod.www'],
}

#file { "/etc/apache2/sites-enabled/bloodhound.conf" :
#  content => template("bloodhound.conf.erb"),
#  require => Exec['chmod.www'],
#  notify  => Class[apache::service],
#}



