'''
Created on 2013-12-04

This module contains common meta data and access functions for CESM model output. 

@author: Andre R. Erler, GPL v3
'''

# external imports
import numpy as np
import netCDF4 as nc
import collections as col
import os, pickle
import osr
# from atmdyn.properties import variablePlotatts
from geodata.netcdf import DatasetNetCDF
from geodata.gdal import addGDALtoDataset, getProjFromDict, GridDefinition, addGeoLocator, GDALError
from geodata.misc import DatasetError, isInt, AxisError, DateError, isNumber
from datasets.common import translateVarNames, data_root, grid_folder, default_varatts 
from geodata.gdal import loadPickledGridDef, griddef_pickle
from WRF_experiments import Exp

# some meta data (needed for defaults)
root_folder = data_root + 'CESM/' # long-term mean folder
outfolder = root_folder + 'cesmout/' # WRF output folder
avgfolder = root_folder + 'cesmavg/' # long-term mean folder

## list of experiments
# N.B.: This is the reference list, with unambiguous, unique keys and no aliases/duplicate entries  
experiments = dict() # dictionary of experiments
Exp.defaults['avgfolder'] = lambda atts: '{0:s}/{1:s}/'.format(avgfolder,atts['name'])
# list of experiments
# historical
experiments['tb20trcn1x1'] = Exp(shortname='Ctrl', name='tb20trcn1x1', title='Ctrl (CESM)', begindate='1979-01-01', enddate='1995-01-01', grid='cesm1x1')
experiments['hab20trcn1x1'] = Exp(shortname='Ens-A', name='hab20trcn1x1', title='Ens-A (CESM)', begindate='1979-01-01', enddate='1989-01-01', grid='cesm1x1')
experiments['hbb20trcn1x1'] = Exp(shortname='Ens-B', name='hbb20trcn1x1', title='Ens-B (CESM)', begindate='1979-01-01', enddate='1989-01-01', grid='cesm1x1')
experiments['hcb20trcn1x1'] = Exp(shortname='Ens-C', name='hcb20trcn1x1', title='Ens-C (CESM)', begindate='1979-01-01', enddate='1989-01-01', grid='cesm1x1')
# mid-21st century
experiments['seaice-5r-hf'] = Exp(shortname='Seaice-2050', name='seaice-5r-hf', begindate='2045-01-01', enddate='2055-01-01', grid='cesm1x1')
experiments['htbrcp85cn1x1'] = Exp(shortname='Ctrl-2050', name='htbrcp85cn1x1', title='Ctrl (CESM, 2050)', begindate='2045-01-01', enddate='2060-01-01', grid='cesm1x1')
experiments['habrcp85cn1x1'] = Exp(shortname='Ens-A-2050', name='habrcp85cn1x1', title='Ens-A (CESM, 2050)', begindate='2045-01-01', enddate='2060-01-01', grid='cesm1x1')
experiments['hbbrcp85cn1x1'] = Exp(shortname='Ens-B-2050', name='hbbrcp85cn1x1', title='Ens-B (CESM, 2050)', begindate='2045-01-01', enddate='2060-01-01', grid='cesm1x1')
experiments['hcbrcp85cn1x1'] = Exp(shortname='Ens-C-2050', name='hcbrcp85cn1x1', title='Ens-C (CESM, 2050)', begindate='2045-01-01', enddate='2060-01-01', grid='cesm1x1')
## an alternate dictionary using short names and aliases for referencing
exps = dict()
# use short names where availalbe, normal names otherwise
for key,item in experiments.iteritems():
  exps[item.name] = item
  if item.shortname is not None: 
    exps[item.shortname] = item
  # both, short and long name are added to list
# add aliases here
CESM_exps = exps # alias for whole dict
CESM_experiments = experiments # alias for whole dict


