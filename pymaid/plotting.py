#    This script is part of pymaid (http://www.github.com/schlegelp/pymaid).
#    Copyright (C) 2017 Philipp Schlegel
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along

""" Module contains functions to plot neurons in 2D and 3D.
"""

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import matplotlib.collections as mcollections
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Line3DCollection
from mpl_toolkits.mplot3d import proj3d
import matplotlib.colors as mcl

import random
import colorsys
import logging
import png

import networkx as nx

from pymaid import morpho, graph, core, fetch, connectivity, graph_utils, utils

from tqdm import tqdm
if utils.is_jupyter():
    from tqdm import tqdm_notebook, tnrange
    tqdm = tqdm_notebook
    trange = tnrange

import plotly.plotly as py
import plotly.offline as pyoff
import plotly.graph_objs as go

import vispy
from vispy import scene
from vispy.geometry import create_sphere
from vispy.gloo.util import _screenshot

try:
    # Try setting vispy backend to PyQt5
    vispy.use(app='PyQt5')
except:
    pass

import pandas as pd
import numpy as np
import random
import math
from colorsys import hsv_to_rgb

module_logger = logging.getLogger(__name__)
module_logger.setLevel(logging.INFO)
if len( module_logger.handlers ) == 0:
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG)
    # Create formatter and add it to the handlers
    formatter = logging.Formatter(
                '%(levelname)-5s : %(message)s (%(name)s)')
    sh.setFormatter(formatter)
    module_logger.addHandler(sh)

__all__ = ['plot3d','plot2d','plot1d','plot_network','clear3d','close3d','screenshot','get_canvas']


def screenshot(file='screenshot.png', alpha=True):
    """ Saves a screenshot of active 3D canvas.

    Parameters
    ----------
    file :      str, optional
                Filename
    alpha :     bool, optional
                If True, alpha channel will be saved
    """
    if alpha:
        mode = 'RGBA'
    else:
        mode = 'RGB'

    im = png.from_array(_screenshot(alpha=alpha), mode=mode)
    im.save(file)

    return

def get_canvas():
    """ Returns active vispy canvas and scale factor. Use this to add custom
    objects to neuron plots.

    Returns
    -------
    vispy.canvas, scale_factor

    Examples
    --------
    >>> from vispy import scene
    >>> # Get and plot neuron in 3d
    >>> n = pymaid.get_neuron(12345)
    >>> n.plot3d(color='red')
    >>> # Plot connector IDs
    >>> cn_ids = n.connectors.connector_id.values.astype(str)
    >>> cn_co = n.connectors[['x','y','z']].values
    >>> canvas, scale_factor = pymaid.get_canvas()
    >>> view = canvas.central_widget.children[0]
    >>> text = scene.visuals.Text( text=cn_ids,
    ...                             pos=cn_co*scale_factor)
    >>> view.add(text)
    """
    try:
        return globals()['canvas'], globals()['vispy_scale_factor']
    except:
        raise Exception('No canvas found.')


def clear3d():
    """ Clear 3D canvas.
    """
    try:
        canvas = globals()['canvas']
        canvas.central_widget.remove_widget(canvas.central_widget.children[0])
        canvas.update()
        globals().pop('vispy_scale_factor')
        del vispy_scale_factor
    except:
        pass


def close3d():
    """ Close existing 3D canvas (wipes memory).
    """
    try:
        canvas = globals()['canvas']
        canvas.close()
        globals().pop('canvas')
        globals().pop('vispy_scale_factor')
        del canvas
        del vispy_scale_factor
    except:
        pass

def _orthogonal_proj(zfront, zback):
    """ Function to get matplotlib to use orthogonal instead of perspective
    view.

    Usage:
    proj3d.persp_transformation = _orthogonal_proj
    """
    a = (zfront+zback)/(zfront-zback)
    b = -2*(zfront*zback)/(zfront-zback)
    # -0.0001 added for numerical stability as suggested in:
    # http://stackoverflow.com/questions/23840756
    return np.array([[1,0,0,0],
                        [0,1,0,0],
                        [0,0,a,b],
                        [0,0,-0.0001,zback]])


