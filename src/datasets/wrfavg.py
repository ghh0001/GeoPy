'''
Created on 2013-10-21

Script to produce climatology files from monthly mean time-series' for all or a subset of available WRF experiments.

@author: Andre R. Erler, GPL v3
'''

# external
import numpy as np
import os
from datetime import datetime
# internal
from geodata.netcdf import DatasetNetCDF, VarNC
from geodata.gdal import GridDefinition
from geodata.misc import isInt
from datasets.common import name_of_month, days_per_month, getCommonGrid
from processing.process import CentralProcessingUnit, DateError
from processing.multiprocess import asyncPoolEC
# WRF specific
from datasets.WRF import loadWRF_TS, fileclasses, avgfolder
from plotting.ARB_settings import WRFname


def computeClimatology(experiment, filetype, domain, periods=None, offset=0, griddef=None, loverwrite=False,
                       lparallel=False, pidstr='', logger=None):
  ''' worker function to compute climatologies for given file parameters. '''
  # input type checks
  if not isinstance(experiment,basestring): raise TypeError
  if not isinstance(filetype,basestring): raise TypeError
  if not isinstance(domain,(np.integer,int)): raise TypeError
  if periods is not None and not (isinstance(periods,(tuple,list)) and isInt(periods)): raise TypeError
  if not isinstance(offset,(np.integer,int)): raise TypeError
  if not isinstance(loverwrite,(bool,np.bool)): raise TypeError  
  if griddef is not None and not isinstance(griddef,GridDefinition): raise TypeError
  
  #if pidstr == '[proc01]': raise TypeError # to test error handling

  # load source
  fileclass = fileclasses[filetype] # used for target file name
  logger.info('\n\n{0:s}   ***   Processing Experiment {1:<15s}   ***   '.format(pidstr,"'%s'"%experiment) +
        '\n{0:s}   ***   {1:^37s}   ***   \n'.format(pidstr,"'%s'"%fileclass.tsfile.format(domain)))
  source = loadWRF_TS(experiment=experiment, filetypes=[filetype], domains=domain) # comes out as a tuple...
  if not lparallel: 
    logger.info('\n'+str(source)+'\n')
  # determine age of oldest source file
  if not loverwrite:
    sourceage = datetime.today()
    for filename in source.filelist:
      age = datetime.fromtimestamp(os.path.getmtime(filename))
      sourceage = age if age < sourceage else sourceage
  
  # figure out start date
  filebegin = int(source.atts.begin_date.split('-')[0]) # first element is the year
  fileend = int(source.atts.end_date.split('-')[0]) # first element is the year
  begindate = offset + filebegin
  if not ( filebegin <= begindate <= fileend ): raise DateError  
  
  ## loop over periods
  if periods is None: periods = [begindate-fileend]
