#!/usr/bin/python                                                                                                                                                                                                    

#Author: Alain Lefebvre <alain.lefebvre@mindgeek.com>     

import sys, subprocess, json, paramiko, os, time, urllib2, yaml, codecs, re
import pprint as pp


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


	def set_config(self, conf):

		# If only a config filename is passed and the file exists, load it as the config
		if isinstance(conf, str):
			if not os.path.isfile(conf):
				print "Config file {0} not found!".format(conf)
				sys.exit(0)
			else:
				with open(conf, 'r') as content_file:
	    				self.config = json.loads(content_file.read())

		# Otherwise, use the specific config dict that was passed
		else:
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
				self._ssh_connection.connect(self.config['puppet_hostname'], username=self.config['username'], pkey=rsa_key)

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
				merged_properties = dict(merged_properties, **properties[hf])

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


	if len(sys.argv) >= 2 and sys.argv[1] == '-h':
		print "Usage: ./hiera-visualize [SERVER_FQDN]\n"
		sys.exit(0)

	print ""

	hv = HieraAggregator()
	hv.set_config('config.json')

	# Get the list of nodes on the given puppet master
	if len(sys.argv) == 1:
		
		result = {}
		print "NOTICE: fetching node list from puppet master {0}..".format(hv.config['puppet_hostname'])
		nl = hv.query_facter({'query_type': 'node_list'})
		total_nodes = len(nl)
		print "NOTICE: {} nodes total".format(total_nodes)
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
		print "NOTICE: fetching node facts for {}..".format(sys.argv[1])
		facts = hv.query_facter({'query_type': 'node_facts', 'fqdn': sys.argv[1]})	
		# Build a final merged list of all the config data to be applied on this host
		chu = hv.build_config_hierarchy(facts, True)
		hv.show_hierarchy_multi({sys.argv[1]: chu})

	