def plot2d(x, method='2d', *args, **kwargs):
    """ Generate 2D plots of neurons and neuropils. The main advantage of this
    is that you can save plot as vector graphics. *Important*: this function
    uses matplotlib which "fakes" 3D as it has only very limited control over
    layers. Therefore neurites aren't necessarily plotted in the right Z order
    which becomes especially troublesome when plotting a complex scene with
    lots of neurons criss-crossing. See the _method_ parameter for details.
    All methods use orthogonal projection.

    Parameters
    ----------
    x :               {skeleton IDs, core.CatmaidNeuron, core.CatmaidNeuronList, core.CatmaidVolume, np.ndarray}
                      Objects to plot::

                        - int is intepreted as skeleton ID(s)
                        - str is intepreted as volume name(s)
                        - multiple objects can be passed as list (see examples)
                        - numpy array of shape (n,3) is intepreted as scatter
    method :          {'2d','3d','3d_complex'}
                      Method used to generate plot. Comes in three flavours:
                        1. '2d' uses normal matplotlib. Neurons are plotted in
                           the order their are provided. Well behaved when
                           plotting neuropils and connectors. Always gives
                           frontal view.
                        2. '3d' uses matplotlib's 3D axis. Here, matplotlib
                           decide the order of plotting. Can chance perspective
                           either interacively or by code (see examples).
                        3. '3d_complex' same as 3d but each neuron segment is
                           added individually. This allows for more complex
                           crossing patterns to be rendered correctly. Slows
                           down rendering though.
    remote_instance : Catmaid Instance, optional
                      Need this too if you are passing only skids
    *args
                      See Notes for permissible arguments.
    **kwargs
                      See Notes for permissible keyword arguments.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> # 1. Plot two neurons and have plot2d download the skeleton data for you:
    >>> fig, ax = pymaid.plot2d( [12345, 45567] )
    >>> # 2. Manually download a neuron, prune it and plot it:
    >>> neuron = pymaid.get_neuron( [12345], rm )
    >>> neuron.prune_distal_to( 4567 )
    >>> fig, ax = pymaid.plot2d( neuron )
    >>> matplotlib.pyplot.show()
    >>> # 3. Plots neuropil in grey, and mushroom body in red:
    >>> neurop = pymaid.get_volume('v14.neuropil')
    >>> neurop.color = (.8,.8,.8)
    >>> mb = pymaid.get_volume('v14.MB_whole')
    >>> mb.color = (.8,0,0)
    >>> fig, ax = pymaid.plot2d(  [ 12346, neurop, mb ] )
    >>> matplotlib.pyplot.show()
    >>> # Change perspective
    >>> fig, ax = pymaid.plot2d( neuron, method='3d_complex' )
    >>> # Change view to lateral
    >>> ax.azim = 0
    >>> ax.elev = 0
    >>> # Change view to top
    >>> ax.azim = -90
    >>> ax.elev = 90
    >>> # Tilted top view
    >>> ax.azim = -135
    >>> ax.elev = 45
    >>> # Move camera closer (will make image bigger)
    >>> ax.dist = 5


    Returns
    --------
    fig, ax :      matplotlib figure and axis object

    Notes
    -----

    Optional ``*args`` and ``**kwargs``:

    ``connectors`` (boolean, default = True )
       Plot connectors (synapses, gap junctions, abutting)

    ``connectors_only`` (boolean, default = False)
       Plot only connectors, not the neuron.

    ``scalebar`` (int/float, default=False)
       Adds scale bar. Provide integer/float to set size of scalebar in um.
       For methods '3d' and '3d_complex', this will create an axis object.

    ``ax`` (matplotlib ax, default=None)
       Pass an ax object if you want to plot on an existing canvas.

    ``color`` (tuple/list/str, dict)
      Tuples/lists (r,g,b) and str (color name) are interpreted as a single
      colors that will be applied to all neurons. Dicts will be mapped onto
      neurons by skeleton ID.

    ``group_neurons`` (bool, default=False)
      If True, neurons will be grouped. Works with SVG export (not PDF).
      Does NOT work with method = '3d_complex'

    ``scatter_kws`` (dict, default = {})
      Parameters to be used when plotting points. Accepted keywords are:
      ``size`` and ``color``.

    See Also
    --------
    :func:`pymaid.plot3d`
            Use this if you want interactive, perspectively correct renders
            and if you don't need vector graphics as outputs.

    """

    _ACCEPTED_KWARGS = ['remote_instance','connectors','connectors_only',
                        'ax','color','view','scalebar','cn_mesh_colors',
                        'linewidth','cn_size','group_neurons', 'scatter_kws',
                        'figsize', 'linestyle']
    wrong_kwargs = [ a for a in kwargs if a not in _ACCEPTED_KWARGS ]
    if wrong_kwargs:
        raise KeyError('Unknown kwarg(s): {0}. Currently accepted: {1}'.format(','.join(wrong_kwargs), ','.join(_ACCEPTED_KWARGS) ))

    _METHOD_OPTIONS = ['2d','3d', '3d_complex']
    if method not in _METHOD_OPTIONS:
        raise ValueError('Unknown method "{0}". Please use either: {1}'.format(method, _METHOD_OPTIONS))

    # Set axis to plot for method '2d'
    axis1, axis2 = 'x', 'y'

    # Keep track of limits if necessary
    lim = []

    #Dotprops are currently ignored!
    skids, skdata, _dotprops, volumes, points = _parse_objects(x)

    remote_instance = kwargs.get('remote_instance', None)
    connectors = kwargs.get('connectors', True)
    connectors_only = kwargs.get('connectors_only', False)
    cn_mesh_colors = kwargs.get('cn_mesh_colors', False)
    ax = kwargs.get('ax', None)
    color = kwargs.get('color', None)
    scalebar = kwargs.get('scalebar', None)
    group_neurons = kwargs.get('group_neurons', False)

    scatter_kws = kwargs.get('scatter_kws', {})

    linewidth = kwargs.get('linewidth', .5)
    cn_size = kwargs.get('cn_size', 1)
    linestyle = kwargs.get('linestyle','-')

    remote_instance = fetch._eval_remote_instance(remote_instance)

    if skids:
        skdata += fetch.get_neuron(skids, remote_instance, connector_flag=1,
                                   tag_flag=0, get_history=False, get_abutting=True)

    if not color and (skdata.shape[0] + _dotprops.shape[0])>0:
        cm = _random_colors(
            skdata.shape[0] + _dotprops.shape[0], color_space='RGB', color_range=1)
        colormap = {}

        if not skdata.empty:
            colormap.update(
                {str(n): cm[i] for i, n in enumerate(skdata.skeleton_id.tolist())})
        if not _dotprops.empty:
            colormap.update({str(n): cm[i + skdata.shape[0]]
                             for i, n in enumerate(_dotprops.gene_name.tolist())})
    elif isinstance(color, dict):
        colormap = {n: tuple(color[n]) for n in color}
    elif isinstance(color,(list,tuple)):
        colormap = {n: tuple(color) for n in skdata.skeleton_id.tolist()}
    elif isinstance(color,str):
        color = tuple( [ int(c *255) for c in mcl.to_rgb(color) ] )
        colormap = {n: color for n in skdata.skeleton_id.tolist()}
    elif (skdata.shape[0] + _dotprops.shape[0])>0:
        raise ValueError('Unable to interpret colors of type "{0}"'.format(type(color)))

    # Make sure axes are projected orthogonally
    if method in ['3d','3d_complex']:
        proj3d.persp_transformation = _orthogonal_proj

    if not ax:
        if method =='2d':
            fig, ax = plt.subplots(figsize= kwargs.get('figsize', (8, 8) ) )
        elif method in ['3d','3d_complex']:
            fig = plt.figure(figsize= kwargs.get('figsize', plt.figaspect(1)*1.5) )
            ax = fig.gca(projection='3d')
            # Set projection to orthogonal
            # This sets front view
            ax.azim = -90
            ax.elev = 0
        ax.set_aspect('equal')
    else:
        if not isinstance(ax, mpl.axes.Axes):
            raise TypeError('Ax must be of type <mpl.axes.Axes>, not <{0}>'.format(type(ax)))
        fig = None #we don't really need this
        if method in ['3d','3d_complex'] and ax.name != '3d':
            raise TypeError('Axis must be 3d.')
        elif method == '2d' and ax.name == '3d':
            raise TypeError('Axis must be 2d.')

    if volumes:
        for v in volumes:
            c = v.get('color', (0.9, 0.9, 0.9))

            if not isinstance(c, tuple):
                c = tuple(c)

            if sum(c[:3]) > 3:
                c = np.array(c)
                c[:3] = np.array(c[:3]) / 255

            if method == '2d':
                vpatch = mpatches.Polygon(
                v.to_2d(view='{0}{1}'.format(axis1,axis2), invert_y=True), closed=True, lw=0, fill=True, fc=c, alpha=1)
                ax.add_patch(vpatch)
            elif method in ['3d','3d_complex']:
                verts = np.vstack( v['vertices'] )
                # Invert y-axis
                verts[:,1] *= -1
                # Add alpha
                if len(c) == 3:
                    c = ( c[0],c[1],c[2],.1 )
                ts = ax.plot_trisurf( verts[:,0],verts[:,2],v['faces'], verts[:,1], label=v['name'], color=c)
                ts.set_gid( v['name'] )
                # Keep track of limits
                lim.append( verts.max(axis=0) )
                lim.append( verts.min(axis=0) )

    # Create lines from segments
    for i, neuron in enumerate(tqdm(skdata.itertuples(), desc='Plotting', total=skdata.shape[0], leave=False)):
        this_color = colormap[ neuron.skeleton_id ]

        if not connectors_only:
            soma = neuron.nodes[neuron.nodes.radius > 1]

            # Now make traces (invert y axis)
            coords = _segments_to_coords(neuron, neuron.segments, modifier=(1,-1,1))

            if method == '2d':
                # We have to add (None,None,None) to the end of each slab to
                # make that line discontinuous there
                coords = np.vstack( [ np.append(t, [[None] * 3], axis=0) for t in coords] )

                this_line = mlines.Line2D( coords[:,0], coords[:,1], lw=linewidth, ls=linestyle,alpha=.9, color=this_color,
                                    label='%s - #%s' % (neuron.neuron_name, neuron.skeleton_id) )

                ax.add_line(this_line)

                for n in soma.itertuples():
                    s = mpatches.Circle((int(n.x), int(-n.y)), radius=n.radius, alpha=.9,
                                        fill=True, color=this_color, zorder=4, edgecolor='none')
                    ax.add_patch(s)

            elif method in ['3d','3d_complex']:
                # For simple scenes, add whole neurons at a time -> will speed up rendering
                if method == '3d':
                    lc = Line3DCollection( [ c[:,[0,2,1]] for c in coords ], color = this_color,
                                           label=neuron.neuron_name,
                                           lw=linewidth,
                                           linestyle=linestyle)
                    if group_neurons:
                        lc.set_gid( neuron.neuron_name )
                    ax.add_collection3d( lc )
                # For complex scenes, add each segment as a single collection -> help preventing Z-order errors
                elif method =='3d_complex':
                    for c in coords:
                        lc = Line3DCollection( [c[:,[0,2,1]] ], color = this_color,
                                               lw=linewidth,
                                               linestyle=linestyle )
                        if group_neurons:
                            lc.set_gid( neuron.neuron_name )
                        ax.add_collection3d( lc )

                coords = np.vstack(coords)
                lim.append( coords.max(axis=0) )
                lim.append( coords.min(axis=0) )

                for n in soma.itertuples():
                    resolution = 20
                    u = np.linspace(0, 2 * np.pi, resolution)
                    v = np.linspace(0, np.pi, resolution)
                    x = n.radius * np.outer(np.cos(u), np.sin(v)) + n.x
                    y = n.radius * np.outer(np.sin(u), np.sin(v)) - n.y
                    z = n.radius * np.outer(np.ones(np.size(u)), np.cos(v)) + n.z
                    surf = ax.plot_surface(x, z, y, color=this_color, shade=False)
                    if group_neurons:
                        surf.set_gid( neuron.neuron_name )

        if connectors or connectors_only:
            if not cn_mesh_colors:
                cn_types = {0: 'red', 1 : 'blue', 2 : 'green', 3 : 'magenta'}
            else:
                cn_types = {0:  this_color, 1 :  this_color, 2 : this_color, 3 : this_color}
            if method == '2d':
                for c in cn_types:
                    this_cn = neuron.connectors[neuron.connectors.relation == c]
                    ax.scatter(this_cn.x.values,
                              (-this_cn.y).values,
                              c=cn_types[c], alpha=1, zorder=4, edgecolor='none', s=cn_size)
                    ax.get_children()[-1].set_gid('CN_{0}'.format(neuron.neuron_name))
            elif method in ['3d','3d_complex']:
                all_cn = neuron.connectors
                c = [ cn_types[i] for i in all_cn.relation.tolist() ]
                ax.scatter(all_cn.x.values, all_cn.z.values, -all_cn.y.values,
                           c=c, s=cn_size, depthshade=False, edgecolor='none')
                ax.get_children()[-1].set_gid('CN_{0}'.format(neuron.neuron_name))

            coords = neuron.connectors[['x','y','z']].as_matrix()
            coords[:,1] *= -1
            lim.append( coords.max(axis=0) )
            lim.append( coords.min(axis=0) )

    if points:
        for p in points:
            if method == '2d':
                default_settings = dict(
                            c = 'black',
                            alpha = 1,
                            zorder = 4,
                            edge_color = 'none',
                            s = 1
                                )
                default_settings.update(scatter_kws)
                default_settings = _fix_default_dict(default_settings)

                ax.scatter(p[:,0],
                           p[:,1] *-1,
                           **default_settings)
            elif method in ['3d','3d_complex']:
                default_settings = dict(
                            c = 'black',
                            s = 1,
                            depthshade = False,
                            edgecolor='none'
                                )
                default_settings.update(scatter_kws)
                default_settings = _fix_default_dict(default_settings)

                ax.scatter(p[:,0], p[:,2], p[:,1] * -1,
                           **default_settings
                           )

            coords = p
            coords[:,1] *= -1
            lim.append( coords.max(axis=0) )
            lim.append( coords.min(axis=0) )

    if method == '2d':
        ax.autoscale()
    elif method in ['3d','3d_complex']:
        lim = np.vstack(lim)
        lim_min = lim.min(axis=0)
        lim_max = lim.max(axis=0)

        center = lim_min + ( lim_max - lim_min ) / 2
        max_dim = ( lim_max - lim_min ).max()

        new_min = center - max_dim / 2
        new_max = center + max_dim / 2

        ax.set_xlim( new_min[0], new_max[0] )
        ax.set_ylim( new_min[2], new_max[2] )
        ax.set_zlim( new_max[1], new_min[1] )

        ax.set_xlim( lim_min[0], lim_min[0]+max_dim )
        ax.set_ylim( lim_min[2], lim_min[2]+max_dim )
        ax.set_zlim( lim_max[1]-max_dim, lim_max[1] )

    if scalebar != None:
        # Convert sc size to nm
        sc_size = scalebar * 1000

        # Hard-coded offset from figure boundaries
        ax_offset = 1000

        if method == '2d':
            xlim = ax.get_xlim()
            ylim = ax.get_ylim()

            coords = np.array( [ [ xlim[0] + ax_offset, ylim[0] + ax_offset ],
                                 [ xlim[0] + ax_offset + sc_size, ylim[0] + ax_offset ]
                                ])

            sbar = mlines.Line2D( coords[:,0], coords[:,1], lw=3, alpha=.9, color='black')
            sbar.set_gid('{0}_um'.format(scalebar))

            ax.add_line( sbar )
        elif method in ['3d','3d_complex']:
            left = lim_min[0] + ax_offset
            bottom = lim_min[1] + ax_offset
            front = lim_min[2] + ax_offset

            sbar = [ np.array( [ [ left, front, bottom ],
                                 [ left, front, bottom ] ] ),
                     np.array( [ [ left, front, bottom ],
                                 [ left, front, bottom ] ] ),
                     np.array( [ [ left, front, bottom ],
                                 [ left, front, bottom ] ] ) ]
            sbar[0][1][0] += sc_size
            sbar[1][1][1] += sc_size
            sbar[2][1][2] += sc_size

            lc = Line3DCollection( sbar, color='black', lw=1)
            lc.set_gid( '{0}_um'.format(scalebar) )
            ax.add_collection3d( lc )

            """
            sbar_x = ax.plot( [left, left+sc_size], [front,front], [bottom,bottom], c='black' )
            sbar_y = ax.plot( [left, left], [front,front-sc_size], [bottom,bottom], c='black' )
            sbar_z = ax.plot( [left, left], [front,front], [bottom,bottom+sc_size], c='black' )

            sbar_x.set_gid('{0}_um'.format(scalebar))
            sbar_y.set_gid('{0}_um'.format(scalebar))
            sbar_z.set_gid('{0}_um'.format(scalebar))
            """

    plt.axis('off')

    module_logger.info('Done. Use matplotlib.pyplot.show() to show plot.')

    return fig, ax


