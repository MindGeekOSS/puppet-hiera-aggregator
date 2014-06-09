puppet-hiera-aggregator
=======================
A python class to extract the config parameters from a hiera hierarchy for a given puppet agent.

##Description
------------------------------------

In some cases, you may have multiple levels of Hiera hierarchy for your puppet nodes.  This tool allows you to easily find out which level of the hierarchy your node is getting config data.  The end result is a final config which would be the end result for a puppet run.


##Python Dependencies:
------------------------------------
- paramiko
- urllib2 
- yaml


##Config File:
------------------------------------

- Rename the config file to config.json and set the appropriate values


##Usage:
------------------------------------

- Example: Get the combined configs for each server connected to a puppet master:
`python hiera-aggregator.py --puppetmaster [PUPPET_MASTER_HOSTNAME]`

- Example: For given server, x.mydomain.com, get the combined configs and determine where the variable "users" is overridden:
`python hiera-aggregator.py --puppetmaster [PUPPET_MASTER_HOSTNAME --hostname x.mydomain.com --tracevar users` 

** A report is written to file for each node containing the final merged Hiera config

###Additional flags:
------------------------------------
`--ssh_user [USERNAME]`  --> Username to use for ssh connection to puppet master

`--ssh_key [PATH_TO_PRIVATE_KEY]`   --> Private key to use for ssh auth

`--hiera_file_dir [HIERA_FILES_PATH]`  --> Location where all hiera files are located

`--hiera_config [HIERA_CONFIG_PATH]`  --> Full path to puppet hiera config

