#!/usr/bin/python                                                                                                                                                                                                    

#Author: Alain Lefebvre <alain.lefebvre@mindgeek.com>     

import sys, subprocess, json, paramiko, os, argparse, time, urllib2, yaml, codecs, re
import pprint as pp


class HieraVisualizer:

	config = {}
	puppet_api_uri = {}
	hierarchy = {}

	def __init__(self):

		self.puppet_api_uri = {
			'node_list': '/v3/nodes',
			'node_facts': '/v3/nodes/{0}/facts',
			'fact_list': '/v3/fact-names',
		}


	def set_config(self, conf):

		self.config['base_api_facts'] = conf['base_api_facts']
		if self.config['base_api_facts'].endswith('/'):
			self.config['base_api_facts'] = self.config['base_api_facts'][:-1]

		if 'use_ssh' in conf and int(conf['use_ssh']) == 1:
			self.config['use_ssh'] = 1
			self.config['private_key_path'] = conf['private_key_path']
			self.config['username'] = conf['username']
		else:
			self.config['use_ssh'] = 0	

		self.config['puppet_hostname'] = conf['puppet_hostname']
		self.config['hiera_local_file_dir'] = conf['hiera_local_file_dir']
		self.config['hiera_config'] = conf['hiera_config']

		# Extract the Hiera hierarchy
		self.compute_hierarchy(self.config['hiera_config'])
		

	def query_facter(self, params):


		# Set the proper puppetdb API URI
		if params['query_type'] == 'node_list':
			facter_query_url = self.config['base_api_facts']+self.puppet_api_uri[params['query_type']]

		elif params['query_type'] == 'node_facts':
			facter_query_url = self.config['base_api_facts']+self.puppet_api_uri[params['query_type']].format(params['fqdn'])

		# Now fetch the data either via SSH or HTTP		
		if int(self.config['use_ssh']) == 1:
			ssh = paramiko.SSHClient()
			ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
			rsa_key = paramiko.RSAKey.from_private_key_file(self.config['private_key_path'])
			ssh.connect(self.config['puppet_hostname'], username=self.config['username'], pkey=rsa_key)

			stdin, stdout, stderr = ssh.exec_command("curl -X GET {0}".format(facter_query_url))
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

			#print "Level:",lvl
			
			if 'facts' in lvl:
				fact_vals = []
				for f in lvl['facts']:
					fact_vals.append(facts[f])

				hiera_file = '{0}/{1}.json'.format(lvl['group'], '-'.join(fact_vals))  
			else:
				hiera_file = '{0}.json'.format(lvl['group'])  

			#print "File:",hiera_file

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


	def show_hierarchy(self, prop_order, properties):

		lvl = 1
		out = []
		merged_properties = {}

		for k in prop_order:
			tabs = u'\t'*(lvl-1)
			out.append(u"{0}\u21B3 Level {1} = {2}".format(tabs, lvl, prop_order[lvl-1]))
			if merged_properties == {}:
				merged_properties = properties[prop_order[lvl-1]];
			else:
				merged_properties = dict(merged_properties, **properties[prop_order[lvl-1]])
			lvl+=1


		out.append("\nTotal Hiera files used: {0}\n".format(len(prop_order)))
		out = '\n'.join(out)+"\n"

		file_name = "hv-report.txt"
		fo = codecs.open(file_name, "wb", "utf-8")
		fo.write(out);
		pp.pprint(json.dumps(merged_properties), stream=fo)		
		fo.close()
		
		print out
		print "\nResults saved to {0}\n".format(file_name)	

		

if __name__ == "__main__":

	if len(sys.argv) == 1 or (len(sys.argv) >= 2 and sys.argv[1] == '-h'):
		print "Usage: ./hiera-visualize [SERVER_FQDN]\n"
		sys.exit(0)

	print ""

	hv = HieraVisualizer()
	hv.set_config(
		{
			'use_ssh': 1,
			'base_api_facts': 'http://localhost:8080/',
			'private_key_path': '[PRIVATE_KEY_PATH]',
			'username': '[USERNAME]',
			'puppet_hostname': '[PUPPET_MASTER_HOSTNAME]',
			'hiera_local_file_dir': '[LOCAL_HIERA_DIR]',
			'hiera_config': '[LOCAL_HIERA_CONFIG]'
		}
	)

	# Get the list of nodes on the given puppet master
	#nl = hv.query_facter({'query_type': 'node_list'})

	# Collect all the node facts for the specific host 
	facts = hv.query_facter({'query_type': 'node_facts', 'fqdn': sys.argv[1]})

	# Build a final merged list of all the config data to be applied on this host
	chu = hv.build_config_hierarchy(facts, True)
	pp.pprint(chu[1])

	