def _fix_default_dict(x):
    """ Consolidates duplicate settings in e.g. scatter kwargs when 'c' and
    'color' is provided.
    """

    # The first entry is the "survivor"
    duplicates = [ ['color','c'], ['size','s'] ]

    for dupl in duplicates:
        if sum([ v in x for v in dupl ]) > 1:
            to_delete = [ v for v in dupl if v in x ][1:]
            _ = [ x.pop(v) for v in to_delete ]

    return x

def _segments_to_coords(x, segments, modifier=(1,1,1)):
    """Turns lists of treenode_ids into coordinates

    Parameters
    ----------
    x :         {pandas DataFrame, CatmaidNeuron}
                Must contain the nodes
    segments :  list of treenode IDs
    modifier :  ints, optional
                Use to modify/invert x/y/z axes.

    Returns
    -------
    coords :    list of tuples
                [ (x,y,z), (x,y,z ) ]
    """

    if not isinstance( modifier, np.ndarray ):
        modifier = np.array(modifier)

    locs = { r.treenode_id : (r.x,r.y,r.z) for r in x.nodes.itertuples() }

    coords = ( [ np.array([ locs[tn] for tn in s ]) * modifier for s in segments ] )

    return coords


def _random_colors(color_count, color_space='RGB', color_range=1):
    """ Divides colorspace into N evenly distributed colors

    Returns
    -------
    colormap :  list
             [ (r,g,b),(r,g,b),... ]

    """
    if color_count == 1:
        return [(0, 0, 0)]

    # Make count_color an even number
    if color_count % 2 != 0:
        color_count += 1

    colormap = []
    interval = 2 / color_count
    runs = int(color_count / 2)

    # Create first half with low brightness; second half with high brightness
    # and slightly shifted hue
    if color_space == 'RGB':
        for i in range(runs):
            # High brightness
            h = interval * i
            s = 1
            v = 1
            hsv = colorsys.hsv_to_rgb(h, s, v)
            colormap.append(tuple(v * color_range for v in hsv))

            # Lower brightness, but shift hue by half an interval
            h = interval * (i + 0.5)
            s = 1
            v = 0.5
            hsv = colorsys.hsv_to_rgb(h, s, v)
            colormap.append(tuple(v * color_range for v in hsv))
    elif color_space == 'Grayscale':
        h = 0
        s = 0
        for i in range(color_count):
            v = 1 / color_count * i
            hsv = colorsys.hsv_to_rgb(h, s, v)
            colormap.append(tuple(v * color_range for v in hsv))

    module_logger.debug('%i random colors created: %s' %
                        (color_count, str(colormap)))

    return(colormap)


def _fibonacci_sphere(samples=1, randomize=True):
    """ Calculates points on a sphere
    """
    rnd = 1.
    if randomize:
        rnd = random.random() * samples

    points = []
    offset = 2. / samples
    increment = math.pi * (3. - math.sqrt(5.))

    for i in range(samples):
        y = ((i * offset) - 1) + (offset / 2)
        r = math.sqrt(1 - pow(y, 2))

        phi = ((i + rnd) % samples) * increment

        x = math.cos(phi) * r
        z = math.sin(phi) * r

        points.append([x, y, z])

    return points


