"""
    This script is part of pymaid (http://www.github.com/schlegelp/pymaid).
    Copyright (C) 2017 Philipp Schlegel

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along
"""

try:
   from pymaid import get_3D_skeleton, get_user_list, get_node_user_details, get_contributor_statistics
except:
   from pymaid.pymaid import get_3D_skeleton, get_user_list, get_node_user_details, get_contributor_statistics

import logging
import pandas as pd

#Set up logging
module_logger = logging.getLogger(__name__)
module_logger.setLevel(logging.INFO)

if not module_logger.handlers:
  #Generate stream handler
  sh = logging.StreamHandler()
  sh.setLevel(logging.DEBUG)
  #Create formatter and add it to the handlers
  formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
  sh.setFormatter(formatter)
  module_logger.addHandler(sh)

def get_user_contributions( skids, remote_instance ):
	"""
	Takes a list of skeleton IDs and returns nodes and synapses contributed by each user.
	This is essentially a wrapper for pymaid.get_contributor_statistics() - if you are 
	also interested in e.g. construction time, review time, etc. you may want to consider
	using pymaid.get_contributor_statistics() instead.

	Parameters:
	-----------
	skids : 			single or list of skeleton IDs
	remote_instance :	Catmaid Instance
	

	Returns:
	-------
	pandas DataFrame

		user   nodes   presynapses   postsynapses
	0
	1
	2
	"""

	user_list = get_user_list( remote_instance ).set_index('id')

	cont = get_contributor_statistics( skids, remote_instance, separate = False ).ix[0]

	all_users = set( list( cont.node_contributors.keys() ) + list ( cont.pre_contributors.keys() ) + list ( cont.post_contributors.keys() ) )

	stats = { 
				'nodes' : { u : 0 for u in all_users },
				'presynapses' : { u : 0 for u in all_users },
				'postsynapses' : { u : 0 for u in all_users }								
			}

	for u in cont.node_contributors:
		stats[ 'nodes' ][ u ] = cont.node_contributors[u]
	for u in cont.pre_contributors:
		stats[ 'presynapses' ][ u ] = cont.pre_contributors[u]
	for u in cont.post_contributors:
		stats[ 'postsynapses' ][ u ] = cont.post_contributors[u]

	return pd.DataFrame( [ [  user_list.ix[ int(u) ].last_name, stats['nodes'][u] , stats['presynapses'][u], stats['postsynapses'][u] ] for u in all_users ] , columns = [ 'user', 'nodes' ,'presynapses', 'postsynapses' ] ).sort_values('nodes', ascending = False).reset_index()

def get_time_invested( skids, remote_instance, interval = 1, minimum_actions = 1 ):
	"""
	Takes a list of skeleton IDs and calculates the time each user has spent working
	on this set of neurons.

	Parameters:
	-----------
	skids : 			single or list of skeleton IDs
	remote_instance :	Catmaid Instance
	interval :			integer (default = 1)
						size of the bins in minutes
	minimum_actions :   integer (default = 1)
						minimum number of actions per bin to be counted as active

	Returns:
	-------
	pandas DataFrame

		user   total   creation   edition   review
	0
	1
	2

	Values represent minutes. Creation/Edition/Review can overlap! This is why total 
	time spent is < creation + edition + review.

	Please note that this does currently not take placement of postsynaptic nodes
	into account!
	"""

	#Need this later for pandas TimeGrouper
	bin_width = '%iMin' % interval

	user_list = get_user_list( remote_instance ).set_index('id')

	skdata = get_3D_skeleton( skids, remote_instance = remote_instance )

	#Extract connector and node IDs
	node_ids = []
	connector_ids = []
	for n in skdata.itertuples():
		node_ids += n.nodes.treenode_id.tolist()
		connector_ids += n.connectors.connector_id.tolist()

	node_details = get_node_user_details( node_ids + connector_ids, remote_instance = remote_instance )		

	#Dataframe for creation (i.e. the actual generation of the nodes)
	creation_timestamps = pd.DataFrame( node_details[ [ 'user' , 'creation_time' ]  ].values, columns = [ 'user' , 'timestamp' ] )
	
	#Dataframe for edition times
	edition_timestamps = pd.DataFrame( node_details[ [ 'editor' , 'edition_time' ]  ].values, columns = [ 'user' , 'timestamp' ] )
	
	#Generate dataframe for reviews	
	reviewers  = [ u for l in node_details.reviewers.tolist() for u in l ]
	timestamps  = [ ts for l in node_details.review_times.tolist() for ts in l ]
	review_timestamps = pd.DataFrame( [ [ u, ts ] for u, ts in zip (reviewers, timestamps ) ] , columns = [ 'user', 'timestamp' ] )

	#Merge all timestamps
	all_timestamps = pd.concat( [creation_timestamps , edition_timestamps, review_timestamps ], axis = 0)

	stats = { 
				'total' : { u : 0 for u in all_timestamps.user.unique() },
				'creation' : { u : 0 for u in all_timestamps.user.unique() },
				'edition' : { u : 0 for u in all_timestamps.user.unique() },
				'review' : { u : 0 for u in all_timestamps.user.unique() }
				}

	#Get total time spent
	for u in all_timestamps.user.unique():
		stats['total'][u] += sum( all_timestamps[ all_timestamps.user == u ].timestamp.to_frame().set_index('timestamp', drop = False ).groupby( pd.TimeGrouper( freq = bin_width ) ).count().values >= minimum_actions )[0] * interval
	#Get reconstruction time spent
	for u in creation_timestamps.user.unique():		
		stats['creation'][u] += sum ( creation_timestamps[ creation_timestamps.user == u ].timestamp.to_frame().set_index('timestamp', drop = False ).groupby( pd.TimeGrouper( freq = bin_width ) ).count().values >= minimum_actions )[0] * interval
	#Get edition time spent
	for u in edition_timestamps.user.unique():
		stats['edition'][u] += sum ( edition_timestamps[ edition_timestamps.user == u ].timestamp.to_frame().set_index('timestamp', drop = False ).groupby( pd.TimeGrouper( freq = bin_width ) ).count().values >= minimum_actions )[0] * interval
	#Get time spent reviewing
	for u in review_timestamps.user.unique():
		stats['review'][u] += sum ( review_timestamps[ review_timestamps.user == u ].timestamp.to_frame().set_index('timestamp', drop = False ).groupby( pd.TimeGrouper( freq = bin_width ) ).count().values >= minimum_actions )[0] * interval	

	module_logger.info('Done! Use e.g. plotly to generate a plot: \n stats = get_time_invested( skids, remote_instance ) \n fig = { "data" : [ { "values" : stats.total.tolist(), "labels" : stats.user.tolist(), "type" : "pie" } ] } \n plotly.offline.plot(fig) ')
 
	return pd.DataFrame( [ [  user_list.ix[ u ].last_name, stats['total'][u] , stats['creation'][u], stats['edition'][u], stats['review'][u] ] for u in all_timestamps.user.unique() ] , columns = [ 'user', 'total' ,'creation', 'edition', 'review' ] ).sort_values('total', ascending = False).reset_index()