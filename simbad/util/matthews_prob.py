"""Module for running matthews probabilities to calculate solvent content"""

__author__ = "Adam Simpkin"
__date__ = "3 June 2020"
__version__ = "1.0"

import abc
import math
import numpy as np

import simbad.util
from simbad.util.pdb_util import PdbStructure

ABC = abc.ABCMeta('ABC', (object,), {})


class _MatthewsCoefficient(ABC):
    """Abstract class for Matthews Coefficient calculation"""

    def __init__(self, cell_volume):
        self.cell_volume = cell_volume

    @abc.abstractmethod
    def calculate_from_file(self, pdb):
        pass

    @abc.abstractmethod
    def calculate_from_struct(self, struct):
        pass

    def get_macromolecule_fraction(self, vm):
        """Calculate the macromolecule fraction"""
        return 1. / (6.02214e23 * 1e-24 * 1.35 * vm)


class SolventContent(_MatthewsCoefficient):
    def __init__(self, cell_volume):
        super(SolventContent, self).__init__(cell_volume)

    def calculate_from_file(self, pdb):
        struct = PdbStructure.from_file(pdb)
        return self.calculate_from_struct(struct)

    def calculate_from_struct(self, struct):
        return self._calculate(struct.molecular_weight)

    def _calculate(self, mw):
        if mw <= 0:
            raise ValueError("Incorrect Molecular Weight")
        vm = self.cell_volume / mw
        macromolecule_fraction = self.get_macromolecule_fraction(vm)
        solvent_fraction = 1.0 - macromolecule_fraction
        return solvent_fraction * 100


class MatthewsProbability(_MatthewsCoefficient):
    def __init__(self, cell_volume):
        super(MatthewsProbability, self).__init__(cell_volume)

    def calculate_from_file(self, pdb):
        struct = PdbStructure.from_file(pdb)
        return self.calculate_from_struct(struct)

    def calculate_from_struct(self, struct):
        return self._calculate(struct.molecular_weight)

    def _calculate(self, mw):
        from simbad.util.ext.c_matthews_prob import c_calculate_solvent_probability, c_get_max_score
        n_copies = 0
        solvent_fraction = 1.0
        scores = []
        while solvent_fraction > 0:
            n_copies += 1
            vm = self.cell_volume / (mw * n_copies)
            macromolecule_fraction = self.get_macromolecule_fraction(vm)
            if macromolecule_fraction > 1:
                break
            solvent_fraction = 1.0 - macromolecule_fraction
            probability = c_calculate_solvent_probability(solvent_fraction)
            scores.append((n_copies, solvent_fraction, probability))
        return c_get_max_score(scores)