def plot3d(x, *args, **kwargs):
    """ Generates 3D plot using either vispy (default, http://vispy.org) or
    plotly (http://plot.ly)

    Parameters
    ----------

    x :               {skeleton IDs, core.CatmaidNeuron, core.CatmaidNeuronList,
                       core.Dotprops, core.Volumes}
                      Objects to plot::

                        - int is intepreted as skeleton ID(s)
                        - str is intepreted as volume name(s)
                        - multiple objects can be passed as list (see examples)

    remote_instance : CATMAID Instance, optional
                      Need to pass this too if you are providing only skids
                      also necessary if you want to include volumes! If
                      possible, will try to get remote instance from neuron
                      object.
    backend :         {'vispy','plotly'}, default = 'vispy'
       | ``vispy`` uses OpenGL to generate high-performance 3D plots but is less pretty.
       | ``plotly`` generates 3D plots in .html which are shareable but take longer to generate.

    connectors :      bool, default=False
                      Plot synapses and gap junctions.
    by_strahler :     bool, default=False
                      Will shade neuron(s) by strahler index.
    by_confidence :   bool, default=False
                      Will shade neuron(s) by arbor confidence
    cn_mesh_colors :  bool, default=False
                      Plot connectors using mesh colors.
    limits :          dict, optional
                      Manually override plot limits.
                      Format: ``{'x' :[min,max], 'y':[min,max], 'z':[min,max]}``
    auto_limits :     bool, default=True
                      Autoscales plot to fit the neurons.
    downsampling :    int, default=None
                      Set downsampling of neurons before plotting.
    clear3d :         bool, default=False
                      If True, canvas is cleared before plotting (only for
                      vispy).
    color :           {tuple, dict}, default=random
                      Use single tuple (r,g,b) to give all neurons the same
                      color. Use dict to give individual colors to neurons:
                      ``{ skid : (r,g,b), ... }``. R/G/B must be 0-255
    use_neuron_color : bool, default=False
                      If True, will try using the ``.color`` attribute of
                      CatmaidNeurons.
    width :           int, default=600
    height :          int, default=600
                      Use to define figure/window size.
    title :           str, default=None
                      Plot title (for plotly only!)
    fig_autosize :    bool, default=False
                      For plotly only! Autoscale figure size.
                      Attention: autoscale overrides width and height
    scatter_kws :     dict, optional
                      Use to modify point plots. Accepted parameters are:
                        - 'size' to adjust size of dots
                        - 'color' to adjust color

    Returns
    --------
    If ``backend='vispy'``

       Opens a 3D window and returns:

            - ``canvas`` - Vispy canvas object
            - ``view`` - Vispy view object -> use to manipulate camera, add object, etc.

    If ``backend='plotly'``

       ``fig`` - dictionary to generate plotly 3D figure:

            Use for example: ``plotly.offline.plot(fig, filename='3d_plot.html')``
            to generate html file and open it webbrowser

    Examples
    --------
    This assumes that you have alread initialised a remote instance as ``rm``

    >>> # Plot single neuron
    >>> nl = pymaid.get_neuron(16, remote_instance=rm)
    >>> pymaid.plot3d(nl)
    >>> # Clear canvas
    >>> pymaid.clear3d()
    >>> # Plot3D can deal with combinations of objects
    >>> nl2 = pymaid.get_neuron('annotation:glomerulus DA1', remote_instance=rm)
    >>> vol = pymaid.get_volume('v13.LH_R')
    >>> vol['color'] = (255,0,0,.5)
    >>> # This plots two neuronlists, two volumes and a single neuron
    >>> pymaid.plot3d( [ nl1, nl2, vol, 'v13.AL_R', 233007 ] )
    >>> # Pass kwargs
    >>> pymaid.plot3d(nl1, connectors=True, clear3d=True, )
    """

    def _plot3d_vispy():
        """
        Plot3d() helper function to generate vispy 3D plots. This is just to
        improve readability.
        """
        if kwargs.get('clear3d', False):
            clear3d()

        if 'vispy_scale_factor' not in globals():
            # Calculate a scale factor: if the scene is too big, we run into issues with line width, etc.
            # Should keep it between -1000 and +1000
            global vispy_scale_factor
            max_dim = max([math.fabs(n)
                           for n in [max_x, min_x, max_y, min_y, max_z, min_z]])
            vispy_scale_factor = 1000 / max_dim
        else:
            vispy_scale_factor = globals()['vispy_scale_factor']

        # If does not exists yet, initialise a canvas object and make global
        if 'canvas' not in globals():
            global canvas
            canvas = scene.SceneCanvas(keys='interactive', size=(
                width, height), bgcolor='white')
            view = canvas.central_widget.add_view()

            # Add camera
            view.camera = scene.TurntableCamera()

            # Set camera range
            view.camera.set_range((min_x * vispy_scale_factor, max_x * vispy_scale_factor),
                                  (min_y * vispy_scale_factor, max_y * vispy_scale_factor),
                                  (min_z * vispy_scale_factor, max_z * vispy_scale_factor)
                                  )
        else:
            canvas = globals()['canvas']

            # Check if we already have a view, if not (e.g. if plot.clear3d()
            # has been used) add new
            if canvas.central_widget.children:
                view = canvas.central_widget.children[0]
            else:
                view = canvas.central_widget.add_view()


                # Add camera
                view.camera = scene.TurntableCamera()

                # Set camera range
                view.camera.set_range((min_x * vispy_scale_factor, max_x * vispy_scale_factor),
                                      (min_y * vispy_scale_factor, max_y * vispy_scale_factor),
                                      (min_z * vispy_scale_factor, max_z * vispy_scale_factor)
                                      )

        for i, neuron in enumerate(skdata.itertuples()):
            module_logger.debug('Working on neuron %s' %
                                str(neuron.skeleton_id))
            try:
                neuron_color = colormap[str(neuron.skeleton_id)]
            except:
                neuron_color = (0, 0, 0)

            if max(neuron_color) > 1:
                neuron_color = np.array(neuron_color) / 255

            # Get root node indices (may be more than one if neuron has
            # been cut weirdly)
            root_ix = neuron.nodes[
                neuron.nodes.parent_id.isnull()].index.tolist()

            if not connectors_only:
                nodes = neuron.nodes[ ~neuron.nodes.parent_id.isnull() ]

                # Extract treenode_coordinates and their parent's coordinates
                tn_coords = nodes[['x', 'y', 'z']].apply(
                    pd.to_numeric).as_matrix()
                parent_coords = neuron.nodes.set_index('treenode_id').loc[nodes.parent_id.tolist(
                )][['x', 'y', 'z']].apply(pd.to_numeric).as_matrix()

                # Turn coordinates into segments
                segments = [item for sublist in zip(
                    tn_coords, parent_coords) for item in sublist]

                # Add alpha to color based on strahler
                if by_strahler or by_confidence:
                    if by_strahler:
                        if 'strahler_index' not in neuron.nodes:
                            morpho.strahler_index(neuron)

                        # Generate list of alpha values
                        alpha = neuron.nodes['strahler_index'].as_matrix()

                    if by_confidence:
                        if 'arbor_confidence' not in neuron.nodes:
                            morpho.arbor_confidence(neuron)

                        # Generate list of alpha values
                        alpha = neuron.nodes['arbor_confidence'].as_matrix()

                    # Pop root from coordinate lists
                    alpha = np.delete(alpha, root_ix, axis=0)

                    alpha = alpha / (max(alpha)+1)
                    # Duplicate values (start and end of each segment!)
                    alpha = np.array([ v for l in zip(alpha,alpha) for v in l ])

                    # Turn color into array (need 2 colors per segment for beginnng and end)
                    neuron_color = np.array( [ neuron_color ] * (tn_coords.shape[0] * 2), dtype=float )

                    neuron_color = np.insert(neuron_color, 3, alpha, axis=1)

                if segments:
                    # Create line plot from segments. Note that we divide coords by
                    # a scale factor
                    t = scene.visuals.Line(pos=np.array(segments) * vispy_scale_factor,
                                           color=list(neuron_color),
                                           width=2,
                                           connect='segments',
                                           antialias=False,
                                           method='gl') #method can also be 'agg'
                    view.add(t)

                if by_strahler or by_confidence:
                    #Convert array back to a single color without alpha
                    neuron_color=neuron_color[0][:3]

                # Extract and plot soma
                soma = neuron.nodes[neuron.nodes.radius > 1]
                if soma.shape[0] >= 1:
                    radius = min(
                        soma.ix[soma.index[0]].radius * vispy_scale_factor, 10)
                    sp = create_sphere(5, 5, radius=radius)
                    s = scene.visuals.Mesh(vertices=sp.get_vertices() + soma.ix[soma.index[0]][
                                           ['x', 'y', 'z']].as_matrix() * vispy_scale_factor,
                                           faces=sp.get_faces(),
                                           color=neuron_color)
                    view.add(s)

            if connectors or connectors_only:
                for j in [0, 1, 2]:
                    if cn_mesh_colors:
                        color = neuron_color
                    else:
                        color = syn_lay[j]['color']

                    if max(color) > 1:
                        color = np.array(color) / 255

                    this_cn = neuron.connectors[
                        neuron.connectors.relation == j]

                    if this_cn.empty:
                        continue

                    pos = this_cn[['x', 'y', 'z']].apply(
                        pd.to_numeric).as_matrix()

                    if syn_lay['display'] == 'mpatches.Circles':
                        con = scene.visuals.Markers()

                        con.set_data(pos=np.array(pos) * vispy_scale_factor,
                                     face_color=color, edge_color=color, size=1)

                        view.add(con)

                    elif syn_lay['display'] == 'lines':
                        tn_coords = neuron.nodes.set_index('treenode_id').ix[this_cn.treenode_id.tolist(
                        )][['x', 'y', 'z']].apply(pd.to_numeric).as_matrix()

                        segments = [item for sublist in zip(
                            pos, tn_coords) for item in sublist]

                        t = scene.visuals.Line(pos=np.array(segments) * vispy_scale_factor,
                                               color=color,
                                               width=2,
                                               connect='segments',
                                               antialias=False,
                                               method='gl') #method can also be 'agg'
                        view.add(t)

        for neuron in dotprops.itertuples():
            try:
                neuron_color = colormap[str(neuron.gene_name)]
            except:
                neuron_color = (10, 10, 10)

            if max(neuron_color) > 1:
                neuron_color = np.array(neuron_color) / 255

            # Prepare lines - this is based on nat:::plot3d.dotprops
            halfvect = neuron.points[
                ['x_vec', 'y_vec', 'z_vec']] / 2 * scale_vect

            starts = neuron.points[['x', 'y', 'z']
                                   ].as_matrix() - halfvect.as_matrix()
            ends = neuron.points[['x', 'y', 'z']
                                 ].as_matrix() + halfvect.as_matrix()

            segments = [item for sublist in zip(
                starts, ends) for item in sublist]

            t = scene.visuals.Line(pos=np.array(segments) * vispy_scale_factor,
                                   color=neuron_color,
                                   width=2,
                                   connect='segments',
                                   antialias=False,
                                   method='gl') #method can also be 'agg'
            view.add(t)

            # Add soma
            sp = create_sphere(5, 5, radius=4)
            s = scene.visuals.Mesh(vertices=sp.get_vertices(
            ) + np.array([neuron.X, neuron.Y, neuron.Z]) * vispy_scale_factor, faces=sp.get_faces(), color=neuron_color)
            view.add(s)

        # Now add neuropils:
        for v in volumes_data:
            color = np.array(volumes_data[v]['color'], dtype=float)

            # Add alpha
            if len(color) < 4:
                color = np.append(color, [.6])

            if max(color) > 1:
                color[:3] = color[:3] / 255

            s = scene.visuals.Mesh(vertices=np.array(volumes_data[v][
                                   'verts']) * vispy_scale_factor, faces=volumes_data[v]['faces'], color=color)
            view.add(s)

        # Add points data
        for p in points:
            if not isinstance(p, np.ndarray):
                p = np.array(p)

            con = scene.visuals.Markers()
            con.set_data(pos=p * vispy_scale_factor,
                         face_color=scatter_kws.get('marker_color', (0,0,0)),
                         edge_color=scatter_kws.get('marker_color', (0,0,0)),
                         size= scatter_kws.get('marker_size', 2))
            view.add(con)

        # Add a 3D axis to keep us oriented
        # ax = scene.visuals.XYZAxis( )
        # view.add(ax)

        # And finally: show canvas
        canvas.show()

        module_logger.info(
            'Use pymaid.clear3d() to clear canvas and pymaid.close3d() to close canvas.')

        return canvas, view

    def _plot3d_plotly():
        """
        Plot3d() helper function to generate plotly 3D plots. This is just to
        improve readability and structure of the code.
        """

        if limits:
            catmaid_limits = limits
        elif auto_limits:
            # Set limits based on data but make sure that dimensions along all
            # axes are the same - otherwise plot will be skewed
            max_dim = max([max_x - min_x, max_y - min_y, max_z - min_z]) * 1.1
            catmaid_limits = {  # These limits refer to x/y/z in CATMAID -> will later on be inverted and switched to make 3d plot
                'x': [int((min_x + (max_x - min_x) / 2) - max_dim / 2), int((min_x + (max_x - min_x) / 2) + max_dim / 2)],
                'y': [int((min_z + (max_z - min_z) / 2) - max_dim / 2), int((min_z + (max_z - min_z) / 2) + max_dim / 2)],
                'z': [int((min_y + (max_y - min_y) / 2) - max_dim / 2), int((min_y + (max_y - min_y) / 2) + max_dim / 2)]
            }  # z and y need to be inverted here!
        elif not skdata.empty:
            catmaid_limits = {  # These limits refer to x/y/z in CATMAID -> will later on be inverted and switched to make 3d plot
                'x': [200000, 1000000],  # Make sure [0] < [1]!
                # Also make sure that dimensions along all axes are the same -
                # otherwise plot will be skewed
                'z': [-70000, 730000],
                'y': [-150000, 650000]
            }
        elif not dotprops.empty:
            catmaid_limits = {  # These limits refer to x/y/z in CATMAID -> will later on be inverted and switched to make 3d plot
                'x': [-500, 500],  # Make sure [0] < [1]!
                # Also make sure that dimensions along all axes are the same -
                # otherwise plot will be skewed
                'z': [-500, 500],
                'y': [-500, 500]
            }

        # Use catmaid project's limits to scale axis -> we basically have to invert
        # everything to give the plot the right orientation
        ax_limits = {
            'x': [-catmaid_limits['x'][1], -catmaid_limits['x'][0]],
            'z': [-catmaid_limits['z'][1], -catmaid_limits['z'][0]],
            'y': [-catmaid_limits['y'][1], -catmaid_limits['y'][0]]
        }

        trace_data = []

        # Generate sphere for somas
        fib_points = _fibonacci_sphere(samples=30)

        module_logger.info('Generating traces...')

        for i, neuron in enumerate(skdata.itertuples()):
            module_logger.debug('Working on neuron %s' %
                                str(neuron.skeleton_id))

            neuron_name = neuron.neuron_name
            skid = neuron.skeleton_id

            if not connectors_only:
                if by_strahler:
                    s_index = morpho.strahler_index(
                        skdata.ix[i], return_dict=True)

                soma = neuron.nodes[neuron.nodes.radius > 1]

                coords = _segments_to_coords(neuron, neuron.segments, modifier=(-1,-1,-1))

                # We have to add (None,None,None) to the end of each slab to
                # make that line discontinuous there
                coords = np.vstack( [ np.append(t, [[None] * 3], axis=0) for t in coords] )

                c = []
                if by_strahler:
                    for k, s in enumerate(coords):
                        this_c = 'rgba(%i,%i,%i,%f)' % (colormap[str(skid)][0],
                                                        colormap[str(skid)][1],
                                                        colormap[str(skid)][2],
                                                        s_index[s[0]] / max(s_index.values()
                                                                            ))
                        # Slabs are separated by a <None> coordinate -> this is
                        # why we need one more color entry
                        c += [this_c] * (len(s) + 1)
                else:
                    try:
                        c = 'rgb%s' % str(colormap[str(skid)])
                    except:
                        c = 'rgb(10,10,10)'

                trace_data.append(go.Scatter3d(x=coords[:,0],
                                               y= coords[:,2],  # y and z are switched
                                               z=coords[:,1],
                                               mode='lines',
                                               line=dict(
                                                   color=c,
                                                   width=5
                                               ),
                                               name=neuron_name,
                                               legendgroup=neuron_name,
                                               showlegend=True,
                                               hoverinfo='none'

                                               ))

                # Add soma(s):
                for n in soma.itertuples():
                    try:
                        color = 'rgb%s' % str(colormap[str(skid)])
                    except:
                        color = 'rgb(10,10,10)'
                    trace_data.append(go.Mesh3d(
                        x=[(v[0] * n.radius / 2) - n.x for v in fib_points],
                        # y and z are switched
                        y=[(v[1] * n.radius / 2) - n.z for v in fib_points],
                        z=[(v[2] * n.radius / 2) - n.y for v in fib_points],

                        alphahull=.5,
                        color=color,
                        name=neuron_name,
                        legendgroup=neuron_name,
                        showlegend=False,
                        hoverinfo='name'
                    )
                    )

            if connectors or connectors_only:
                for j in [0, 1, 2]:
                    if cn_mesh_colors:
                        try:
                            color = colormap[str(skid)]
                        except:
                            color = (10,10,10)
                    else:
                        color = syn_lay[j]['color']

                    this_cn = neuron.connectors[
                        neuron.connectors.relation == j]

                    if syn_lay['display'] == 'mpatches.Circles':
                        trace_data.append(go.Scatter3d(
                            x=this_cn.x.as_matrix() * -1,
                            y=this_cn.z.as_matrix() * -1,  # y and z are switched
                            z=this_cn.y.as_matrix() * -1,
                            mode='markers',
                            marker=dict(
                                color='rgb%s' % str(color),
                                size=2
                            ),
                            name=syn_lay[j]['name'] + ' of ' + neuron_name,
                            showlegend=True,
                            hoverinfo='none'
                        ))
                    elif syn_lay['display'] == 'lines':
                        # Find associated treenode
                        tn = neuron.nodes.set_index('treenode_id').ix[this_cn.treenode_id.tolist()]
                        x_coords = [n for sublist in zip(this_cn.x.as_matrix(
                        ) * -1, tn.x.as_matrix() * -1, [None] * this_cn.shape[0]) for n in sublist]
                        y_coords = [n for sublist in zip(this_cn.y.as_matrix(
                        ) * -1, tn.y.as_matrix() * -1, [None] * this_cn.shape[0]) for n in sublist]
                        z_coords = [n for sublist in zip(this_cn.z.as_matrix(
                        ) * -1, tn.z.as_matrix() * -1, [None] * this_cn.shape[0]) for n in sublist]

                        trace_data.append(go.Scatter3d(
                            x=x_coords,
                            y=z_coords,  # y and z are switched
                            z=y_coords,
                            mode='lines',
                            line=dict(
                                color='rgb%s' % str(color),
                                width=5
                            ),
                            name=syn_lay[j]['name'] + ' of ' + neuron_name,
                            showlegend=True,
                            hoverinfo='none'
                        ))

        for neuron in dotprops.itertuples():
            # Prepare lines - this is based on nat:::plot3d.dotprops
            halfvect = neuron.points[
                ['x_vec', 'y_vec', 'z_vec']] / 2 * scale_vect

            starts = neuron.points[['x', 'y', 'z']
                                   ].as_matrix() - halfvect.as_matrix()
            ends = neuron.points[['x', 'y', 'z']
                                 ].as_matrix() + halfvect.as_matrix()

            x_coords = [n for sublist in zip(
                starts[:, 0] * -1, ends[:, 0] * -1, [None] * starts.shape[0]) for n in sublist]
            y_coords = [n for sublist in zip(
                starts[:, 1] * -1, ends[:, 1] * -1, [None] * starts.shape[0]) for n in sublist]
            z_coords = [n for sublist in zip(
                starts[:, 2] * -1, ends[:, 2] * -1, [None] * starts.shape[0]) for n in sublist]

            try:
                c = 'rgb%s' % str(colormap[neuron.gene_name])
            except:
                c = 'rgb(10,10,10)'

            trace_data.append(go.Scatter3d(x=x_coords,  # (-neuron.nodes.ix[ s ].x).tolist(),
                                           # (-neuron.nodes.ix[ s ].z).tolist(), #y and z are switched
                                           y=z_coords,
                                           # (-neuron.nodes.ix[ s ].y).tolist(),
                                           z=y_coords,
                                           mode='lines',
                                           line=dict(
                                               color=c,
                                               width=5
                                           ),
                                           name=neuron.gene_name,
                                           legendgroup=neuron.gene_name,
                                           showlegend=True,
                                           hoverinfo='none'
                                           ))

            # Add soma
            rad = 4
            trace_data.append(go.Mesh3d(
                x=[(v[0] * rad / 2) - neuron.X for v in fib_points],
                # y and z are switched
                y=[(v[1] * rad / 2) - neuron.Z for v in fib_points],
                z=[(v[2] * rad / 2) - neuron.Y for v in fib_points],

                alphahull=.5,

                color=c,
                name=neuron.gene_name,
                legendgroup=neuron.gene_name,
                showlegend=False,
                hoverinfo='name'
            )
            )

        module_logger.info('Tracing done.')

        # Now add neuropils:
        for v in volumes_data:
            if volumes_data[v]['verts']:
                trace_data.append(go.Mesh3d(
                    x=[-v[0] for v in volumes_data[v]['verts']],
                    # y and z are switched
                    y=[-v[2] for v in volumes_data[v]['verts']],
                    z=[-v[1] for v in volumes_data[v]['verts']],

                    i=[f[0] for f in volumes_data[v]['faces']],
                    j=[f[1] for f in volumes_data[v]['faces']],
                    k=[f[2] for f in volumes_data[v]['faces']],

                    opacity=.5,
                    color='rgb' + str(volumes_data[v]['color']),
                    name=v,
                    showlegend=True,
                    hoverinfo='none'
                )
                )

        layout = dict(
            width=width,
            height=height,
            autosize=fig_autosize,
            title=pl_title,
            scene=dict(
                xaxis=dict(
                    gridcolor='rgb(255, 255, 255)',
                    zerolinecolor='rgb(255, 255, 255)',
                    showbackground=True,
                    backgroundcolor='rgb(240, 240, 240)',
                    range=ax_limits['x']

                ),
                yaxis=dict(
                    gridcolor='rgb(255, 255, 255)',
                    zerolinecolor='rgb(255, 255, 255)',
                    showbackground=True,
                    backgroundcolor='rgb(240, 240, 240)',
                    range=ax_limits['y']
                ),
                zaxis=dict(
                    gridcolor='rgb(255, 255, 255)',
                    zerolinecolor='rgb(255, 255, 255)',
                    showbackground=True,
                    backgroundcolor='rgb(240, 240, 240)',
                    range=ax_limits['z']
                ),
                camera=dict(
                    up=dict(
                        x=0,
                        y=0,
                        z=1
                    ),
                    eye=dict(
                        x=-1.7428,
                        y=1.0707,
                        z=0.7100,
                    )
                ),
                aspectratio=dict(x=1, y=1, z=1),
                aspectmode='manual'
            ),
        )

        # Need to remove width and height to make autosize actually matter
        if fig_autosize:
            layout.pop('width')
            layout.pop('height')

        fig = dict(data=trace_data, layout=layout)

        module_logger.info('Done. Plotted %i nodes and %i connectors' % (sum([n.nodes.shape[0] for n in skdata.itertuples() if not connectors_only] + [
                           n.points.shape[0] for n in dotprops.itertuples()]), sum([n.connectors.shape[0] for n in skdata.itertuples() if connectors or connectors_only])))
        module_logger.info(
            'Use plotly.offline.plot(fig, filename="3d_plot.html") to plot. Optimised for Google Chrome.')

        return fig

    skids, skdata, dotprops, volumes, points = _parse_objects(x)

    # Backend
    backend = kwargs.get('backend', 'vispy')

    # CatmaidInstance
    remote_instance = kwargs.get('remote_instance', None)

    # Parameters for neurons
    color = kwargs.get('color', None)
    names = kwargs.get('names', [])
    downsampling = kwargs.get('downsampling', 1)
    connectors = kwargs.get('connectors', False)
    by_strahler = kwargs.get('by_strahler', False)
    by_confidence = kwargs.get('by_confidence', False)
    cn_mesh_colors = kwargs.get('cn_mesh_colors', False)
    connectors_only = kwargs.get('connectors_only', False)
    use_neuron_color = kwargs.get('use_neuron_color', False)

    scatter_kws = kwargs.get('scatter_kws', {})
    syn_lay_new = kwargs.get('synapse_layout',  {})
    syn_lay = {0: {
        'name': 'Presynapses',
        'color': (255, 0, 0)
    },
        1: {
        'name': 'Postsynapses',
        'color': (0, 0, 255)
    },
        2: {
        'name': 'Gap junctions',
        'color': (0, 255, 0)
    },
        'display': 'lines' #'mpatches.Circles'
    }
    syn_lay.update(syn_lay_new)

    # Parameters for dotprops
    scale_vect = kwargs.get('scale_vect', 1)
    alpha_range = kwargs.get('alpha_range', False)

    # Parameters for figure
    pl_title = kwargs.get('title', None)
    width = kwargs.get('width', 600)
    height = kwargs.get('height', 600)
    fig_autosize = kwargs.get('fig_autosize', False)
    limits = kwargs.get('limits', [])
    auto_limits = kwargs.get('auto_limits', True)
    auto_limits = kwargs.get('autolimits', auto_limits)

    if backend not in ['plotly','vispy']:
        module_logger.error(
            'Unknown backend: %s. See help(plot.plot3d).' % str(backend))
        return

    if not remote_instance and isinstance(skdata, core.CatmaidNeuronList):
        try:
            remote_instance = skdata._remote_instance
        except:
            pass

    remote_instance = fetch._eval_remote_instance(remote_instance)

    if skids and remote_instance:
        skdata += fetch.get_neuron(skids, remote_instance,
                                   connector_flag=1,
                                   tag_flag=0,
                                   get_history=False,
                                   get_abutting=True)
    elif skids and not remote_instance:
        module_logger.error(
            'You need to provide a CATMAID remote instance.')

    if not color and (skdata.shape[0] + dotprops.shape[0])>0:
        cm = _random_colors(
            skdata.shape[0] + dotprops.shape[0], color_space='RGB', color_range=255)
        colormap = {}

        if not skdata.empty:
            colormap.update(
                {str(n): cm[i] for i, n in enumerate(skdata.skeleton_id.tolist())})
        if not dotprops.empty:
            colormap.update({str(n): cm[i + skdata.shape[0]]
                             for i, n in enumerate(dotprops.gene_name.tolist())})
        if use_neuron_color:
            colormap.update( { n.skeleton_id : n.color for n in skdata } )
    elif isinstance(color, dict):
        colormap = {n: tuple(color[n]) for n in color}
    elif isinstance(color,(list,tuple)):
        colormap = {n: tuple(color) for n in skdata.skeleton_id.tolist()}
    elif isinstance(color,str):
        color = tuple( [ int(c *255) for c in mcl.to_rgb(color) ] )
        colormap = {n: color for n in skdata.skeleton_id.tolist()}
    else:
        colormap = {}

    # Make sure colors are 0-255
    if colormap:
        if max([ v for n in colormap for v in colormap[n] ]) <= 1:
            module_logger.warning('Looks like RGB values are 0-1. Converting to 0-255.')
            colormap = { n : tuple( [ int(v * 255) for v in colormap[n] ] ) for n in colormap }

    # Get and prepare volumes
    volumes_data = {}
    for v in volumes:
        if isinstance(v, str):
            if not remote_instance:
                module_logger.error(
                    'Unable to add volumes - please also pass a Catmaid Instance using <remote_instance = ... >')
                return
            else:
                v = fetch.get_volume(v, remote_instance)

        volumes_data[ v['name'] ] = {'verts': v['vertices'],
                           'faces': v['faces'], 'color': v['color']}

    # Get boundaries of what to plot
    min_x, max_x, min_y, max_y, min_z, max_z, = [],[],[],[],[],[]

    if not skdata.empty:
        if not connectors_only:
            min_x += [n.nodes.x.min() for n in skdata.itertuples()]
            max_x += [n.nodes.x.max() for n in skdata.itertuples()]
            min_y += [n.nodes.y.min() for n in skdata.itertuples()]
            max_y += [n.nodes.y.max() for n in skdata.itertuples()]
            min_z += [n.nodes.z.min() for n in skdata.itertuples()]
            max_z += [n.nodes.z.max() for n in skdata.itertuples()]

        if connectors or connectors_only:
            min_x += [n.connectors.x.min() for n in skdata.itertuples()]
            max_x += [n.connectors.x.max() for n in skdata.itertuples()]
            min_y += [n.connectors.y.min() for n in skdata.itertuples()]
            max_y += [n.connectors.y.max() for n in skdata.itertuples()]
            min_z += [n.connectors.z.min() for n in skdata.itertuples()]
            max_z += [n.connectors.z.max() for n in skdata.itertuples()]

    if not dotprops.empty:
        min_x += [n.points.x.min() for n in dotprops.itertuples()]
        max_x += [n.points.x.max() for n in dotprops.itertuples()]
        min_y += [n.points.y.min() for n in dotprops.itertuples()]
        max_y += [n.points.y.max() for n in dotprops.itertuples()]
        min_z += [n.points.z.min() for n in dotprops.itertuples()]
        max_z += [n.points.z.max() for n in dotprops.itertuples()]

    if volumes_data:
        v_min  = [ np.array(volumes_data[v]['verts']).min(axis=0) for v in volumes_data ]
        v_max  = [ np.array(volumes_data[v]['verts']).max(axis=0) for v in volumes_data ]
        min_x += [ v[0] for v in v_min]
        max_x += [ v[0] for v in v_max]
        min_y += [ v[1] for v in v_min]
        max_y += [ v[1] for v in v_max]
        min_z += [ v[2] for v in v_min]
        max_z += [ v[2] for v in v_max]

    if points:
        p_min = [ p.min(axis=0) for p in points ]
        p_max = [ p.max(axis=0) for p in points ]

        min_x += [ p[0] for p in p_min]
        max_x += [ p[0] for p in p_max]
        min_y += [ p[1] for p in p_min]
        max_y += [ p[1] for p in p_max]
        min_z += [ p[2] for p in p_min]
        max_z += [ p[2] for p in p_max]

    min_x = min(min_x)
    max_x = max(max_x)
    min_y = min(min_y)
    max_y = max(max_y)
    min_z = min(min_z)
    max_z = max(max_z)

    module_logger.debug('Preparing neurons for plotting...')
    # First downsample neurons
    if downsampling > 1 and not connectors_only and not skdata.empty:
        module_logger.debug('Downsampling neurons...')
        morpho.module_logger.setLevel('ERROR')
        skdata.downsample( downsampling )
        morpho.module_logger.setLevel('INFO')
        module_logger.debug('Downsampling finished.')
    elif skdata.shape[0] > 100:
        module_logger.info(
            'Large dataset detected. Consider using the <downsampling> parameter if you encounter bad performance.')

    if backend == 'plotly':
        return _plot3d_plotly()
    else:
        return _plot3d_vispy()


