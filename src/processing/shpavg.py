'''
Created on 2014-01-26

A script to extract time-series averaged over the area defined by a collection of shapes (shapefiles).
Adapted from regrid.py.

@author: Andre R. Erler, GPL v3
'''

# external imports
import os # check if files are present
import numpy as np
from importlib import import_module
from datetime import datetime
import logging   
from collections import OrderedDict
# internal imports
from geodata.misc import DatasetError, DateError, isInt, printList
from geodata.netcdf import DatasetNetCDF
from geodata.base import Dataset
from datasets import gridded_datasets
from datasets.common import getFileName
from processing.multiprocess import asyncPoolEC
from processing.process import CentralProcessingUnit
# WRF specific
from datasets.WRF import loadWRF, loadWRF_TS
from projects.WRF_experiments import WRF_exps
# CESM specific
from datasets.CESM import loadCESM, loadCESM_TS, CESM_exps

# import shape objects
from datasets.WSC import basins
from datasets.EC import provinces


# worker function that is to be passed to asyncPool for parallel execution; use of the decorator is assumed
def performExtraction(dataset, mode, shape_name, shape_dict, dataargs, loverwrite=False, varlist=None, lwrite=True, lreturn=False,
                      ldebug=False, lparallel=False, pidstr='', logger=None):
  ''' worker function to extract point data from gridded dataset '''  
  # input checking
  if not isinstance(dataset,basestring): raise TypeError
  if not isinstance(dataargs,dict): raise TypeError # all dataset arguments are kwargs 
  if not isinstance(shape_dict, OrderedDict): raise TypeError # function to load station dataset
  if lparallel: 
    if not lwrite: raise IOError, 'In parallel mode we can only write to disk (i.e. lwrite = True).'
    if lreturn: raise IOError, 'Can not return datasets in parallel mode (i.e. lreturn = False).'
  
  # logging
  if logger is None: # make new logger     
    logger = logging.getLogger() # new logger
    logger.addHandler(logging.StreamHandler())
  else:
    if isinstance(logger,basestring): 
      logger = logging.getLogger(name=logger) # connect to existing one
    elif not isinstance(logger,logging.Logger): 
      raise TypeError, 'Expected logger ID/handle in logger KW; got {}'.format(str(logger))

  # load source
  if dataset == 'WRF': 
    # WRF datasets
    module = import_module('datasets.WRF')
    exp = dataargs['experiment']    
    dataset_name = exp.name
    domain = dataargs['domain']
    # figure out period
    period = dataargs['period']
    if period is None: pass
    elif isinstance(period,(int,np.integer)):
      beginyear = int(exp.begindate[0:4])
      period = (beginyear, beginyear+period)
    elif len(period) != 2 and all(isInt(period)): raise DateError
    del exp
    # identify file and domain
    if len(dataargs['filetypes']) > 1: raise DatasetError # process only one file at a time
    filetype = dataargs['filetypes'][0]
    if isinstance(domain,(list,tuple)): domain = domain[0]
    if not isinstance(domain, (np.integer,int)): raise DatasetError
    # load source data
    if mode == 'climatology':
      source = loadWRF(experiment=dataset_name, name=None, domains=domain, grid=None, period=period, 
                       filetypes=[filetype], varlist=varlist, varatts=None, lconst=True) # still want topography...
    elif mode == 'time-series':
      source = loadWRF_TS(experiment=dataset_name, name=None, domains=domain, grid=None, 
                       filetypes=[filetype], varlist=varlist, varatts=None, lconst=True) # still want topography...
    else: raise NotImplementedError, "Unrecognized Mode: '{:s}'".format(mode)
    # check period
    if period is None: periodstr = '' 
    else: periodstr = '{0:4d}-{1:4d}'.format(*period)
    if 'period' in source.atts and periodstr != source.atts.period: # a NetCDF attribute
      raise DateError, "Specifed period is inconsistent with netcdf records: '{:s}' != '{:s}'".format(periodstr,source.atts.period)
    datamsgstr = "Processing WRF '{:s}'-file from Experiment '{:s}' (d{:02d})".format(filetype, dataset_name, domain)
  elif dataset == 'CESM': 
    # CESM datasets
    module = import_module('datasets.CESM')
    exp = dataargs['experiment']    
    dataset_name = exp.name
    # figure out period
    period = dataargs['period']
    if period is None: pass
    elif isinstance(period,(int,np.integer)):
      beginyear = int(exp.begindate[0:4])
      period = (beginyear, beginyear+period)
    elif len(period) != 2 and all(isInt(period)): raise DateError
    del exp
    # identify file
    if len(dataargs['filetypes']) > 1: raise DatasetError # process only one file at a time
    filetype = dataargs['filetypes'][0]        
    # load source data 
    load3D = dataargs.pop('load3D',None) # if 3D fields should be loaded (default: False)
    if mode == 'climatology':
      source = loadCESM(experiment=dataset_name, name=None, grid=None, period=period, filetypes=[filetype],  
                        varlist=varlist, varatts=None, load3D=load3D, translateVars=None)
    elif mode == 'time-series':
      source = loadCESM_TS(experiment=dataset_name, name=None, grid=None, filetypes=[filetype],  
                           varlist=varlist, varatts=None, load3D=load3D, translateVars=None)
    else: raise NotImplementedError, "Unrecognized Mode: '{:s}'".format(mode)
    # check period
    if period is None: periodstr = ''
    else: periodstr = '{0:4d}-{1:4d}'.format(*period)
    if 'period' in source.atts and periodstr != source.atts.period: # a NetCDF attribute
      raise DateError, "Specifed period is inconsistent with netcdf records: '{:s}' != '{:s}'".format(periodstr,source.atts.period)
    datamsgstr = "Processing CESM '{:s}'-file from Experiment '{:s}'".format(filetype, dataset_name)  
  elif dataset == dataset.upper():
    # observational datasets
    module = import_module('datasets.{0:s}'.format(dataset))      
    dataset_name = module.dataset_name
    resolution = dataargs['resolution']
    if resolution: grid_name = '{0:s}_{1:s}'.format(dataset_name,resolution)
    else: grid_name = dataset_name   
    # figure out period
    period = dataargs['period']    
    if period is None: pass
    elif isinstance(period,(int,np.integer)):
      period = (1979, 1979+period) # they all begin in 1979
    elif len(period) != 2 and not all(isInt(period)): raise DateError
    # load pre-processed climatology
    if mode == 'climatology':
      source = module.loadClimatology(name=dataset_name, period=period, grid=None, resolution=resolution,  
                                      varlist=varlist, varatts=None, folder=module.avgfolder, filelist=None)
    elif mode == 'time-series':
      source = module.loadTimeSeries(name=dataset_name, grid=None, resolution=resolution,  
                                      varlist=varlist, varatts=None, folder=None, filelist=None)
    else: raise NotImplementedError, "Unrecognized Mode: '{:s}'".format(mode)
    datamsgstr = "Processing Dataset '{:s}'".format(dataset_name)
    # check period
    if period is None: 
      if mode == 'climatology': periodstr = 'Long-Term Mean'
      else: periodstr = ''
    else: periodstr = '{0:4d}-{1:4d}'.format(*period)
  else:
    raise DatasetError, "Dataset '{:s}' not found!".format(dataset)
  del dataargs
  # common message
  if mode == 'climatology': opmsgstr = "Averaging Data from Climatology ({:s})".format(periodstr)
  elif mode == 'time-series': opmsgstr = "Averaging Data from Time-series"
  else: raise NotImplementedError, "Unrecognized Mode: '{:s}'".format(mode)        
  # print feedback to logger
  logger.info('\n{0:s}   ***   {1:^65s}   ***   \n{0:s}   ***   {2:^65s}   ***   \n'.format(pidstr,datamsgstr,opmsgstr))
  if not lparallel and ldebug:
    logger.info('\n'+str(source)+'\n')
  # determine age of oldest source file
  if not loverwrite:
    sourceage = datetime.today()
    for filename in source.filelist:
      age = datetime.fromtimestamp(os.path.getmtime(filename))
      sourceage = age if age < sourceage else sourceage    
          
  # prepare target dataset
  if dataset == 'WRF':
    stnstr = '_{}'.format(shape_name) # use name as "grid" designation for station data
    periodstr = '_{}'.format(periodstr) if periodstr else ''
    if lwrite:
      if mode == 'climatology': filename = module.clim_file_pattern.format(filetype,domain,stnstr,periodstr)
      elif mode == 'time-series': filename = module.ts_file_pattern.format(filetype,domain,stnstr)
      else: raise NotImplementedError
      avgfolder = '{0:s}/{1:s}/'.format(module.avgfolder,dataset_name)    
  elif dataset == 'CESM':
    stnstr = '_{}'.format(shape_name) # use name as "grid" designation for station data
    periodstr = '_{}'.format(periodstr) if periodstr else ''
    if lwrite:
      if mode == 'climatology': filename = module.clim_file_pattern.format(filetype,stnstr,periodstr)
      elif mode == 'time-series': filename = module.ts_file_pattern.format(filetype,stnstr)
      else: raise NotImplementedError
      avgfolder = '{0:s}/{1:s}/'.format(module.avgfolder,dataset_name)    
  elif dataset == dataset.upper(): # observational datasets
    if lwrite:
      avgfolder = module.avgfolder
      filename = getFileName(grid=shape_name, period=period, name=grid_name, filetype=mode)      
  else: raise DatasetError
  if ldebug: filename = 'test_' + filename
  if not os.path.exists(avgfolder): raise IOError, "Dataset folder '{:s}' does not exist!".format(avgfolder)
  lskip = False # else just go ahead
  if lwrite:
    if lreturn: 
      tmpfilename = filename # no temporary file if dataset is passed on (can't rename the file while it is open!)
    else: 
      if lparallel: tmppfx = 'tmp_{:s}_{:s}_'.format(shape_name,pidstr[1:-1])
      else: tmppfx = 'tmp_{:s}_'.format(shape_name)
      tmpfilename = tmppfx + filename      
    filepath = avgfolder + filename
    tmpfilepath = avgfolder + tmpfilename
    if os.path.exists(filepath): 
      if not loverwrite: 
        age = datetime.fromtimestamp(os.path.getmtime(filepath))
        # if source file is newer than sink file or if sink file is a stub, recompute, otherwise skip
        if age > sourceage and os.path.getsize(filepath) > 1e6: lskip = True
        # N.B.: NetCDF files smaller than 1MB are usually incomplete header fragments from a previous crashed
      if not lskip: os.remove(filepath) # recompute
  
  # depending on last modification time of file or overwrite setting, start computation, or skip
  if lskip:        
    # print message
    skipmsg =  "\n{:s}   >>>   Skipping: file '{:s}' in dataset '{:s}' already exists and is newer than source file.".format(pidstr,filename,dataset_name)
    skipmsg += "\n{:s}   >>>   ('{:s}')\n".format(pidstr,filepath)
    logger.info(skipmsg)              
  else:
          
    ## create new sink/target file
    # set attributes   
    atts=source.atts.copy()
    atts['period'] = periodstr[1:] if periodstr else 'time-series' 
    atts['name'] = dataset_name; atts['shapes'] = shape_name
    atts['title'] = 'Area Averages from {:s} {:s}'.format(dataset_name,mode.title())
    # make new dataset
    if lwrite: # write to NetCDF file 
      if os.path.exists(tmpfilepath): os.remove(tmpfilepath) # remove old temp files 
      sink = DatasetNetCDF(folder=avgfolder, filelist=[tmpfilename], atts=atts, mode='w')
    else: sink = Dataset(atts=atts) # ony create dataset in memory
    
    # initialize processing
    CPU = CentralProcessingUnit(source, sink, varlist=varlist, tmp=False, feedback=ldebug)
  
    # extract data at station locations
    CPU.ShapeAverage(shape_dict=shape_dict, shape_name=shape_name, flush=True)
    # get results    
    CPU.sync(flush=True)
    
    # print dataset
    if not lparallel and ldebug:
      logger.info('\n'+str(sink)+'\n')   
    # write results to file
    if lwrite:
      sink.sync()
      writemsg =  "\n{:s}   >>>   Writing to file '{:s}' in dataset {:s}".format(pidstr,filename,dataset_name)
      writemsg += "\n{:s}   >>>   ('{:s}')\n".format(pidstr,filepath)
      logger.info(writemsg)      
      
      # rename file to proper name
      if not lreturn:
        sink.unload(); sink.close(); del sink # destroy all references 
        if os.path.exists(filepath): os.remove(filepath) # remove old file
        os.rename(tmpfilepath,filepath)
      # N.B.: there is no temporary file if the dataset is returned, because an open file can't be renamed
        
    # clean up and return
    source.unload(); del source#, CPU
    if lreturn:      
      return sink # return dataset for further use (netcdf file still open!)
    else:            
      return 0 # "exit code"
    # N.B.: garbage is collected in multi-processing wrapper