# return name and folder
def getFolderName(name=None, experiment=None, folder=None):
  ''' Convenience function to infer and type-check the name and folder of an experiment based on various input. '''
  # N.B.: 'experiment' can be a string name or an Exp instance
  # figure out experiment name
  if experiment is None:
    if not isinstance(folder,basestring): 
      raise IOError, "Need to specify an experiment folder in order to load data."    
    # load experiment meta data
    if name in exps: experiment = exps[name]
    else: raise DatasetError, 'Dataset of name \'{0:s}\' not found!'.format(name)
  else:
    if isinstance(experiment,(Exp,basestring)):
      if isinstance(experiment,basestring): experiment = exps[experiment] 
      # root folder
      if folder is None: folder = experiment.avgfolder
      elif not isinstance(folder,basestring): raise TypeError
      # name
      if name is None: name = experiment.name
    if not isinstance(name,basestring): raise TypeError      
  # check if folder exists
  if not os.path.exists(folder): raise IOError, 'Dataset folder does not exist: {0:s}'.format(folder)
  # return name and folder
  return folder, experiment, name


## variable attributes and name
class FileType(object): pass # ''' Container class for all attributes of of the constants files. '''
# surface variables
class ATM(FileType):
  ''' Variables and attributes of the surface files. '''
  def __init__(self):
    self.atts = dict(TREFHT   = dict(name='T2', units='K'), # 2m Temperature
                     QREFHT   = dict(name='q2', units='kg/kg'), # 2m water vapor mass mixing ratio                     
                     TS       = dict(name='Ts', units='K'), # Skin Temperature (SST)
                     TSMN     = dict(name='Tmin', units='K'),   # Minimum Temperature (at surface)
                     TSMX     = dict(name='Tmax', units='K'),   # Maximum Temperature (at surface)                     
                     PRECT    = dict(name='precip', units='kg/m^2/s'), # total precipitation rate (kg/m^2/s)
                     PRECC    = dict(name='preccu', units='kg/m^2/s'), # convective precipitation rate (kg/m^2/s)
                     PRECL    = dict(name='precnc', units='kg/m^2/s'), # grid-scale precipitation rate (kg/m^2/s)
                     #NetPrecip    = dict(name='p-et', units='kg/m^2/s'), # net precipitation rate
                     #LiquidPrecip = dict(name='liqprec', units='kg/m^2/s'), # liquid precipitation rate
                     PRECSL   = dict(name='solprec', units='kg/m^2/s'), # solid precipitation rate
                     #SNOWLND   = dict(name='snow', units='kg/m^2'), # snow water equivalent
                     SNOWHLND = dict(name='snowh', units='m'), # snow depth
                     SNOWHICE = dict(name='snowhice', units='m'), # snow depth
                     ICEFRAC  = dict(name='seaice', units=''), # seaice fraction
                     SHFLX    = dict(name='hfx', units='W/m^2'), # surface sensible heat flux
                     LHFLX    = dict(name='lhfx', units='W/m^2'), # surface latent heat flux
                     QFLX     = dict(name='evap', units='kg/m^2/s'), # surface evaporation
                     FLUT     = dict(name='OLR', units='W/m^2'), # Outgoing Longwave Radiation
                     FLDS     = dict(name='GLW', units='W/m^2'), # Ground Longwave Radiation
                     FSDS     = dict(name='SWD', units='W/m^2'), # Downwelling Shortwave Radiation                     
                     PS       = dict(name='ps', units='Pa'), # surface pressure
                     PSL      = dict(name='pmsl', units='Pa'), # mean sea level pressure
                     PHIS     = dict(name='zs', units='m'), # surface elevation
                     LANDFRAC = dict(name='landfrac', units='')) # land fraction
    self.vars = self.atts.keys()    
    self.climfile = 'cesmatm{0:s}_clim{1:s}.nc' # the filename needs to be extended by ('_'+grid,'_'+period)
    self.tsfile = NotImplemented # native CESM output
# CLM variables
class LND(FileType):
  ''' Variables and attributes of the land surface files. '''
  def __init__(self):
    self.atts = dict(topo     = dict(name='zs', units='m'), # surface elevation
                     landmask = dict(name='landmask', units=''), # land mask
                     landfrac = dict(name='landfrac', units='')) # land fraction