def plot_network(x, *args, **kwargs):
    """ Uses NetworkX to generate a Plotly network plot.

    Parameters
    ----------
    x
                      Neurons as single or list of either:

                      1. skeleton IDs (int or str)
                      2. neuron name (str, exact match)
                      3. annotation: e.g. ``'annotation:PN right'``
                      4. CatmaidNeuron or CatmaidNeuronList object
                      5. pandas.DataFrame containing an adjacency matrix.,
                         e.g. from :funct:`~pymaid.create_adjacency_matrix`
                      6. NetworkX Graph
    remote_instance : CATMAID Instance, optional
                      Need to pass this too if you are providing only skids.
    layout :          {str, function}, default = nx.spring_layout
                      Layout function. See https://networkx.github.io/documentation/latest/reference/drawing.html
                      for available layouts. Use either the function directly
                      or its name.
    syn_cutoff :      int, default=False
                      If provided, connections will be maxed at this value.
    syn_threshold :   int, default=0
                      Edges with less connections are ignored.
    groups :          dict
                      Use to group neurons. Format:
                      ``{ 'Group A' : [skid1, skid2, ..], }``
    colormap :        {str, tuple, dict }
                | Set to 'random' (default) to assign random colors to neurons
                | Use single tuple to assign the same color to all neurons:
                | e.g. ``( (220,10,50) )``
                | Use dict to assign rgb colors to individual neurons:
                | e.g. ``{ neuron1 : (200,200,0), .. }``
    label_nodes :     bool, default=True
                      Plot neuron labels.
    label_edges :     bool, default=True
                      Plot edge labels.
    width :           int, default=800
    height :          int, default=800
                      Figure width and height.
    node_hover_text : dict
                      Provide custom hover text for neurons:
                      ``{ neuron1 : 'hover text', .. }``
    node_size :       {int, dict}
                      | Use int to set node size once.
                      | Use dict to set size for individual nodes:
                      | ``{ neuron1 : 20, neuron2 : 5,  .. }``

    Returns
    -------
    fig : plotly dict
       Use for example ``plotly.offline.plot(fig, filename='plot.html')`` to
       generate html file and open it webbrowser

    """

    remote_instance = kwargs.get('remote_instance', None)

    layout = kwargs.get('layout', nx.spring_layout)

    if isinstance(layout, str):
        layout = getattr(nx, layout)

    syn_cutoff = kwargs.get('syn_cutoff', None)
    syn_threshold = kwargs.get('syn_threshold', 1)
    groups = kwargs.get('groups', [])
    colormap = kwargs.get('colormap', 'random')

    label_nodes = kwargs.get('label_nodes', True)
    label_edges = kwargs.get('label_edges', True)
    label_hover = kwargs.get('label_hover', True)

    node_labels = kwargs.get('node_labels', [])
    node_hover_text = kwargs.get('node_hover_text', [])
    node_size = kwargs.get('node_size', 20)

    width = kwargs.get('width', 800)
    height = kwargs.get('height', 800)

    remote_instance = fetch._eval_remote_instance(remote_instance)

    if not isinstance(x, (nx.DiGraph, nx.Graph) ):
        x = fetch.eval_skids(x, remote_instance=remote_instance)
        g = graph.network2nx(x, threshold=syn_threshold)
    else:
        g = x

    pos = layout(g)

    # Prepare colors
    if isinstance(colormap, dict):
        colors = colormap
        # Give grey color to neurons that are not in colormap
        colors.update({n: (.5, .5, .5) for n in g.nodes if n not in colormap})
    elif colormap == 'random':
        c = _random_colors(len(g.nodes), color_space='RGB', color_range=255)
        colors = { n: c[i] for i, n in enumerate(g.nodes)}
    elif isinstance(colormap, tuple, list) and len(colormap) == 3:
        colors = {n : tuple(colormap) for v in g.nodes }
    else:
        module_logger.error(
            'I dont understand the colors you have provided. Please, see help(plot.plot_network).')
        return None

    edges = []
    annotations = []
    max_weight = max( nx.get_edge_attributes(g,'weight').values() )
    for e in  list( g.edges.data() ):
        e_width = 2 + 5 * round(e[2]['weight']) / max_weight

        edges.append(
            go.Scatter(dict(
                x=[pos[e[0]][0], pos[e[1]][0], None],
                y=[pos[e[0]][1], pos[e[1]][1], None],
                mode='lines',
                hoverinfo='text',
                text=str(e[2]['weight']),
                line=dict(
                    width=e_width,
                    color='rgb(255,0,0)'
                )
            ))
        )

        annotations.append(dict(
            x=pos[e[1]][0],
            y=pos[e[1]][1],
            xref='x',
            yref='y',
            showarrow=True,
            align='center',
            arrowhead=2,
            arrowsize=.5,
            arrowwidth=e_width,
            arrowcolor='#636363',
            ax=pos[e[0]][0],
            ay=pos[e[0]][1],
            axref='x',
            ayref='y',
            standoff=10,
            startstandoff=10,
            opacity=.7

        ))

        if label_edges:
            center_x = (pos[e[1]][0] - pos[e[0]]
                        [0]) / 2 + pos[e[0]][0]
            center_y = (pos[e[1]][1] - pos[e[0]]
                        [1]) / 2 + pos[e[0]][1]

            if e[2]['weight'] == syn_cutoff:
                t = '%i +' % int(e[2]['weight'])
            else:
                t = str(int(e[2]['weight']))

            annotations.append(dict(
                x=center_x,
                y=center_y,
                xref='x',
                yref='y',
                showarrow=False,
                text=t,
                font=dict(color='rgb(0,0,0)', size=10)
            )

            )

    # Prepare hover text
    if not node_hover_text:
        node_hover_text = {n: g.nodes[n]['neuron_name'] for n in g.nodes}
    else:
        # Make sure all nodes are represented
        node_hover_text.update({n: g.nodes[n]['neuron_name']
                                for n in g.nodes if n not in node_hover_text})

    # Prepare node sizes
    if isinstance(node_size, dict):
        n_size = [ node_size[n] for n in g.nodes]
    else:
        n_size = node_size

    nodes = go.Scatter(dict(
        x=np.vstack( pos.values() )[:,0],
        y=np.vstack( pos.values() )[:,1],
        text=[node_hover_text[ n ] for n in g.nodes ] if label_hover else None,
        mode='markers',
        hoverinfo='text',
        marker=dict(
            size=n_size,
            color=['rgb' + str(tuple(colors[ n ])) for n in g.nodes ]
        )
    ))

    if label_nodes:
        annotations += [dict(
            x=pos[n][0],
            y=pos[n][1],
            xref='x',
            yref='y',
            text=g.nodes[n]['neuron_name'],
            showarrow=False,
            font=dict(color='rgb(0,0,0)', size=12)
        )
            for n in pos]

    layout = dict(
        width=width,
        height=height,
        showlegend=False,
        annotations=annotations,
        xaxis=dict(
            showline=False,
            zeroline=False,
            showgrid=False,
            showticklabels=False,
            title=''
        ),
        yaxis=dict(
            showline=False,
            zeroline=False,
            showgrid=False,
            showticklabels=False,
            title=''
        ),
        hovermode='closest'
    )

    data = go.Data([nodes])

    fig = go.Figure(data=data, layout=layout)

    module_logger.info(
        'Done! Use e.g. plotly.offline.plot(fig, filename="network_plot.html") to plot.')

    return fig

