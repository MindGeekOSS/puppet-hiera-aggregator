#!/usr/bin/python                                                                                                                                                                                                    

#Author: Alain Lefebvre <alain.lefebvre@mindgeek.com>     

import sys, subprocess, json, paramiko, os, time, urllib2, yaml, codecs, re, argparse, types
import pprint as pp
from collections import defaultdict


class HieraAggregator:

	config = {}
	puppet_api_uri = {}
	hierarchy = {}
	_ssh_connection = None

	def __init__(self):

		self.puppet_api_uri = {
			'node_list': '/v3/nodes',
			'node_facts': '/v3/nodes/{0}/facts',
		}


	def load_config(self, filename):

		if isinstance(filename, str):
			if not os.path.isfile(filename):
				print "Config file {0} not found!".format(filename)
				sys.exit(0)
			else:
				with open(filename, 'r') as content_file:
	    				return json.loads(content_file.read())		

	def set_config(self, conf):


		self.config['puppetdb_api'] = conf['puppetdb_api']
		if 'use_ssh' in conf and int(conf['use_ssh']) == 1:
			self.config['use_ssh'] = 1
			self.config['private_key_path'] = conf['private_key_path']
			self.config['username'] = conf['username']
		else:
			self.config['use_ssh'] = 0	

		self.config['puppet_hostname'] = conf['puppet_hostname']
		self.config['hiera_local_file_dir'] = conf['hiera_local_file_dir']
		self.config['hiera_config'] = conf['hiera_config']

		# Remove the trailing slash if it exists
		if self.config['puppetdb_api'].endswith('/'):
				self.config['puppetdb_api'] = self.config['puppetdb_api'][:-1]

		# Extract the Hiera hierarchy
		self.compute_hierarchy(self.config['hiera_config'])
		

	def query_facter(self, params):


		# Set the proper puppetdb API URI
		if params['query_type'] == 'node_list':
			facter_query_url = self.config['puppetdb_api']+self.puppet_api_uri[params['query_type']]

		elif params['query_type'] == 'node_facts':
			facter_query_url = self.config['puppetdb_api']+self.puppet_api_uri[params['query_type']].format(params['fqdn'])

		# Now fetch the data either via SSH or HTTP		
		if int(self.config['use_ssh']) == 1:

			if self._ssh_connection == None:
				self._ssh_connection = paramiko.SSHClient()
				self._ssh_connection.set_missing_host_key_policy(paramiko.AutoAddPolicy())
				rsa_key = paramiko.RSAKey.from_private_key_file(self.config['private_key_path'])
				self._ssh_connection.connect(self.config['puppet_hostname'], username=self.config['username'], pkey=rsa_key, timeout=5, look_for_keys=True)

			stdin, stdout, stderr = self._ssh_connection.exec_command("curl -X GET {0}".format(facter_query_url))
			data = stdout.read()
			json_data = json.loads(data)
		else:
			response = urllib2.urlopen(facter_query_url)
			body = response.read()
			json_data = json.loads(data)
	
		# Simplify the facts into a simple query
		if params['query_type'] == 'node_facts':
			tmp = {}
			for e in json_data:
				tmp[e['name']] = e['value']	
			json_data = tmp		

		elif params['query_type'] == 'node_list':
			tmp = []
			for e in json_data:
				tmp.append(e['name'])
			json_data = tmp		
		
		return json_data
		

	def merge_config(self, base, override, current_config):

		# store a copy of the base config, but overwrite with any of override's values     
		merged = dict(base,**override)
		xkeys = base.keys()

		if self._tracevar != None:
			if self._tracevar in override and self._tracevar in base:
				print "\tNOTICE: {0} overriden by {1}".format(self._tracevar, current_config) 

		# if the value of merged[key] was overwritten with y[key]'s value           
		# then we need to put back any missing x[key] values                        
		for key in xkeys:
			# If this key is a dictionary, then execute the merge function on it again                                 
			if type(base[key]) is types.DictType and override.has_key(key):
			    merged[key] = self.merge_config(base[key],override[key], current_config)

		return merged


	def compute_hierarchy(self, hiera_yaml_config):

		f = open(hiera_yaml_config)
		dataMap = yaml.load(f)
		f.close()
		cleaned = []

		for v in dataMap[':hierarchy']:
			parts = v.split('/')
			if len(parts) == 2:
				matches = re.findall(r'\%{::([a-zA-Z_]+)}', parts[len(parts)-1], re.M|re.I)
				if matches:
					cleaned.append({'group': parts[0], 'facts': matches})		
			else:
				cleaned.append({'group': parts[0]})		

		# Set items in order of least precedence (smaller index has less precedence)
		self.hierarchy = list(reversed(cleaned))


	def build_config_hierarchy(self, facts, merge=False):

		properties = {}
		merged_properties = {}
		order = []

		file_path = "{0}".format(self.config['hiera_local_file_dir'])

		for lvl in self.hierarchy:

			if 'facts' in lvl:
				fact_vals = []
				for f in lvl['facts']:
					if f in facts:
						fact_vals.append(facts[f])

				hiera_file = '{0}/{1}.json'.format(lvl['group'], '-'.join(fact_vals))  
			else:
				hiera_file = '{0}.json'.format(lvl['group'])  

			full_path = "{0}/{1}".format(file_path, hiera_file) 	
			if os.path.isfile(full_path):
				with open(full_path) as data_file: 
					properties[hiera_file] = json.load(data_file)
					order.append(hiera_file)	


		# If the option to merge the properties is True, then merge them before returning them
		if merge == True:
			for hf in order:
				merged_properties = self.merge_config(merged_properties, properties[hf], hf)
			return (order, merged_properties)
		else:
			return (order, properties)



	def show_hierarchy_multi(self, results):


		# was (prop_order, properties)
		for i in results:
			lvl = 1
			out = []
			prop_order, properties = results[i]

			print "Host:", i

			for k in prop_order:
				tabs = u'\t'*(lvl-1)
				out.append(u"{0}\u21B3 Level {1} = {2}".format(tabs, lvl, prop_order[lvl-1]))
				lvl+=1

			print '\n'.join(out)

			file_name = "hv-report_{0}.txt".format(i)
			fo = codecs.open(file_name, "wb", "utf-8")
			fo.write(json.dumps(properties, indent=4, sort_keys=True))	
			fo.close()

			print "\nResults saved to {0}\n".format(file_name)	
			print "-"*40
		

