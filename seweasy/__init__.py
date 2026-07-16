"""
    A Python library for building parametric sewing pattern programs
"""

# Building blocks
from seweasy.garmentcode.component import Component
from seweasy.garmentcode.panel import Panel
from seweasy.garmentcode.edge import Edge, CircleEdge, CurveEdge, EdgeSequence
from seweasy.garmentcode.connector import Stitches
from seweasy.garmentcode.interface import Interface
from seweasy.garmentcode.edge_factory import EdgeSeqFactory
from seweasy.garmentcode.edge_factory import CircleEdgeFactory
from seweasy.garmentcode.edge_factory import EdgeFactory
from seweasy.garmentcode.edge_factory import CurveEdgeFactory


# Operations
import seweasy.garmentcode.operators as ops
import seweasy.garmentcode.utils as utils

# Parameter support
from seweasy.garmentcode.params import BodyParametrizationBase, DesignSampler

# Errors
from seweasy.pattern.core import EmptyPatternError