def _parse_objects(x,remote_instance=None):
    """ Helper class to extract objects for plotting.
    """

    if not isinstance(x, list):
        x = [x]

    # Check for skeleton IDs
    skids = []
    for ob in x:
        try:
            skids.append(int(ob))
        except:
            pass

    # Collect neuron objects and collate to single Neuronlist
    neuron_obj = [ob for ob in x if isinstance(
        ob, (pd.DataFrame, pd.Series, core.CatmaidNeuron, core.CatmaidNeuronList))
        and not isinstance(ob, (core.Dotprops, core.Volume))] # dotprops and volumes are instances of pd.DataFrames

    skdata = core.CatmaidNeuronList( neuron_obj, make_copy=False)

    # Collect dotprops
    dotprops = [ob for ob in x if isinstance(ob,core.Dotprops)]

    if len(dotprops) == 1:
        dotprops = dotprops[0]
    elif len(dotprops) == 0:
        dotprops = pd.DataFrame()
    elif len(dotprops) > 1:
        dotprops = pd.concat(dotprops)

    # Collect and parse volumes
    volumes = [ ob for ob in x if isinstance(ob, (core.Volume, str) ) ]

    # Collect dataframes with xyz coordinates
    dataframes = [ ob for ob in x if isinstance(ob, (pd.DataFrame, pd.Series) ) ]

    # Collect points
    points = [ob.copy() for ob in x if isinstance(ob,np.ndarray)]

    # Remove points with wrong dimensions
    if [ ob for ob in points if ob.shape[1] != 3 ]:
        module_logger.warning('Point objects need to be of shape (n,3).')
    points = [ ob for ob in points if ob.shape[1] == 3 ]

    return skids, skdata, dotprops, volumes, points