if __name__ == '__main__':
  
  ## read arguments
  # number of processes NP 
  if os.environ.has_key('PYAVG_THREADS'): 
    NP = int(os.environ['PYAVG_THREADS'])
  else: NP = None
  # run script in debug mode
  if os.environ.has_key('PYAVG_DEBUG'): 
    ldebug =  os.environ['PYAVG_DEBUG'] == 'DEBUG' 
  else: ldebug = False # i.e. append
  # run script in batch or interactive mode
  if os.environ.has_key('PYAVG_BATCH'): 
    lbatch =  os.environ['PYAVG_BATCH'] == 'BATCH' 
  else: lbatch = False # i.e. append  
  # re-compute everything or just update 
  if os.environ.has_key('PYAVG_OVERWRITE'): 
    loverwrite =  os.environ['PYAVG_OVERWRITE'] == 'OVERWRITE' 
  else: loverwrite = ldebug # False means only update old files
  
  lbatch = True # for now
  
  # default settings
  if not lbatch:
    NP = 2 ; ldebug = False # for quick computations
#     NP = 1 ; ldebug = True # just for tests
#     modes = ('time-series',) # 'climatology','time-series'
    modes = ('climatology',) # 'climatology','time-series'
#     loverwrite = False
    loverwrite = True
    varlist = None
