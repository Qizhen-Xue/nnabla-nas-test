from collections import defaultdict

from tensorboard.compat.proto.config_pb2 import RunMetadata
from tensorboard.compat.proto.graph_pb2 import GraphDef
from tensorboard.compat.proto.step_stats_pb2 import StepStats, DeviceStepStats
from tensorboard.compat.proto.versions_pb2 import VersionDef
from tensorboard.compat.proto.node_def_pb2 import NodeDef
from tensorboard.compat.proto.types_pb2 import DT_FLOAT
from tensorboard.compat.proto.tensor_shape_pb2 import TensorShapeProto
from tensorboard.compat.proto.attr_value_pb2 import AttrValue
from tensorboard.compat.proto import event_pb2

from .writer import FileWriter
from .proto_graph import node_proto, tensor_shape_proto
from collections import OrderedDict
import numpy as np
import nnabla as nn

EXCLUDED_NODES = ['CONSTANT']


def _get_unique_params(params):
    r"""Returns a dictionary with unique parameters."""
    mark = set()
    unique_params = OrderedDict()
    for k, p in params.items():
        h = hash(p)
        if h not in mark:
            mark.add(h)
            unique_params[k] = p
    return unique_params


class GraphVisitor(object):
    r"""A visitor for nnabla graph.

    Args:
        model (Module): A nnabla module.

    Note: all arguments in `args` should be nnabla variables, which will be used during the `call` method.
    """

    def __init__(self, model, *args, **kargs):
        # this will store the tensorboard name for each parameter.
        self._tb_name = dict()
        # wether the node was already constructed
        self._visited = set()
        # the current graph
        self._graph = []
        # counter for the node having same name
        self._counter = defaultdict(int)

        # build the nnabla graph
        outputs = model(*args, **kargs)

        # get parameters
        params = model.get_parameters(grad_only=False)
        params = _get_unique_params(params)

        # define the scope for all known parameters
        prefix = type(model).__name__ + '/'
        self._scope = defaultdict(str, {hash(p): (prefix + k) for k, p in params.items()})

        for ni in args:
            self._scope[hash(ni)] = 'Input'

        if not isinstance(outputs, (tuple, list)):
            outputs = [outputs]

        # add connections to outputs
        for no in outputs:
            if isinstance(no, nn.Variable):
                self._scope[hash(no)] = 'Output'
                no.visit(self)

    def add_node(self, node):
        r"""Adds a new node to the graph."""
        self._graph.append(node)

    def create_node(self, p):
        r"""Create a node given its parameter."""
        name = self.get_node_name(p)
        if (name not in self._visited) and (name not in EXCLUDED_NODES):
            # add a new node to the graph
            self.add_node(
                node_proto(
                    name=name, op='Variable',
                    output_shapes=[p.shape],
                    attributes=f'shape={p.shape}'
                )
            )

    def get_scope_from(self, scopes):
        r"""Return the scope from list of scopes."""
        idx = np.argmax([len(s.split('/')) for s in scopes])
        scope = '/'.join(scopes[idx].split('/')[:-1])
        return scope

    def get_node_name(self, p):
        r"""Return the node name according to tensorboard."""
        h = hash(p)

        if h not in self._scope:
            return 'CONSTANT'

        scope = self._scope[h]
        if h not in self._tb_name:
            self._tb_name[h] = scope
            if self._counter[scope]:
                self._tb_name[h] += f'_{self._counter[scope]}'
            self._counter[scope] += 1
        return self._tb_name[h]

    def __call__(self, f):
        inputs = []
        for ni in f.inputs:
            self.create_node(ni)
            node_name = self.get_node_name(ni)
            if node_name not in EXCLUDED_NODES:
                inputs.append(node_name)

        # get function node
        self._scope[hash(f)] = self.get_scope_from(inputs)
        self._scope[hash(f)] += ('/' if self._scope[hash(f)] else '') + str(f)
        name = self.get_node_name(f)

        # make sure all outputs refer to the same function node
        outputsize = []
        for no in f.outputs:
            ho = hash(no)
            if self._scope[ho] == 'Output':
                self.add_node(
                    node_proto(
                        name=self.get_node_name(no), op='Output',
                        inputs=[name],
                        attributes=f'shape={no.shape}'
                    )
                )
            self._scope[ho] = self._scope[hash(f)]
            self._tb_name[ho] = name
            outputsize.append(no.shape)

        # add the function node
        self.add_node(
            node_proto(
                name=name,
                op=str(f),
                inputs=inputs if len(inputs) > 0 else None,
                output_shapes=outputsize
            )
        )
