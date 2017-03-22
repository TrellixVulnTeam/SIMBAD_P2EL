"""Class to run an anomalous phased fourier on MR results"""

import os
import simbad_util
import mtz_util

__author__ = "Adam Simpkin"
__date__ = "17 Mar 2017"
__version__ = "0.1"

class AnomSearch():
    """An anomalous phased fourier running class"""

    def __init__(self, mtz, output_dir):
        self._mtz = None
        self._f = None
        self._sigf = None
        self._dano = None
        self._sigdano = None
        self._free = None
        self._space_group = None
        self._resolution = None
        self._cell_parameters = None
        self._output_dir = None

        self.name = None
        self.mtz = mtz
        self.output_dir = output_dir
        self.work_dir = None

    @property
    def mtz(self):
        """The input MTZ file"""
        return self._mtz

    @mtz.setter
    def mtz(self, mtz):
        """Define the input MTZ file"""
        self._mtz = mtz

    @property
    def output_dir(self):
        """The path to the working directory"""
        return self._output_dir

    @output_dir.setter
    def output_dir(self, output_dir):
        """Define the working directory"""
        self._output_dir = output_dir

    @staticmethod
    def cleanup(logfile):
        """Simple function to clean up log files after a run"""
        os.remove(logfile)

    def run(self, model):
        """Function to run SFALL/CAD/FFT to create phased anomalous fourier map"""

        # Make output directory
        self.work_dir = os.path.join(self.output_dir, model.pdb_code, "anomalous")
        os.mkdir(self.work_dir)

        self._f, self._sigf, self._dano, self._sigdano, self._free = mtz_util.get_labels(self.mtz)
        self._space_group, self._resolution, self._cell_parameters = mtz_util.crystal_data(self.mtz)

        # Create path to the placed mr solution
        input_model = os.path.join(self.output_dir, model.pdb_code, "mr", "molrep", "{0}_mr_output.1.pdb".format(
            model.pdb_code))
        self.name = model.pdb_code

        # Run programs
        self.sfall(input_model)
        self.cad()
        self.fft()
        self.peakmax()
        return

    def sfall(self, model):
        """Function to run SFALL to calculated structure factors for the placed MR model

        Parameters
        ----------
        model : str
            path to placed model from MR
        self.name : str
            unique identifier for the input model set by :obj:`AnomSearch.run`
        self.mtz : str
            mtz file input to :obj:`AnomSearch`
        self.work_dir : str
            working directory set by :obj:`AnomSearch.run`
        self._f : str
            f column label set by :obj: `AnomSearch`
        self._sigf : str
            sigf column label set by :obj: `AnomSearch`
        self._free : str
            free column label set by :obj: `AnomSearch`

        Returns
        -------
        file
            mtz file containing FCalc and PHICalc columns
        """

        cmd = ["sfall",
               "HKLOUT", os.path.join(self.work_dir, "sfall_{0}.mtz".format(self.name)),
               "XYZIN", model,
               "HKLIN", self.mtz]
        command_line = os.linesep.join(map(str, cmd))

        key = """LABIN  FP={0} SIGFP={1} FREE={2}
labout -
   FC=FCalc PHIC=PHICalc
MODE SFCALC -
    XYZIN -
    HKLIN
symmetry '{3}'
badd 0.0
vdwr 2.5
end""".format(self._f, self._sigf, self._free, self._space_group)

        logfile = os.path.join(self.work_dir, 'sfall_{0}.log'.format(self.name))
        simbad_util.run_job(command_line, logfile, key)

        self.cleanup(logfile)

    def cad(self):
        """Function to run CAD to combine the calculated structure factors and the anomalous signal

        Parameters
        ----------
        self.name : str
            unique identifier for the input model set by :obj:`AnomSearch.run`
        self.mtz : str
            mtz file input to :obj: `AnomSearch`
        self.work_dir : str
            working directory set by :obj:`AnomSearch.run`
        self._f : str
            f column label set by :obj: `AnomSearch`
        self._sigf : str
            sigf column label set by :obj: `AnomSearch`
        self._free : str
            free column label set by :obj: `AnomSearch`
        self._dano : str
            dano column label set by :obj: `AnomSearch`
        self._sigdano : str
            sigdano column label set by :obj: `AnomSearch`
        self._resolution : float
            mtz resolution set by :obj: `AnomSearch`

        Returns
        -------
        file
            mtz file containing FCalc, PHICalc, DANO and SIGDANO columns
        """

        cmd = ["cad",
               "HKLIN1", self.mtz,
               "HKLIN2", os.path.join(self.work_dir, "sfall_{0}.mtz".format(self.name)),
               "HKLOUT", os.path.join(self.work_dir, "cad_{0}.mtz".format(self.name))]
        command_line = os.linesep.join(map(str, cmd))

        key = """monitor BRIEF
labin file 1 -
    E1 = {0} -
    E2 = {1} -
    E3 = {2} -
    E4 = {3} -
    E5 = {4}
labout file 1 -
    E1 = {0} -
    E2 = {1} -
    E3 = {2} -
    E4 = {3} -
    E5 = {4}
ctypin file 1 -
    E1 = F -
    E2 = Q -
    E3 = I -
    E4 = D -
    E5 = Q
resolution file 1 50 {5}
labin file 2 -
    E1 = FCalc -
    E2 = PHICalc
labout file 2 -
    E1 = FCalc -
    E2 = PHICalc
ctypin file 2 -
    E1 = F -
    E2 = P""".format(self._f, self._sigf, self._free, self._dano, self._sigdano, self._resolution)

        logfile = os.path.join(self.work_dir, 'cad_{0}.log'.format(self.name))
        simbad_util.run_job(command_line, logfile, key)

        self.cleanup(logfile)

    def fft(self):
        """Function to run FFT to create phased anomalous fourier map

        Parameters
        ----------
        self.name : str
            unique identifier for the input model set by :obj:`AnomSearch.run`
        self.work_dir : str
            working directory set by :obj:`AnomSearch.run`

        Returns
        -------
        file
            anomalous phased fourier map file
        file
            log file containing the peaks identified by the anomalous phased fourier
        """

        cmd = ["fft",
               "HKLIN", os.path.join(self.work_dir, "cad_{0}.mtz".format(self.name)),
               "MAPOUT", os.path.join(self.work_dir, "fft_{0}.map".format(self.name))]
        command_line = os.linesep.join(map(str, cmd))

        key = """xyzlim asu
scale F1 1.0
labin -
   DANO=DANO SIG1=SIGDANO PHI=PHICalc
end"""
        logfile = os.path.join(self.work_dir, 'fft_{0}.log'.format(self.name))
        simbad_util.run_job(command_line, logfile, key)

    def peakmax(self):
        """Function to run peakmax to return the peaks from FFT"""

        cmd = ["peakmax",
               "MAPIN", os.path.join(self.work_dir, "fft_{0}.map".format(self.name)),
               "XYZOUT", os.path.join(self.work_dir, "peakmax_{0}.pdb".format(self.name)),
               "XYZFRC", os.path.join(self.work_dir, "peakmax_{0}.ha".format(self.name))]
        command_line = os.linesep.join(map(str, cmd))

        key = """threshhold -
    rms -
    3.0
numpeaks 50
output brookhaven frac
residue WAT
atname OW
chain X"""

        logfile = os.path.join(self.work_dir, 'peakmax_{0}.log'.format(self.name))
        simbad_util.run_job(command_line, logfile, key)