#     varlist = ['precip',]
    periods = []
#     periods += [1]
#     periods += [3]
#     periods += [5]
#     periods += [10]
#     periods += [15]
#     periods += [30]
    # Observations/Reanalysis
    datasets = []; resolutions = None
#     lLTM = False # also average the long-term mean climatologies
    lLTM = True 
    resolutions = {'CRU':'','GPCC':'05','NARR':'','CFSR':'05'}
#     datasets += ['PCIC','PRISM']; periods = None; lLTM = True
#     datasets += ['CFSR']; resolutions = {'CFSR':'031'}
#     datasets += ['NARR']
#     datasets += ['GPCC']; resolutions = {'GPCC':['025','05','10','25']}
    datasets += ['GPCC']; resolutions = {'GPCC':['025']}
#     datasets += ['CRU']
    # CESM experiments (short or long name) 
    load3D = False
    CESM_experiments = [] # use None to process all CESM experiments
#     CESM_experiments += ['Ctrl-1']
#     CESM_experiments += ['Ctrl-1', 'Ctrl-A', 'Ctrl-B', 'Ctrl-C']
#     CESM_experiments += ['Ctrl-1-2050', 'Ctrl-A-2050', 'Ctrl-B-2050', 'Ctrl-C-2050']
#     CESM_experiments += ['Ens', 'Ens-2050', 'Ens-2100']
#     CESM_filetypes = ['atm'] # ,'lnd'
    CESM_filetypes = ['atm','lnd']
    # WRF experiments (short or long name)
    WRF_experiments = [] # use None to process all CESM experiments
