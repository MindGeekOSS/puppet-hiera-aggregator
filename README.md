puppet-hiera-aggregator
=======================
A python class to extract the config parameters from a hiera hierarchy for a given puppet agent.

##Description
=======================

In some cases, you may have multiple levels of Hiera hierarchy for your puppet nodes.  This tool allows you to easily find out which level of the hierarchy your node is getting config data.  The end result is a final config which would be the end result for a puppet run.


##Python Dependencies:
=======================
- paramiko
- urllib2 
- yaml


##Config File:
=======================

- Rename the config file to config.json and set the appropriate values


##Usage:
=======================

`python hiera-visualize.py [SERVER_FQDN]`

- Note that the **[SERVER_FQDN]** parameter is optional. If specified, only the report for that host will be compiled.
- A report is written to file for each node containing the final merged Hiera config