def plot1d( x, ax=None, color=None, **kwargs):
    """ Plot neuron topology in 1D according to Cuntz et al. (2010).

    Parameters
    ----------
    x :         {CatmaidNeuron, CatmaidNeuronList}
                Neurons to plot.
    ax :        matplotlib.ax, optional
    cmap :      {tuple, dict}
                Color. If dict must map skeleton ID to color.
    **kwargs
                Will be passed to matplotlib.patches.Rectangle

    Returns
    -------
    matplotlib.ax
    """

    if isinstance(x, core.CatmaidNeuronList):
        pass
    elif isinstance(x, core.CatmaidNeuron):
        x = core.CatmaidNeuronList(x)
    else:
        raise TypeError('Unable to work with data of type "{0}"'.format(type(x)))

    if isinstance(color, type(None)):
        color = (0.56, 0.86, 0.34)

    if not ax:
        fig, ax = plt.subplots(figsize=(8, len(x)/3 ))

    # Add some default parameters for the plotting to kwargs
    kwargs.update( { 'lw' : kwargs.get('lw', .1),
                     'ec' :  kwargs.get('ec', (1,1,1)),
                     })

    max_x = []
    for ix,n in enumerate( tqdm(x, desc='Processing') ):
        if isinstance(color, dict):
            this_c = color[n.skeleton_id]
        else:
            this_c = color

        # Get topological sort (root -> terminals)
        topology = graph_utils.node_label_sorting(n)

        # Get terminals and branch points
        bp = n.nodes[n.nodes.type=='branch'].treenode_id.values
        term = n.nodes[n.nodes.type=='end'].treenode_id.values

        # Order this neuron's segments by topology
        breaks = [ topology[0] ] + [ n for i,n in enumerate(topology) if n in bp or n in term ]
        segs = [ ( [ s for s in n.segments if s[0] == end ][0][-1], end ) for end in breaks[1:] ]

        # Now get distances for each segment
        if 'nodes_geodesic_distance_matrix' in n.__dict__:
            # If available, use geodesic distance matrix
            dist_mat = n.nodes_geodesic_distance_matrix
        else:
            # If not, compute matrix for subset of nodes
            dist_mat = graph_utils.geodesic_matrix( n, tn_ids=breaks, directed=False )

        dist = np.array([ dist_mat.loc[ s[0], s[1] ] for s in segs ] ) / 1000
        max_x.append(sum(dist))

        # Plot
        curr_dist = 0
        for k, d in enumerate(dist):
            if segs[k][1] in term:
                c = tuple( np.array(this_c) / 2 )
            else:
                c = color

            p = mpatches.Rectangle( (curr_dist, ix), d, 1, fc=c, **kwargs )
            ax.add_patch(p)
            curr_dist += d

    ax.set_xlim(0,max(max_x))
    ax.set_ylim(0,len(x))

    ax.set_yticks( np.array( range(0, len(x)) ) + .5 )
    ax.set_yticklabels( x.neuron_name )

    ax.set_xlabel('distance [um]')

    ax.set_frame_on(False)

    try:
        plt.tight_layout()
    except:
        pass

    return ax