#     WRF_experiments += ['max-ens-A']
#     WRF_experiments += ['max-ctrl','max-ens-A','max-ens-B','max-ens-C',]
#     WRF_experiments += ['max-ctrl-2050','max-ens-A-2050','max-ens-B-2050','max-ens-C-2050',]    
#     WRF_experiments += ['max-ens','max-ens-2050','max-ens-2100'] # requires different implementation...
    # other WRF parameters 
    domains = None # domains to be processed
#     domains = (2,) # domains to be processed
#     WRF_filetypes = ('srfc','xtrm','plev3d','hydro','lsm') # filetypes to be processed # ,'rad'
    WRF_filetypes = ('hydro','xtrm','srfc','lsm') # filetypes to be processed
#     WRF_filetypes = ('hydro',)
#     WRF_filetypes = ('xtrm','lsm') # filetypes to be processed    
    #WRF_filetypes = ('const',); periods = None
    # define shape data  
    shape_name = 'shpavg' # Canadian shapes
    shapes = dict()
    shapes['basins'] = None # river basins (in Canada) from WSC module
    shapes['provinces'] = None # Canadian provinces from EC module
#     shapes['basins'] = ['FRB'] # river basins (in Canada) from WSC module
#     shapes['provinces'] = ['BC'] # Canadian provinces from EC module
  else:
    NP = NP or 3 # time-series might take more memory or overheat...
    #modes = ('climatology','time-series')
    modes = ('time-series',) # too many small files...
    loverwrite = False
    varlist = None # process all variables
    periods = None # (5,10,15,) # climatology periods to process
    # Datasets
    datasets = None # process all applicable
    # N.B.: processing 0.5 deg CRU & GPCC time-series at the same time, can crash the system
    resolutions = None # process all applicable
    lLTM = False # again, not necessary
    # CESM
    load3D = True # doesn't hurt... data is small
    CESM_experiments = []
    CESM_filetypes = ('atm','lnd')    
    # WRF
    WRF_experiments = [] # process all WRF experiments
    WRF_experiments += ['max-ctrl','max-ens-A','max-ens-B','max-ens-C',]
    WRF_experiments += ['erai-max','cfsr-max','max-seaice-2050','max-seaice-2100']  
    WRF_experiments += ['max-ctrl-2050','max-ens-A-2050','max-ens-B-2050','max-ens-C-2050',]
    WRF_experiments += ['max-ctrl-2100','max-ens-A-2100','max-ens-B-2100','max-ens-C-2100',]
    WRF_experiments += ['new-ctrl', 'new-ctrl-2050', 'new-ctrl-2100', 'cfsr-new', ] # new standard runs (arb3)     
    WRF_experiments += ['ctrl-1', 'ctrl-2050', 'ctrl-2100'] # new standard runs (arb3)
    WRF_experiments += ['old-ctrl', 'old-ctrl-2050', 'old-ctrl-2100'] # new standard runs (arb3)
    WRF_experiments += ['max-ens','max-ens-2050','max-ens-2100'] # requires different implementation...
    domains = None # domains to be processed
    WRF_filetypes = ('srfc','xtrm','plev3d','hydro','lsm') # process all filetypes except 'rad'
    # define shape data
    shape_name = 'shpavg'
    shapes = dict()
    shapes['basins'] = None # all river basins (in Canada) from WSC module
    shapes['provinces'] = None # all Canadian provinces from EC module
    
  ## process arguments    
  if periods is None: periods = [None]
  # expand experiments
  if WRF_experiments is None: WRF_experiments = WRF_exps.values() # do all 
  else: WRF_experiments = [WRF_exps[exp] for exp in WRF_experiments]
  if CESM_experiments is None: CESM_experiments = CESM_exps.values() # do all 
  else: CESM_experiments = [CESM_exps[exp] for exp in CESM_experiments]  
  # expand datasets and resolutions
  if datasets is None: datasets = gridded_datasets
  # expand shapes (and enforce consistent sorting)
  if shapes['basins'] is None:
    items = basins.keys()
    if not isinstance(basins, OrderedDict): items.sort()
    shapes['basins'] = items
  if shapes['provinces'] is None:
    items = provinces.keys()
    if not isinstance(provinces, OrderedDict): items.sort()     
    shapes['provinces'] = items
      
  # add shapes of different categories
  shape_dict = OrderedDict()
  for shp in shapes['provinces']: shape_dict[shp] = provinces[shp]
  for shp in shapes['basins']: shape_dict[shp] = basins[shp]
    
  # print an announcement
  if len(WRF_experiments) > 0:
    print('\n Averaging from WRF Datasets:')
    print([exp.name for exp in WRF_experiments])
  if len(CESM_experiments) > 0:
    print('\n Averaging from CESM Datasets:')
    print([exp.name for exp in CESM_experiments])
  if len(datasets) > 0:
    print('\n Averaging from Observational Datasets:')
    print(datasets)
  print('\n Using Shapefiles:')
  for shptype,shplst in shapes.iteritems():
    print('   {0:s} {1:s}'.format(shptype,printList(shplst)))
  print('\nOVERWRITE: {0:s}\n'.format(str(loverwrite)))

  
  ## construct argument list
  args = []  # list of job packages (commands)
  # loop over modes
  for mode in modes:
    # only climatology mode has periods    
    if mode == 'climatology': periodlist = periods
    elif mode == 'time-series': periodlist = (None,)
    else: raise NotImplementedError, "Unrecognized Mode: '{:s}'".format(mode)

    # observational datasets (grid depends on dataset!)
    for dataset in datasets:
      mod = import_module('datasets.{0:s}'.format(dataset))
      if isinstance(resolutions,dict):
        if dataset not in resolutions: resolutions[dataset] = ('',)
        elif not isinstance(resolutions[dataset],(list,tuple)): resolutions[dataset] = (resolutions[dataset],)                
      elif resolutions is not None: raise TypeError                                
      if mode == 'climatology':
        # some datasets come with a climatology 
        if lLTM:
          if resolutions is None: dsreses = mod.LTM_grids
          elif isinstance(resolutions,dict): dsreses = [dsres for dsres in resolutions[dataset] if dsres in mod.LTM_grids]  
          for dsres in dsreses: 
            args.append( (dataset, mode, shape_name, shape_dict, dict(period=None, resolution=dsres)) ) # append to list
        # climatologies derived from time-series
        if resolutions is None: dsreses = mod.TS_grids
        elif isinstance(resolutions,dict): dsreses = [dsres for dsres in resolutions[dataset] if dsres in mod.TS_grids]  
        for dsres in dsreses:
          for period in periodlist:
            args.append( (dataset, mode, shape_name, shape_dict, dict(period=period, resolution=dsres)) ) # append to list            
      elif mode == 'time-series': 
        # regrid the entire time-series
        if resolutions is None: dsreses = mod.TS_grids
        elif isinstance(resolutions,dict): dsreses = [dsres for dsres in resolutions[dataset] if dsres in mod.TS_grids]  
        for dsres in dsreses:
          args.append( (dataset, mode, shape_name, shape_dict, dict(period=None, resolution=dsres)) ) # append to list            
    
    # CESM datasets
    for experiment in CESM_experiments:
      for filetype in CESM_filetypes:
        for period in periodlist:
          # arguments for worker function: dataset and dataargs       
          args.append( ('CESM', mode, shape_name, shape_dict, dict(experiment=experiment, filetypes=[filetype], period=period, load3D=load3D)) )
    # WRF datasets
    for experiment in WRF_experiments:
      for filetype in WRF_filetypes:
        # effectively, loop over domains
        if domains is None:
          tmpdom = range(1,experiment.domains+1)
        else: tmpdom = domains
        for domain in tmpdom:
          for period in periodlist:
            # arguments for worker function: dataset and dataargs       
            args.append( ('WRF', mode, shape_name, shape_dict, dict(experiment=experiment, filetypes=[filetype], domain=domain, period=period)) )
      
  # static keyword arguments
  kwargs = dict(loverwrite=loverwrite, varlist=varlist)
          
  ## call parallel execution function
  ec = asyncPoolEC(performExtraction, args, kwargs, NP=NP, ldebug=ldebug, ltrialnerror=True)
  # exit with fraction of failures (out of 10) as exit code
  exit(int(10+np.ceil(10.*ec/len(args))) if ec > 0 else 0)