if __name__ == "__main__":


	parser = argparse.ArgumentParser()
	parser.add_argument('-pm', '--puppetmaster', help='Hostname or IP of the puppet master to query', default='', required=False)
	parser.add_argument('-hn', '--hostname', help='Name of the server for which to compile the hiera config', default='', required=False)
	parser.add_argument('-c', '--config', help='Use a config for the necessary parameters', default='', required=False)
	parser.add_argument('-t', '--tracevar', help='Trace how a specific var is overridden', default='', required=False)
	tmp_args = vars(parser.parse_args())
	args = {}
	for a in tmp_args:
		if tmp_args[a] != '':
			args[a] = tmp_args[a]

	print ""

	hv = HieraAggregator()

	if 'config' in args:
		conf = hv.load_config(args['config'])
	else:
		conf = hv.load_config('config.json')

	if 'puppetmaster' in args and args['puppetmaster'] != '':
		conf['puppet_hostname'] = args['puppetmaster']		

	if 'hostname' in args and args['hostname'] != '':
		conf['hostname'] = args['hostname']		

	if 'tracevar' in args and args['tracevar'] != '':
		hv._tracevar = args['tracevar']		

	hv.set_config(conf)

	# Get the list of nodes on the given puppet master
	if len(args) == 1:
		
		result = {}
		print "NOTICE: fetching node list from puppet master {0}".format(conf['puppet_hostname'])
		nl = hv.query_facter({'query_type': 'node_list'})
		total_nodes = len(nl)
		print "NOTICE: {0} nodes total".format(total_nodes)
		print "NOTICE: fetching individual node facts.."
		i=1

		for node in nl:
			# Get the node facts
			facts = hv.query_facter({'query_type': 'node_facts', 'fqdn': node})
			# Build a final merged list of all the config data to be applied on this host
			chu = hv.build_config_hierarchy(facts, True)
			result[node] = chu
			sys.stdout.write("\r%d of %d nodes complete" % (i, total_nodes))
    			sys.stdout.flush()
			i+=1

		print "-"*40

		hv.show_hierarchy_multi(result)

	else:
		print "NOTICE: fetching node facts from puppet master {0} for {1}".format(conf['puppet_hostname'], conf['hostname'])
		facts = hv.query_facter({'query_type': 'node_facts', 'fqdn': conf['hostname']})	
		# Build a final merged list of all the config data to be applied on this host
		print "NOTICE: Tracing config var '{0}'".format(hv._tracevar) 
		chu = hv.build_config_hierarchy(facts, True)
		hv.show_hierarchy_multi({conf['hostname']: chu})

	



