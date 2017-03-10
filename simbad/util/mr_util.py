"""Class to run MR on SIMBAD results using code from MrBump"""

__author__ = "Adam Simpkin"
__date__ = "09 Mar 2017"
__version__ = "0.1"

import os
import sys
import logging
import tempfile
import types
import copy_reg
from contextlib import contextmanager
import multiprocessing

from simbad.util import simbad_util
from simbad.util import mtz_util

# Set up MrBUMP imports
if os.path.isdir(os.path.join(os.environ["CCP4"], "share", "mrbump")):
    mrbump = os.path.join(os.environ["CCP4"], "share", "mrbump")
mrbump_incl = os.path.join(mrbump, "include")

sys.path.append(os.path.join(mrbump_incl, 'dev'))
sys.path.append(os.path.join(mrbump_incl, 'file_info'))
sys.path.append(os.path.join(mrbump_incl, 'modelling'))
sys.path.append(os.path.join(mrbump_incl, 'mr'))
sys.path.append(os.path.join(mrbump_incl, 'output'))
sys.path.append(os.path.join(mrbump_incl, 'seq_align'))
sys.path.append(os.path.join(mrbump_incl, 'ccp4'))
sys.path.append(os.path.join(mrbump_incl, 'structures'))
sys.path.append(os.path.join(mrbump_incl, 'tools'))
sys.path.append(os.path.join(mrbump_incl, 'initialisation'))
sys.path.append(os.path.join(mrbump_incl, 'building'))
sys.path.append(os.path.join(mrbump_incl, 'cluster'))
sys.path.append(os.path.join(mrbump_incl, 'dispatchers'))
sys.path.append(os.path.join(mrbump_incl, 'parsers'))
sys.path.append(os.path.join(mrbump_incl, 'phasing'))

import cluster_run

_logger = logging.getLogger(__name__)


def _pickle_method(m):
    if m.im_self is None:
        return getattr, (m.im_class, m.im_func.func_name)
    else:
        return getattr, (m.im_self, m.im_func.func_name)


copy_reg.pickle(types.MethodType, _pickle_method)