#                      ALBEDO = dict(name='A', units=''), # Albedo
#                      SNOWC  = dict(name='snwcvr', units=''), # snow cover (binary)
#                      ACSNOM = dict(name='snwmlt', units='kg/m^2/s'), # snow melting rate 
#                      ACSNOW = dict(name='snwacc', units='kg/m^2/s'), # snow accumulation rate
#                      SFCEVP = dict(name='evap', units='kg/m^2/s'), # actual surface evaporation/ET rate
#                      POTEVP = dict(name='pet', units='kg/m^2/s'), # potential evapo-transpiration rate
#                      SFROFF = dict(name='sfroff', units='kg/m^2/s'), # surface run-off
#                      UDROFF = dict(name='ugroff', units='kg/m^2/s'), # sub-surface/underground run-off
#                      Runoff = dict(name='runoff', units='kg/m^2/s')) # total surface and sub-surface run-off
    self.vars = self.atts.keys()    
    self.climfile = 'cesmlnd{0:s}_clim{1:s}.nc' # the filename needs to be extended by ('_'+grid,'_'+period)
    self.tsfile = NotImplemented # native CESM output
# CICE variables
class ICE(FileType):
  ''' Variables and attributes of the seaice files. '''
  def __init__(self):
    self.atts = dict() # currently not implemented...                     
    self.vars = self.atts.keys()
    self.climfile = 'cesmice{0:s}_clim{1:s}.nc' # the filename needs to be extended by ('_'+grid,'_'+period)
    self.tsfile = NotImplemented # native CESM output

# axes (don't have their own file)
class Axes(FileType):
  ''' A mock-filetype for axes. '''
  def __init__(self):
    self.atts = dict(time        = dict(name='time', units='month'), # time coordinate
                     # N.B.: the time coordinate is only used for the monthly time-series data, not the LTM
                     #       the time offset is chose such that 1979 begins with the origin (time=0)
                     lon           = dict(name='lon', units='deg E'), # west-east coordinate
                     lat           = dict(name='lat', units='deg N'), # south-north coordinate
                     levgrnd = dict(name='s', units=''), # soil layers
                     lev = dict(name='lev', units='')) # hybrid pressure coordinate
    self.vars = self.atts.keys()
    self.climfile = None
    self.tsfile = None

# data source/location
fileclasses = dict(atm=ATM(), lnd=LND(), ice=ICE(), axes=Axes())


## Functions to load different types of WRF datasets

# Time-Series (monthly)
def loadCESM_TS(experiment=None, name=None, filetypes=None, varlist=None, varatts=None):
  ''' Get a properly formatted CESM dataset with monthly time-series. '''
  raise NotImplementedError