#   periods.sort(reverse=True) # reverse, so that largest chunk is done first
  for period in periods:       
            
    # figure out period
    enddate = begindate + period     
    if filebegin > enddate: raise DateError    
    if enddate > fileend: 
      logger.info('\n{0:s}   ---   Invalid Period: End Date {1:4d} not in File!   ---   \n'.format(pidstr,enddate))
      
    else:  
      ## begin actual computation
      periodstr = '{0:4d}-{1:4d}'.format(begindate,enddate)
      expfolder = avgfolder + experiment + '/'
      logger.info('\n{0:s}   <<<   Computing Climatology from {1:s} on {2:s} grid  >>>   \n'.format(pidstr,periodstr,grid))              

      # determine if sink file already exists, and what to do about it      
      gridstr = '' if griddef is None or griddef.name is 'WRF' else '_'+griddef.name
      filename = fileclass.climfile.format(domain,gridstr,'_'+periodstr)
      if ldebug: filename = 'test_' + filename
      assert os.path.exists(expfolder)
      filepath = expfolder+filename
      lskip = False # else just go ahead
      if os.path.exists(filepath): 
        if not loverwrite: 
          age = datetime.fromtimestamp(os.path.getmtime(filepath))
          # if sink file is newer than source file, skip (do not recompute)
          if age > sourceage: lskip = True
          #print sourceage, age
        if not lskip: os.remove(filepath) 
      
      # depending on last modification time of file or overwrite setting, start computation, or skip
      if lskip:        
        # print message
        logger.info('{0:s}   >>>   Skipping: File \'{1:s}\' already exists and is newer than source file.   <<<   \n'.format(pidstr,filename))              
      else:
         
        # prepare sink
        sink = DatasetNetCDF(name='WRF Climatology', folder=expfolder, filelist=[filename], atts=source.atts, mode='w')
        sink.atts.period = periodstr 
        
        # initialize processing
        CPU = CentralProcessingUnit(source, sink, varlist=None, tmp=True) # no need for lat/lon
        #CPU = CentralProcessingUnit(source, sink, varlist=varlist, tmp=True) # no need for lat/lon
        
        # start processing climatology
        CPU.Climatology(period=period, offset=offset, flush=False)
        
        # reproject and resample (regrid) dataset
        if griddef is not None:
          CPU.Regrid(griddef=griddef, flush=False)
          logger.info('%s    ---   '+str(griddef.geotansform)+'   ---   \n'%(pidstr))      
        
        # sync temporary storage with output dataset (sink)
        CPU.sync(flush=True)
        
        # make new masks
        #sink.mask(sink.landmask, maskSelf=False, varlist=['snow','snowh','zs'], invert=True, merge=False)
        
        # add names and length of months
        sink.axisAnnotation('name_of_month', name_of_month, 'time', 
                            atts=dict(name='name_of_month', units='', long_name='Name of the Month'))
        sink += VarNC(sink.dataset, name='length_of_month', units='days', axes=(sink.time,), data=days_per_month,
                      atts=dict(name='length_of_month',units='days',long_name='Length of Month'))
        
        # close... and write results to file
        logger.info('\n{0:s} Writing to: \'{1:s}\'\n'.format(pidstr,filename))
        sink.sync()
        sink.close()
        # print dataset
        if not lparallel:
          logger.info('\n'+str(sink)+'\n')   


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
  # re-compute everything or just update 
  if os.environ.has_key('PYAVG_OVERWRITE'): 
    loverwrite =  os.environ['PYAVG_OVERWRITE'] == 'OVERWRITE' 
  else: loverwrite = ldebug # False means only update old files
  
  # default settings
  if ldebug:
    #ldebug = False
    NP = NP or 2
    #loverwrite = True
    varlist = None # ['precip', ]
    experiments = ['max']
    #experiments = ['max','gulf','new','noah'] 
    periods = [1,]
    domains = [1,2] # domains to be processed
    filetypes = ['lsm',] # filetypes to be processed
    grid = 'WRF' 
  else:
    NP = NP or 4
    #loverwrite = False
    varlist = None
    experiments = [] # WRF experiment names (passed through WRFname)
    periods = [5,10] # averaging period
    domains = [1,2] # domains to be processed
    filetypes = ['srfc','xtrm','plev3d','hydro','lsm','rad'] # filetypes to be processed
    grid = 'WRF' 

  # expand experiments 
  if len(experiments) > 0: experiments = [WRFname[exp] for exp in experiments]
  else: experiments = [exp for exp in WRFname.values()]    

  ## do some fancy regridding
  # determine coordinate arrays
  if grid != 'WRF':
    griddef = getCommonGrid(grid)
  else:
    griddef = None
  
  # print an announcement
  print('\n Computing Climatologies for WRF experiments:\n')
  print(experiments)
  if grid != 'WRF': print('\nRegridding to \'{0:s}\' grid.\n'.format(grid))
  print('\nOVERWRITE: {0:s}\n'.format(str(loverwrite)))
      
  # assemble argument list and do regridding
  args = [] # list of arguments for workers, i.e. "work packages"
  # generate list of parameters
  for experiment in experiments:    
    # loop over file types
    for filetype in filetypes:                
      # effectively, loop over domains
      for domain in domains:
        # arguments for worker function
        args.append( (experiment, filetype, domain) )        
  # static keyword arguments
  kwargs = dict(periods=periods, offset=0, griddef=None, loverwrite=loverwrite)        
  # call parallel execution function
  asyncPoolEC(computeClimatology, args, kwargs, NP=NP, ldebug=ldebug, ltrialnerror=True)