'''
Created on Feb 28, 2013

@author: jmht
'''

import multiprocessing
import os
import sys

from simbad.util import simbad_util

def worker(inqueue, early_terminate=False, check_success=None, chdir=False):
    """
    Worker process to run MrBump jobs until no more left.

    Args:
    inqueue -- a python Queue object
    early_terminate -- bool - terminate on first success or continue running

    Returns:
    0 if molecular replacement worked
    1 if nothing found

    We keep looping, removing jobs from the inqueue until there are no more left.

    REM: This needs to import the main module that it lives in so maybe this should
    live in a separate module?
    """

    if early_terminate: assert callable(check_success)

    success=True
    while True:
        if inqueue.empty():
            if success: sys.exit(0)
            else: sys.exit(1)

        # Got a script so run
        job = inqueue.get()

        # Get name from script
        directory, sname = os.path.split(job)
        jobname = os.path.splitext(sname)[0]
        
        # Change directory to the script directory
        if chdir: os.chdir(directory)
        retcode = simbad_util.run_job([job], logfile=job.rsplit('.', 1)[0] + '.log')

        # Can we use the retcode to check?
        # REM - is retcode object
        if retcode != 0:
            print "WARNING! Worker {0} got retcode {1}: {2}".format(multiprocessing.current_process().name, retcode, jobname)
            success=False

        # Now check the result if early terminate
        if early_terminate:
            if check_success( job ):
                #return 0
                sys.exit(0)

    print "worker {0} FAILED!".format(multiprocessing.current_process().name)
    #return 1
    sys.exit(1)
##End worker

# No tests here as the main module needs to be importable
