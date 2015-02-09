'''
Created on Dec 11, 2014

A custom Axes class that provides some specialized plotting functions and retains variable information.

@author: Andre R. Erler, GPL v3
'''

# external imports
import numpy as np
import matplotlib as mpl
from matplotlib.axes import Axes
from mpl_toolkits.axes_grid.axes_divider import LocatableAxes
# internal imports
from geodata.base import Variable, Dataset, Ensemble
from geodata.misc import ListError, AxisError, ArgumentError, isEqual
from plotting.misc import smooth, getPlotValues
from collections import OrderedDict
from utils.misc import binedges, expandArgumentList, evalDistVars

## new axes class
class MyAxes(Axes): 
  ''' 
    A custom Axes class that provides some specialized plotting functions and retains variable 
    information. The custom Figure uses this Axes class by default.
  '''
  variables          = None
  variable_plotargs  = None
  dataset_plotargs   = None
  plots              = None
  title_height       = 2
  flipxy             = False
  xname              = None
  xunits             = None
  xpad               = 2 
  yname              = None
  yunits             = None
  ypad               = 0
  
  def linePlot(self, varlist, varname=None, bins=None, support=None, lineformats=None, plotatts=None,
               legend=None, llabel=True, labels=None, hline=None, vline=None, title=None,                 
               flipxy=None, xlabel=True, ylabel=True, xticks=True, yticks=True, reset_color=None, 
               xlog=False, ylog=False, xlim=None, ylim=None, lsmooth=False, lprint=False, 
               expand_list=None, lproduct='inner', method='pdf', **plotargs):
    ''' A function to draw a list of 1D variables into an axes, and annotate the plot based on 
        variable properties; extra keyword arguments (plotargs) are passed through expandArgumentList,
        before being passed to Axes.plot(). '''
    ## figure out variables
    # varlist is the list of variable objects that are to be plotted
    if isinstance(varlist,Variable): varlist = [varlist]
    elif not isinstance(varlist,(tuple,list,Ensemble)):raise TypeError
    if varname is not None:
      varlist = [getattr(var,varname) if isinstance(var,Dataset) else var for var in varlist]
    if not all([isinstance(var,Variable) for var in varlist]): raise TypeError
    for var in varlist: var.squeeze() # remove singleton dimensions
    # evaluate distribution variables on support/bins
    varlist = evalDistVars(varlist, bins=bins, support=support, method=method, ldatasetLink=True) 
    # check axis: they need to have only one axes, which has to be the same for all!
    for var in varlist: 
      if var.ndim > 1: raise AxisError, "Variable '{}' has more than one dimension; consider squeezing.".format(var.name)
      elif var.ndim == 0: raise AxisError, "Variable '{}' is a scalar; consider display as a line.".format(var.name)
    # initialize axes names and units
    self.flipxy = flipxy
    if self.flipxy: varname,varunits,axname,axunits = self.xname,self.xunits,self.yname,self.yunits
    else: axname,axunits,varname,varunits = self.xname,self.xunits,self.yname,self.yunits
    ## figure out plot arguments
    if self.variables is None: self.variables = OrderedDict() # save variables by label
    # reset color cycle
    if reset_color is False: pass
    elif reset_color is True: self.set_color_cycle(None) # reset
    else: self.set_color_cycle(reset_color)
    # figure out label list
    if labels is None: labels = self._getPlotLabels(varlist)           
    elif len(labels) != len(varlist): raise ArgumentError, "Incompatible length of varlist and labels."
    for label,var in zip(labels,varlist): self.variables[label] = var
    label_list = labels if llabel else [None]*len(labels) # used for plot labels later
    assert len(labels) == len(varlist)
    # finally, expand keyword arguments
    plotargs = self._expandArguments(labels=label_list, expand_list=expand_list, lproduct=lproduct, **plotargs)
    assert len(plotargs) == len(varlist)
    ## generate individual line plots
    plts = [] # list of plot handles
    if self.plots is None: self.plots = OrderedDict() # save plot objects by label
    # loop over variables and plot arguments
    for var,plotarg,label in zip(varlist,plotargs,labels):
      varax = var.axes[0]
      # scale axis and variable values 
      axe, axunits, axname = getPlotValues(varax, checkunits=axunits, checkname=None)
      val, varunits, varname = getPlotValues(var, checkunits=varunits, checkname=None)
      # variable and axis scaling is not always independent...
      if var.plot is not None and varax.plot is not None: 
        if varax.units != axunits and var.plot.preserve == 'area':
          val /= varax.plot.scalefactor
      # N.B.: other scaling behavior could be added here
      if lprint: print varname, varunits, np.nanmean(val), np.nanstd(val)   
      if lsmooth: val = smooth(val)
      # figure out orientation
      if self.flipxy: xx,yy = val, axe 
      else: xx,yy = axe, val
      # update plotargs from defaults
      plotarg = self._getPlotArgs(label, var, plotatts=plotatts, plotarg=plotarg)
      lineformat = plotarg.pop('lineformat',None)
      # call plot function
      if lineformat: plt = self.plot(xx, yy, lineformat, **plotarg)[0]
      else: plt = self.plot(xx, yy, **plotarg)[0]
      plts.append(plt); self.plots[label] = plt
    ## format axes
    # set plot scale (log/linear)
    self.set_xscale('log' if xlog else 'linear')
    self.set_yscale('log' if ylog else 'linear')
    # set axes limits
    if isinstance(xlim,(list,tuple)) and len(xlim)==2: self.set_xlim(*xlim)
    elif xlim is not None: raise TypeError
    if isinstance(ylim,(list,tuple)) and len(ylim)==2: self.set_ylim(*ylim)
    elif ylim is not None: raise TypeError 
    # set title
    if title is not None: self.addTitle(title)
    # set axes labels  
    if self.flipxy: self.xname,self.xunits,self.yname,self.yunits = varname,varunits,axname,axunits
    else: self.xname,self.xunits,self.yname,self.yunits = axname,axunits,varname,varunits
    # format axes ticks
    self.xTickLabels(xticks, n=len(xx), loverlap=False) # False means overlaps will be prevented
    self.yTickLabels(yticks, n=len(yy), loverlap=False)
    ## add axes labels and annotation
    # format axes labels
    self.xLabel(xlabel)
    self.yLabel(ylabel)    
    # N.B.: a typical custom label that makes use of the units would look like this: 'custom label [{1:s}]', 
    # where {} will be replaced by the appropriate default units (which have to be the same anyway)
    # add legend
    if isinstance(legend,dict): self.addLegend(**legend) 
    elif isinstance(legend,(int,np.integer,float,np.inexact)): self.addLegend(loc=legend)
    # add orientation lines
    if hline is not None: self.addHline(hline)
    if vline is not None: self.addVline(vline)
    # return handle
    return plts

  def histogram(self, varlist, varname=None, bins=None, binedgs=None, histtype='bar', lstacked=False, lnormalize=True,
                lcumulative=0, varatts=None, legend=None, colors=None, llabel=True, labels=None, align='mid', rwidth=None, 
                bottom=None, weights=None, xticks=True, yticks=True, hline=None, vline=None, title=None, reset_color=True, 
                flipxy=None, xlabel=True, ylabel=True, log=False, xlim=None, ylim=None, lprint=False, **kwargs):
    ''' A function to draw histograms of a list of 1D variables into an axes, 
        and annotate the plot based on variable properties. '''
    # varlist is the list of variable objects that are to be plotted
    if isinstance(varlist,Variable): varlist = [varlist]
    elif isinstance(varlist,(tuple,list,Ensemble)): pass
    elif isinstance(varlist,Dataset): pass
    else: raise TypeError
    if varname is not None:
      varlist = [getattr(var,varname) if isinstance(var,Dataset) else var for var in varlist]
    if not all([isinstance(var,Variable) for var in varlist]): raise TypeError
    for var in varlist: var.squeeze() # remove singleton dimensions
    # varatts are variable-specific attributes that are parsed for special keywords and then passed on to the
    if varatts is None: varatts = [dict()]*len(varlist)  
    elif isinstance(varatts,dict):
      tmp = [varatts[var.name] if var.name in varatts else dict() for var in varlist]
      if any(tmp): varatts = tmp # if any variable names were found
      else: varatts = [varatts]*len(varlist) # assume it is one varatts dict, which will be used for all variables
    elif not isinstance(varatts,(tuple,list)): raise TypeError
    if not all([isinstance(atts,dict) for atts in varatts]): raise TypeError
    # check axis: they need to have only one axes, which has to be the same for all!
    if len(varatts) != len(varlist): raise ListError, "Failed to match varatts to varlist!"  
    # line/plot label policy
    lname = not any(var.name == varlist[0].name for var in varlist[1:])
    if lname or not all(var.dataset is not None for var in varlist): ldataset = False
    elif not any(var.dataset.name == varlist[0].dataset.name for var in varlist[1:]): ldataset = True
    else: ldataset = False
    # initialize axes names and units
    self.flipxy = flipxy
    if not self.flipxy: # histogram has opposite convention
      varname,varunits,axname,axunits = self.xname,self.xunits,self.yname,self.yunits
    else:
      axname,axunits,varname,varunits = self.xname,self.xunits,self.yname,self.yunits
    # reset color cycle
    if reset_color: self.set_color_cycle(None)
    # figure out bins
    vmin = np.min([var.min() for var in varlist])
    vmax = np.max([var.max() for var in varlist])
    bins, binedgs = binedges(bins=bins, binedgs=binedgs, limits=(vmin,vmax), lcheckVar=True)
    # prepare label list
    if labels is None: labels = []; lmklblb = True
    elif len(labels) == len(varlist): lmklblb = False
    else: raise ArgumentError, "Incompatible length of label list."
    if self.variables is None: self.variables = OrderedDict()
    # loop over variables
    values = [] # list of plot handles
    for n,var in zip(xrange(len(varlist)),varlist):
      # scale variable values(axes are irrelevant)
      val, varunits, varname = getPlotValues(var, checkunits=varunits, checkname=None)
      val = val.ravel() # flatten array
      if not varname.endswith('_bins'): varname += '_bins'
      # figure out label
      if lmklblb:
        if lname: label = var.name # default label: variable name
        elif ldataset: label = var.dataset.name
        else: label = n
        labels.append(label)
      else: label = labels[n]
      # save variable  
      self.variables[label] = var
      if lprint: print varname, varunits, np.nanmean(val), np.nanstd(val)  
      # save values
      values.append(val)
    # figure out orientation
    if self.flipxy: orientation = 'horizontal' 
    else: orientation = 'vertical'
    # call histogram method of Axis
    if not llabel: labels = None 
    hdata, bin_edges, patches = self.hist(values, bins=binedgs, normed=lnormalize, weights=weights, cumulative=lcumulative, 
                                          bottom=bottom, histtype=histtype, align=align, orientation=orientation, 
                                          rwidth=rwidth, log=log, color=colors, label=labels, stacked=lstacked, **kwargs)
    del hdata; assert isEqual(bin_edges, binedgs)
    # N.B.: generally we don't need to keep the histogram results - there are other functions for that
    # set axes limits
    if isinstance(xlim,(list,tuple)) and len(xlim)==2: self.set_xlim(*xlim)
    elif xlim is not None: raise TypeError
    if isinstance(ylim,(list,tuple)) and len(ylim)==2: self.set_ylim(*ylim)
    elif ylim is not None: raise TypeError 
    # set title
    if title is not None: self.addTitle(title)
    # set axes labels  
    if not self.flipxy: 
      self.xname,self.xunits,self.yname,self.yunits = varname,varunits,axname,axunits
    else: 
      self.xname,self.xunits,self.yname,self.yunits = axname,axunits,varname,varunits
    # format axes ticks
    self.xTickLabels(xticks, loverlap=False)
    self.yTickLabels(yticks, loverlap=False)
    # format axes labels
    self.xLabel(xlabel)
    self.yLabel(ylabel)    
    # N.B.: a typical custom label that makes use of the units would look like this: 'custom label [{1:s}]', 
    # where {} will be replaced by the appropriate default units (which have to be the same anyway)
    # make monthly ticks
    if self.xname == 'time' and self.xunits == 'month':
      if len(xticks) == 12 or len(xticks) == 13:
        self.xaxis.set_minor_locator(mpl.ticker.AutoMinorLocator(2)) # self.minorticks_on()
    # add legend
    if isinstance(legend,dict): self.addLegend(**legend) 
    elif isinstance(legend,(int,np.integer,float,np.inexact)): self.addLegend(loc=legend)
    # add orientation lines
    if hline is not None: self.addHline(hline)
    if vline is not None: self.addVline(vline)
    # return handle
    return bins, patches # bins can be used as support for distributions
  
  def addHline(self, hline, **kwargs):
    ''' add one or more horizontal lines to the plot '''
    if 'color' not in kwargs: kwargs['color'] = 'black'
    if not isinstance(hline,(list,tuple,np.ndarray)): hline = (hline,)
    lines = []
    for hl in list(hline):
      if isinstance(hl,(int,np.integer,float,np.inexact)): 
        lines.append(self.axhline(y=hl, **kwargs))
      else: raise TypeError, hl
    return lines
  
  def addVline(self, vline, **kwargs):
    ''' add one or more horizontal lines to the plot '''
    if 'color' not in kwargs: kwargs['color'] = 'black'
    if not isinstance(vline,(list,tuple,np.ndarray)): vline = (vline,)
    lines = []
    for hl in list(vline):
      if isinstance(hl,(int,np.integer,float,np.inexact)): 
        lines.append(self.axvline(x=hl, **kwargs))
      else: raise TypeError, hl.__class__
    return lines    
  
  def addTitle(self, title, **kwargs):
    ''' add title and adjust margins '''
    if 'fontsize' not in kwargs: kwargs['fontsize'] = 'medium'
    title_height = kwargs.pop('title_height', self.title_height)
    pos = self.get_position()
    pos = pos.from_bounds(x0=pos.x0, y0=pos.y0, width=pos.width, height=pos.height-title_height)    
    self.set_position(pos)
    return self.set_title(title, kwargs)
  
  def addLegend(self, loc=0, **kwargs):
      ''' add a legend to the axes '''
      if 'fontsize' not in kwargs and self.get_yaxis().get_label():
        kwargs['fontsize'] = self.get_yaxis().get_label().get_fontsize()
      kwargs['loc'] = loc
      self.legend(**kwargs)
  
  def _expandArguments(self, labels=None, expand_list=None, lproduct='inner', **plotargs):
    ''' function to expand arguments while applying some default treatments; plural forms of some
        plot arguments are automatically converted and expanded for all plotargs '''
    # line style parameters is just a list of line styles for each plot
    if lproduct == 'inner':
      if expand_list is None: expand_list = []
      expand_list.append('label')
      # loop over special arguments that allow plural form
      for name in ('lineformats','linestyles','colors','markers'):
        if name in plotargs:
          args = plotargs.pop(name)  
          if not isinstance(args,(tuple,list)): 
            if not all([isinstance(arg,basestring) for arg in args]): raise TypeError
            if len(labels) != len(args): raise ListError, "Failed to match linestyles to varlist!"
            expand_list.append(name[:-1]) # cut off trailing 's' (i.e. proper singular form)
      # actually expand list 
      plotargs = expandArgumentList(label=labels, expand_list=expand_list, lproduct=lproduct, **plotargs)
    else: raise NotImplementedError, lproduct
    # return cleaned-up and expanded plot arguments
    return plotargs
    
  def _getPlotLabels(self, varlist):
    ''' figure out reasonable plot labels based variable and dataset names '''
    # figure out line/plot label policy
    if not any(var.name == varlist[0].name for var in varlist[1:]):
      labels = [var.name for var in varlist]
    elif ( all(var.dataset is not None for var in varlist) and
           not any(var.dataset.name == varlist[0].dataset.name for var in varlist[1:]) ):
      labels = [var.dataset.name for var in varlist]
    else: 
      labels = range(len(varlist))
    return labels
  
  def _getPlotArgs(self, label, var, plotatts=None, plotarg=None):
    ''' function to return plotting arguments/styles based on defaults and explicit arguments '''
    args = dict()
    # apply figure/project defaults
    if label == var.name: # variable name has precedence
      if var.dataset is not None and self.dataset_plotargs is not None: 
        args.update(self.dataset_plotargs.get(var.dataset.name,{}))
      if self.variable_plotargs is not None: args.update(self.variable_plotargs.get(var.name,{}))
    else: # dataset name has precedence
      if self.variable_plotargs is not None: args.update(self.variable_plotargs.get(var.name,{}))
      if var.dataset is not None and self.dataset_plotargs is not None: 
        args.update(self.dataset_plotargs.get(var.dataset.name,{}))
    # apply axes/local defaults
    if plotatts is not None: args.update(plotatts.get(label,{}))
    if plotarg is not None: args.update(plotarg)
    # return dictionary with keyword argument for plotting function
    return args    
  
  def xLabel(self, xlabel, name=None, units=None):
    ''' format x-axis label '''
    if xlabel is not None:
      xticks = self.get_xaxis().get_ticklabels()
      # len(xticks) > 0 is necessary to avoid errors with AxesGrid, which removes invisible tick labels      
      if len(xticks) > 0 and xticks[-1].get_visible(): 
        name = self.xname if name is None else name
        units = self.xunits if units is None else units
        xlabel = self._axLabel(xlabel, name, units)
        # N.B.: labelpad is ignored by AxesGrid
        self.set_xlabel(xlabel, labelpad=self.xpad)
    return xlabel    
  def yLabel(self, ylabel, name=None, units=None):
    ''' format y-axis label '''
    if ylabel is not None:
      yticks = self.get_yaxis().get_ticklabels()
      if len(yticks) > 0 and yticks[-1].get_visible(): 
        name = self.yname if name is None else name
        units = self.yunits if units is None else units
        ylabel = self._axLabel(ylabel, name, units)
        # N.B.: labelpad is ignored by AxesGrid
        self.set_ylabel(ylabel, labelpad=self.ypad)
    return ylabel    
  def _axLabel(self, label, name, units):
    ''' helper method to format axes lables '''
    if label is True: 
      if not name and not units: label = ''
      elif not units: label = '{0:s}'.format(name)
      elif not name: label = '[{:s}]'.format(units)
      else: label = '{0:s} [{1:s}]'.format(name,units)
    elif label is False or label is None: label = ''
    elif isinstance(label,basestring): label = label.format(name,units)
    else: raise ValueError, label
    return label
    
  def xTickLabels(self, xticks, n=None, loverlap=False):
    ''' format x-tick labels '''
    xticks = self._tickLabels(xticks, self.get_xaxis())
    yticks = self.get_yaxis().get_ticklabels()
    if not loverlap and len(xticks) > 0 and (
        len(yticks) == 0 or not yticks[-1].get_visible() ):
        xticks[0].set_visible(False)
    if n is not None: self._minorTickLabels(xticks, n, self.xaxis)
    return xticks
  def yTickLabels(self, yticks, n=None, loverlap=False):
    ''' format y-tick labels '''
    xticks = self.get_xaxis().get_ticklabels()
    yticks = self._tickLabels(yticks, self.get_yaxis())
    if not loverlap and len(yticks) > 0 and (
        len(xticks) == 0 or not xticks[-1].get_visible() ):
        yticks[0].set_visible(False)
    if n is not None: self._minorTickLabels(yticks, n, self.yaxis)      
    return yticks
  def _minorTickLabels(self, ticks, n, axis):
    ''' helper method to format axes ticks '''
    nmaj = len(ticks)
    if n%nmaj == 0: 
      nmin = n//nmaj
      axis.set_minor_locator(mpl.ticker.AutoMinorLocator(nmin))
  def _tickLabels(self, ticks, axis):
    ''' helper method to format axes ticks '''
    if ticks is True: 
      ticklist = axis.get_ticklabels()
    elif ticks is False: 
      ticklist = axis.get_ticklabels()
      for tick in ticklist: tick.set_visible(False)
      ticklist = []
    elif isinstance(ticks,list,tuple): 
      axis.set_ticklabels(ticks)
      ticklist = axis.get_ticklabels()
    else: raise ValueError, ticks
    return ticklist
      
  # add subplot/axes label (alphabetical indexing, byt default)
  def addLabel(self, label, loc=1, lstroke=False, lalphabet=True, size=None, prop=None, **kwargs):
    from string import lowercase # lowercase letters
    from matplotlib.offsetbox import AnchoredText 
    from matplotlib.patheffects import withStroke    
    # settings
    if prop is None: prop = dict()
    if not size: prop['size'] = 'large'
    args = dict(pad=0., borderpad=1.5, frameon=False)
    args.update(kwargs)
    # create label    
    if lalphabet and isinstance(label,int):
      label = '('+lowercase[label]+')'    
    at = AnchoredText(label, loc=loc, prop=prop, **args)
    self.add_artist(at) # add to axes
    if lstroke: 
      at.txt._text.set_path_effects([withStroke(foreground="w", linewidth=3)])
        


# a new class that combines the new axes with LocatableAxes for use with AxesGrid 
class MyLocatableAxes(LocatableAxes,MyAxes):
  ''' A new Axes class that adds functionality from MyAxes to a LocatableAxes for use in AxesGrid '''


if __name__ == '__main__':
    pass