
$bhroot="/opt/bloodhound"
$bhenvironments="${bhroot}/environments"
$bhvirtualenv="${bhroot}/python-virtualenv"
$bhwww="${bhroot}/www"

$bhsrc="/bloodhound"
#$bhsrc="${bhroot}/src"

$username='bloodhound'

$mainenvironment='main'
$defaultproductprefix='@'

exec { 'localapt':
  command => "sed -i  's/us\\./nl./' /etc/apt/sources.list",
  path    => "/usr/bin:/usr/sbin:/bin",
  onlyif  => "/bin/grep -q 'us\\.' '/etc/apt/sources.list'",
  notify  => Exec["apt-get update"],
}

exec { 'apt-get update':
  path => '/usr/bin',
  onlyif => "/bin/sh -c '[ ! -f /var/cache/apt/pkgcache.bin ] || /usr/bin/find /etc/apt/* -cnewer /var/cache/apt/pkgcache.bin | /bin/grep . > /dev/null'",
}

Exec["apt-get update"] -> Package <| |>

package { ['vim', 'curl', 'nmap', 'python-psycopg2', 'subversion', 'libapache2-mod-wsgi', 'apache2-utils', 'less', 'git']:
  ensure => present,
}


file { "${bhroot}":
  ensure => 'directory',
}

# vagrant shares bloodhound directory as /bloodhound.
# we can use it directly or copy it to somewhere else first
if $bhsrc != '/bloodhound' {

  file { "${bhsrc}":
    ensure => 'directory',
    source  => '/bloodhound',
    recurse => true,
    require => File["${bhroot}"],
  }

  # separate define requirements.txt to avoid it gets overwritten by python::virtualenv
  # https://github.com/stankevich/puppet-python/issues/64
  file { "${bhsrc}/installer/requirements.txt":
    ensure  => present,
    source  => '/bloodhound/installer/requirements.txt',
    require => File["${bhsrc}"],
  }

  File["${bhsrc}/installer/requirements.txt"] -> Python::Virtualenv["${bhvirtualenv}"]
} 
else {

  # avoid owner changing to root causing rerun of pip each time it is provisioned
  file { "${bhsrc}/installer/requirements.txt":
    ensure  => present,
    replace => false,
  }

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