class MrSubmit(object):
    """Class to run MR on a defined set of models

    Attributes
    ----------
    mtz : str
        Path to the input MTZ file
    mr_program : str
        Name of the molecular replacement program to use
    refine_program : str
        Name of the refinement program to use
    model_dir : str
        Path to the directory containing input models
    output_dir : str
        Path to the directory to output results
    early_term : bool
        Terminate early if a solution is found [default: True]
    enam : bool
        Test enantimorphic space groups [default: False]
    results : class
        Results from :obj: '_LatticeParameterScore' or :obj: '_AmoreRotationScore'
    time_out : int, optional
        Number of seconds for multiprocessing job to timeout [default: 60]
    nproc : int, optional
        Number of processors to use [default: 2]

    Examples
    --------
    >>> from simbad.util.mr_util import MrSubmit
    >>> MR = MrSubmit('<mtz>', '<mr_program>', '<refine_program>', '<model_dir>', '<output_dir>', '<early_term>',
    >>>               '<enam>')
    >>> MR.multiprocessing('<results>', '<time_out>', '<nproc>')

    If a solution is found and early_term is set to True, the queued jobs will be terminated.
    """

    def __init__(self, mtz, mr_program, refine_program, model_dir, output_dir, early_term=True, enam=False):
        """Initialise MrSubmit class"""
        self.input_file = None
        self._early_term = None
        self._enam = None
        self._model_dir = None
        self._mtz = None
        self._mr_program = None
        self._output_dir = None
        self._refine_program = None

        # options derived from the input mtz
        self._cell_parameters = None
        self._resolution = None
        self._solvent = None
        self._space_group = None
        self._f = None
        self._sigf = None
        self._free = None

        self.early_term = early_term
        self.enam = enam
        self.model_dir = model_dir
        self.mtz = mtz
        self.mr_program = mr_program
        self.output_dir = output_dir
        self.refine_program = refine_program

    @property
    def early_term(self):
        """Flag to decide if the program should terminate early"""
        return self._early_term

    @early_term.setter
    def early_term(self, early_term):
        """Set the early term flag to true or false"""
        self._early_term = early_term

    @property
    def enam(self):
        """Flag to decide if enantiomorphic spacegroups should be trialled"""
        return self._enam

    @enam.setter
    def enam(self, enam):
        """Set the enam flag to true or false"""
        self._enam = enam

    @property
    def model_dir(self):
        """The directory containing the input models"""
        return self._model_dir

    @model_dir.setter
    def model_dir(self, model_dir):
        """Define the path to the directory containing the input models"""
        self._model_dir = model_dir

    @property
    def mtz(self):
        """The input MTZ file"""
        return self._mtz

    @mtz.setter
    def mtz(self, mtz):
        """Define the input MTZ file"""
        self._mtz = mtz
        self.get_mtz_info(mtz)

    @property
    def cell_parameters(self):
        """The cell parameters of the input MTZ file"""
        return self._cell_parameters

    @property
    def resolution(self):
        """The resolution of the input MTZ file"""
        return self._resolution

    @property
    def solvent(self):
        """The predicted solvent content of the input MTZ file"""
        return self._solvent

    @property
    def space_group(self):
        """The space group of the input MTZ file"""
        return self._space_group

    @property
    def f(self):
        """The F column label of the input MTZ file"""
        return self._f

    @property
    def sigf(self):
        """The SIGF column label of the input MTZ file"""
        return self._sigf

    @property
    def free(self):
        """The FREE column label of the input MTZ file"""
        return self._free

    @property
    def mr_program(self):
        """The molecular replacement program to use"""
        return self._mr_program

    @mr_program.setter
    def mr_program(self, mr_program):
        """Define the molecular replacement program to use"""
        self._mr_program = mr_program

    @property
    def refine_program(self):
        """The refinement program to use"""
        return self._refine_program

    @refine_program.setter
    def refine_program(self, refine_program):
        """Define the refinement program to use"""
        self._refine_program = refine_program

    @property
    def output_dir(self):
        """The path to the output directory"""
        return self._output_dir

    @output_dir.setter
    def output_dir(self, output_dir):
        """Define the output directory"""
        self._output_dir = output_dir

    @contextmanager
    def suppress_stdout(self):
        """Code to suppress the stdout of a function, used here to silence stdout of MrBUMP modules"""
        with open(os.devnull, "w") as devnull:
            old_stdout = sys.stdout
            sys.stdout = devnull
            try:
                yield
            finally:
                sys.stdout = old_stdout

    def _run_job(self, model):
        """Function to run MR on each model"""
        _logger.info("Running MR and refinement on {0}".format(model.pdb_code))

        # Generate MR input file
        self.MR_setup(model)

        # Run job
        cljob = cluster_run.ClusterJob()

        if self.input_file:
            # Parse input file
            cljob.parse_input(self.input_file)

        # Create temp files for the mr and refine keyfiles
        mr_key = tempfile.NamedTemporaryFile(delete=False)
        ref_key = tempfile.NamedTemporaryFile(delete=False)

        if self.mr_program and self.refine_program:
            with self.suppress_stdout():
                cljob.run(self.mr_program, self.refine_program, mr_key.name, refine_keyfile=ref_key.name)

        # Remove temp files
        os.unlink(mr_key.name)
        os.unlink(ref_key.name)

        if self.early_term:
            terminate = self.solution_found(model)
            return terminate

        return False

    def get_mtz_info(self, mtz):
        """Get various information from the input MTZ

         Parameters
         ----------
         mtz : str
            Path to the input MTZ

        Returns
        -------
        self._cell_parameters : list
            The parameters that descibe the unit cell
        self._resolution : float
            The resolution of the data
        self._space_group : str
            The space group of the data
        self._f : str
            The column label for F
        self._sigf : str
            The column label for SIGF
        self._free : str
            The column label for FREE
        self._solvent : float
            The predicted solvent content of the protein
        """
        # Extract crystal data from input mtz
        self._cell_parameters, self._resolution, self._space_group = mtz_util.crystal_data(mtz)

        # Extract column labels from input mtz
        self._f, self._sigf, _, _, self._free = mtz_util.get_labels(mtz)

        # Get solvent content
        self._solvent = self.matthews_coef(self._cell_parameters, self._space_group)
        return

    def MR_setup(self, model):
        """Code to generate directories for MR and refinement for a model
        and generate an input file containing information about the MR/refine run

        Parameters
        ----------
        model : class
            Class object containing the PDB code for the input model
        self.output_dir : str
            Output directory input to :obj: MrSubmit
        self.model_dir : str
            Model directory input to :obj: MrSubmit
        self.mr_program : str
            molecular replacement program input to :obj: MrSubmit
        self.space_group : str
            space group input to :obj: MrSubmit
        self.mtz : str
            MTZ file input to :obj: MrSubmit
        self.enam : bool
            Enantimorphic space groups flag input to :obj: MrSubmit
        self.f : str
            F flag input to :obj: MrSubmit
        self.sigf : str
            SIGF flag input to :obj: MrSubmit
        self.free : str
            FREE flag input to :obj: MrSubmit
        self.solvent : float
            Predicted solvent content input to :obj: MrSubmit
        self.resolution : float
            Resolution input to :obj: MrSubmit

        Returns
        -------
        file
            Output directory for molecular replacement
        file
            Output directory for refinement
        file
            Input file used by MrBUMP MR module
        """

        if not os.path.isdir(self.output_dir):
            os.mkdir(self.output_dir)

        # Create individual directories for every results
        if self.mr_program.upper() == "MOLREP":
            os.mkdir(os.path.join(self.output_dir, model.pdb_code))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr'))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr', 'molrep'))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr', 'molrep', 'refine'))
        elif self.mr_program.upper() == "PHASER":
            os.mkdir(os.path.join(self.output_dir, model.pdb_code))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr'))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr', 'phaser'))
            os.mkdir(os.path.join(self.output_dir, model.pdb_code, 'mr', 'phaser', 'refine'))

        # create input file path
        input_file = os.path.join(self.output_dir, model.pdb_code, 'input.txt')
        dire = os.path.join(self.output_dir, model.pdb_code)
        pdbi = os.path.join(self.model_dir, '{0}.pdb'.format(model.pdb_code))

        # Assign variables
        hklr = os.path.join(dire, 'mr', self.mr_program, '{0}_refinement_input.mtz'.format(model.pdb_code))
        hklo = os.path.join(dire, 'mr', self.mr_program, '{0}_phaser_output.mtz'.format(model.pdb_code))
        pdbo = os.path.join(dire, 'mr', self.mr_program, '{0}_mr_output.pdb'.format(model.pdb_code))
        mrlo = os.path.join(dire, 'mr', self.mr_program, '{0}_mr.log'.format(model.pdb_code))
        refh = os.path.join(dire, 'mr', self.mr_program, 'refine', '{0}_refinement_output.mtz'.format(model.pdb_code))
        refp = os.path.join(dire, 'mr', self.mr_program, 'refine', '{0}_refinement_output.pdb'.format(model.pdb_code))
        refl = os.path.join(dire, 'mr', self.mr_program, 'refine', '{0}_ref.log'.format(model.pdb_code))

        # Write input file
        with open(input_file, 'w') as f:
            f.write("DIRE {0}\n".format(os.path.abspath(dire)))
            f.write("SGIN {0}\n".format(self.space_group))
            f.write("HKL1 {0}\n".format(os.path.abspath(self.mtz)))
            f.write("HKLR {0}\n".format(hklr))
            f.write("PDBO {0}\n".format(pdbo))
            f.write("MRLO {0}\n".format(mrlo))
            f.write("REFH {0}\n".format(refh))
            f.write("REFP {0}\n".format(refp))
            f.write("REFL {0}\n".format(refl))
            f.write("ENAN {0}\n".format(self.enam))
            f.write("FPIN {0}\n".format(self.f))
            f.write("SIGF {0}\n".format(self.sigf))
            f.write("FREE {0}\n".format(self.free))
            f.write("SOLV {0}\n".format(self.solvent))
            f.write("RESO {0}\n".format(self.resolution))
            f.write("PDBI {0}\n".format(os.path.abspath(pdbi)))
            if self.mr_program == "phaser":
                f.write("HKLO {0}\n".format(hklo))

        self.input_file = input_file

        return

    def multiprocessing(self, results, time_out=60, nproc=2):
        """Code to run MR and refinement in parallel

        Parameters
        ----------
        results : class
            Results from :obj: '_LatticeParameterScore' or :obj: '_AmoreRotationScore'
        time_out: int
            Number of seconds for multiprocessing job to timeout [default: 60]
        nproc : int
            Number of processors to use [default: 2]

        Returns
        -------
        file
            PDB from the molecular replacement job
        file
            Log file from the molecular replacement job
        file
            PDB from the refinement job
        file
            MTZ from the refinement job
        file
            Log file from the refinement job
        """

        def run(job_queue):
            """processes element of job queue if queue not empty"""
            while not job_queue.empty():
                model = job_queue.get(timeout=time_out)
                terminate = self._run_job(model)

                if terminate:
                    print "MR with {0} was successful so removing remaining jobs from inqueue".format(model.pdb_code)
                    while not job_queue.empty():
                        job = job_queue.get()
                        _logger.debug("Removed job [{0}] from inqueue".format(job.pdb_code))

        # Create job queue
        job_queue = multiprocessing.Queue()

        # Add each result from results to the job queue
        for result in results:
            job_queue.put(result)

        processes = []
        # Set up processes equal to the number of processors input
        for i in range(nproc):
            process = multiprocessing.Process(target=run, args=(job_queue,))
            process.start()
            processes.append(process)

        # block the calling thread
        for p in processes:
            p.join()

    def solution_found(self, model):
        """Function to check is a solution has been found

        Parameters
        ----------
        result_dir : str
            Path to the results directory
        model : class
            Class object containing the PDB code for the input model

        Returns
        -------
        bool
            Solution found <True|False>
        """
        # Set default values if no results found
        final_r_fact = 1
        final_r_free = 1

        with open(os.path.join(self.output_dir, model.pdb_code, 'mr', 'molrep',
                               'refine', '{0}_ref.log'.format(model.pdb_code)), 'r') as f:
            for line in f:
                if line.startswith('           R factor'):
                    final_r_fact = float(line.split()[2])
                elif line.startswith('             R free'):
                    final_r_free = float(line.split()[2])

        if final_r_fact < 0.45 and final_r_free < 0.45:
            return True
        else:
            return False

    def matthews_coef(self, cell_parameters, space_group):
        """Function to run matthews coefficient to decide if the model can fit in the unit cell

        Parameters
        ----------
        cell_parameters
            The parameters of the unit cell
        space_group
            The space group of the crystal

        Returns
        -------
        float
            solvent content of the protein

        """

        cmd = ["matthews_coef"]
        key = """CELL {0}
symm {1}
auto""".format(cell_parameters,
               space_group)
        command_line = os.linesep.join(map(str, cmd))

        logfile = 'matt_coef.log'
        simbad_util.run_job(command_line, logfile, key)

        # Determine if the model can fit in the unit cell
        solvent_content = 0.5
        with open(logfile, 'r') as f:
            for line in f:
                if line.startswith('  1'):
                    solvent_content = (float(line.split()[2]) / 100)

        # Clean up
        os.remove(logfile)

        return solvent_content