# pre-processed climatology files (varatts etc. should not be necessary) 
def loadCESM(experiment=None, name=None, grid=None, period=None, filetypes=None, varlist=None, 
            varatts=None):
  ''' Get a properly formatted monthly CESM climatology as NetCDFDataset. '''
  # prepare input  
  folder,experiment,name = getFolderName(name=name, experiment=experiment, folder=None)
  # N.B.: 'experiment' can be a string name or an Exp instance
  # period  
  if isinstance(period,(tuple,list)): pass
  elif isinstance(period,basestring): pass
  elif period is None: pass
  elif isinstance(period,(int,np.integer)) and isinstance(experiment,Exp):
    period = (experiment.beginyear, experiment.beginyear+period)
  else: raise DateError   
  if period is None or period == '': 
    raise DateError, 'Currently CESM Climatologies have to be loaded with the period explicitly specified.'
  elif isinstance(period,basestring): periodstr = '_{0:s}'.format(period)
  else: periodstr = '_{0:4d}-{1:4d}'.format(*period)  
  # generate filelist and attributes based on filetypes and domain
  if filetypes is None: filetypes = fileclasses.keys()
  elif isinstance(filetypes,(list,tuple,set)):
    filetypes = list(filetypes)  
    if 'axes' not in filetypes: filetypes.append('axes')    
  else: raise TypeError  
  atts = dict(); filelist = []
  for filetype in filetypes:
    fileclass = fileclasses[filetype]
    if fileclass.climfile is not None: # this eliminates const files
      filelist.append(fileclass.climfile) 
  if varatts is not None: atts.update(varatts)
  # default varlist
  if varlist is None: 
    varlist = atts.keys()
    for filetype in filetypes:
      if not filetype == 'axes': varlist += fileclasses[filetype].atts.keys()
  # translate varlist
  if varatts: varlist = translateVarNames(varlist, varatts) # default_varatts
  # get grid name
  if grid is None or grid == experiment.grid: gridstr = ''
  else: gridstr = '_%s'%grid.lower() # only use lower case for filenames   
  # insert grid name and period
  filenames = [filename.format(gridstr,periodstr) for filename in filelist]
  # load dataset
  dataset = DatasetNetCDF(name=name, folder=folder, filelist=filenames, varlist=varlist, axes=None, 
                          varatts=atts, multifile=False, ncformat='NETCDF4', squeeze=True)
  # check
  if len(dataset) == 0: raise DatasetError, 'Dataset is empty - check source file or variable list!'
  # add projection
  dataset = addGDALtoDataset(dataset, gridfolder=grid_folder, geolocator=True)
  # return formatted dataset
  return dataset

## Dataset API

dataset_name = 'CESM' # dataset name
root_folder # root folder of the dataset
avgfolder # root folder for monthly averages
outfolder # root folder for direct WRF output
file_pattern = 'cesm{0:s}{1:s}_clim{2:s}.nc' # filename pattern: filetype, grid, period
data_folder = root_folder # folder for user data
grid_def = {'':None} # there are too many... 
grid_res = {'':1.} # approximate grid resolution at 45 degrees latitude
default_grid = None 
# functions to access specific datasets
loadLongTermMean = None # WRF doesn't have that...
loadTimeSeries = loadCESM_TS # time-series data
loadClimatology = loadCESM # pre-processed, standardized climatology


## (ab)use main execution for quick test
if __name__ == '__main__':

#   mode = 'test_climatology'
  mode = 'pickle_grid'
  experiment = 'Ctrl'  
  filetypes = ['atm','lnd']
  grids = ['cesm1x1']; experiments = ['Ctrl']

  # pickle grid definition
  if mode == 'pickle_grid':
    
    for grid,experiment in zip(grids,experiments):
      
      print('')
      print('   ***   Pickling Grid Definition for {0:s}   ***   '.format(grid))
      print('')
      
      # load GridDefinition
      dataset = loadCESM(experiment=experiment, grid=None, filetypes=['lnd'], period=(1979,1989))
      griddef = dataset.griddef
      #del griddef.xlon, griddef.ylat      
      print griddef
      griddef.name = grid
      print('   Loading Definition from \'{0:s}\''.format(dataset.name))
      # save pickle
      filename = '{0:s}/{1:s}'.format(grid_folder,griddef_pickle.format(grid))
      if os.path.exists(filename): os.remove(filename) # overwrite
      filehandle = open(filename, 'w')
      pickle.dump(griddef, filehandle)
      filehandle.close()
      
      print('   Saving Pickle to \'{0:s}\''.format(filename))
      print('')
      
      # load pickle to make sure it is right
      del griddef
      griddef = loadPickledGridDef(grid, res=None, folder=grid_folder)
      print(griddef)
      print('')
    
  # load averaged climatology file
  elif mode == 'test_climatology':
    
    print('')
    dataset = loadCESM(experiment=experiment, grid=None, filetypes=None, period=(1979,1989)) # ['atm','lnd','ice']
    print(dataset)
    dataset.lon2D.load()
    print('')
    print(dataset.geotransform)
  
