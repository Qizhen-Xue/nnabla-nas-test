import numpy as np
from copy import deepcopy
import networkx as nx
import matplotlib.pyplot as plt
from nnabla_nas.module import static as smo
import nnabla_nas.module as mo
from nnabla_nas.contrib.model import Model
import nnabla as nn

class RandomModule(smo.Graph):
    def __init__(self, parents, channels, name=''):
        smo.Graph.__init__(self,
                           parents=parents,
                           name=name)
        self._channels = channels
        shapes = [(list(ii.shape) + 4 * [1])[:4] for ii in self.parents]
        min_shape = np.min(np.array(shapes), axis=0)
        self._shape_adaptation = {i: np.array(si[2:]) / min_shape[2:]
                                  for i, si in enumerate(shapes)
                                  if tuple(si[2:]) != tuple(min_shape[2:])}
        projected_inputs = []

        # add an input convolution to project to the correct #channels
        for i, pi in enumerate(self.parents):
            self.append(smo.Conv(name='{}/input_conv_{}'.format(self.name, i),
                                 parents=[pi],
                                 in_channels=pi.shape[1],
                                 out_channels=self._channels,
                                 kernel=(1, 1)))
            self.append(smo.BatchNormalization(name='{}/input_conv_bn_{}'.format(
                                               self.name, i),
                                               parents=[self[-1]],
                                               n_dims=4,
                                               n_features=self._channels))
            self.append(smo.ReLU(name='{}/input_conv/relu_{}'.format(self.name, i),
                                 parents=[self[-1]]))

            projected_inputs.append(self[-1])

        for i, pii in enumerate(projected_inputs):
            if i in self._shape_adaptation:
                self.append(smo.MaxPool(name='{}/shape_adapt'
                                        '_pool_{}'.format(self.name, i),
                                         parents=[pii],
                                         kernel=self._shape_adaptation[i],
                                         stride=self._shape_adaptation[i]))
                projected_inputs[i] = self[-1]
        if len(projected_inputs) > 1:
            self.append(smo.Merging(parents=projected_inputs,
                                    name='{}/merging'.format(self.name),
                                    mode='add'))


class Conv(RandomModule):
    def __init__(self,
                parents,
                channels,
                kernel,
                pad,
                name=''):
        RandomModule.__init__(self,
                              parents=parents,
                              channels=channels,
                              name=name)
        self._channels = channels
        self._kernel = kernel
        self._pad = pad
        self.append(smo.Conv(name='{}/conv'.format(self.name),
                             parents=[self[-1]],
                             in_channels=self[-1].shape[1],
                             out_channels=self._channels,
                             kernel=self._kernel,
                             pad=self._pad))
        self.append(smo.BatchNormalization(name='{}/conv_bn'.format(
                                               self.name),
                                               parents=[self[-1]],
                                               n_dims=4,
                                               n_features=self._channels))
        self.append(smo.ReLU(name='{}/conv/relu'.format(self.name),
                                parents=[self[-1]]))


class SepConv(RandomModule):
    def __init__(self,
                parents,
                channels,
                kernel,
                pad,
                name=''):
        RandomModule.__init__(self,
                              parents=parents,
                              channels=channels,
                              name=name)
        self._channels = channels
        self._kernel = kernel
        self._pad = pad
        self.append(smo.Conv(name='{}/conv_dw'.format(self.name),
                             parents=[self[-1]],
                             in_channels=self[-1].shape[1],
                             out_channels=self[-1].shape[1],
                             kernel=self._kernel,
                             group=1,
                             pad=self._pad))
        self.append(smo.Conv(name='{}/conv_pw'.format(self.name),
                             parents=[self[-1]],
                             in_channels=self[-1].shape[1],
                             out_channels=self._channels,
                             kernel=(1, 1)))
        self.append(smo.BatchNormalization(name='{}/conv_bn'.format(
                                               self.name),
                                               parents=[self[-1]],
                                               n_dims=4,
                                               n_features=self._channels))
        self.append(smo.ReLU(name='{}/conv/relu'.format(self.name),
                                parents=[self[-1]]))


class Conv3x3(Conv):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        Conv.__init__(self,
                      parents=parents,
                      channels=channels,
                      name=name,
                      kernel=(3, 3),
                      pad=(1, 1))


class SepConv3x3(SepConv):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        SepConv.__init__(self,
                         parents=parents,
                         channels=channels,
                         name=name,
                         kernel=(3, 3),
                         pad=(1, 1))


class Conv5x5(Conv):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        Conv.__init__(self,
                      parents=parents,
                      channels=channels,
                      name=name,
                      kernel=(5, 5),
                      pad=(2, 2))


class SepConv5x5(SepConv):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        SepConv.__init__(self,
                         parents=parents,
                         channels=channels,
                         name=name,
                         kernel=(5, 5),
                         pad=(2, 2))


class MaxPool3x3(RandomModule):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        RandomModule.__init__(self,
                              parents=parents,
                              channels=channels,
                              name=name)
        self.append(smo.MaxPool(parents=[self[-1]],
                                kernel=(2, 2),
                                stride=(2, 2),
                                #pad=(1, 1),
                                name='{}/max_pool_3x3'.format(self.name)))


class AvgPool3x3(RandomModule):
    def __init__(self,
                 parents,
                 channels,
                 name=''):
        RandomModule.__init__(self,
                              parents=parents,
                              channels=channels,
                              name=name)
        self.append(smo.AvgPool(parents=[self[-1]],
                                kernel=(2, 2),
                                stride=(2, 2),
                                #pad=(1, 1),
                                name='{}/avg_pool_3x3'.format(self.name)))


RANDOM_CANDIDATES=[RandomModule,
                   SepConv3x3,
                   SepConv5x5,
                   RandomModule,
                   SepConv3x3,
                   SepConv5x5,
                   RandomModule,
                   SepConv3x3,
                   SepConv5x5,
                   MaxPool3x3,
                   AvgPool3x3]


class TrainNet(Model, smo.Graph):
    def __init__(self, n_vertices=20, input_shape=(3, 32, 32),
                 n_classes=10, candidates=RANDOM_CANDIDATES, min_channels=128,
                 max_channels=1024, k=4, p=0.75, name=''):
        smo.Graph.__init__(self,
                           parents=[],
                           name=name)
        self._input_shape = (1,) + input_shape
        self._n_vertices = n_vertices
        self._candidates = candidates
        self._n_classes = n_classes
        self._min_channels = min_channels
        self._max_channels = max_channels
        self._k = k
        self._p = p

        # 1. draw a random network graph
        g = self._get_random_graph(n_vertices,
                                   self._input_shape[1],
                                   output_channels=self._n_classes,
                                   candidates=self._candidates,
                                   min_channels=self._min_channels,
                                   max_channels=self._max_channels,
                                   k=self._k,
                                   p=self._p)

        self._init_modules_from_graph(g)

    def _init_modules_from_graph(self, graph):
        adj_matrix = nx.adjacency_matrix(graph).todense()
        sorted_nodes = np.argsort(graph.nodes)
        for i, ii in enumerate(sorted_nodes):
            p_idxs = np.where(np.ravel(adj_matrix[sorted_nodes,ii]) > 0)[0]
            if len(p_idxs) == 0:
                self.append(smo.Input(name='{}/input'.format(self.name),
                                      value=nn.Variable(self._input_shape)))
            else:
                rnd_class = self._candidates[np.random.randint(0, len(self._candidates), 1)[0]]
                rnd_channels = np.random.randint(self._min_channels,
                                                 self._max_channels,
                                                 1)[0]
                parents = [self[pi] for pi in p_idxs]

                self.append(rnd_class(name='{}/{}'.format(self.name, i),
                                      parents=parents,
                                      channels=rnd_channels))

        self.append(smo.GlobalAvgPool(
            name='{}/global_average_pool'.format(self.name),
            parents=[self[-1]]))
        self.append(smo.Collapse(name='{}/output_reshape'.format(self.name),
                                 parents=[self[-1]]))

    def _get_random_graph(self,
                          n_vertices,
                          input_channels,
                          output_channels,
                          candidates=[],
                          min_channels=32,
                          max_channels=512,
                          k=10,
                          p=0.5):

        graph = nx.watts_strogatz_graph(n_vertices, k=k, p=p)

        # 1. make the graph directed, such that it is not cyclic
        G = nx.DiGraph()
        G.name = graph.name
        G.add_nodes_from(graph)
        G.add_edges_from(((u, v, deepcopy(data))
                for u, nbrs in graph.adjacency()
                for v, data in nbrs.items()
                if v > u))
        G.graph = deepcopy(graph.graph)

        # 2. add a single input and output to the network
        adj_matrix = nx.adjacency_matrix(G).todense()
        inputs = np.where(np.ravel(np.sum(adj_matrix, axis=0) == 0))
        outputs = np.where(np.ravel(np.sum(adj_matrix, axis=1) == 0))
        G.add_node(-1) # input
        G.add_node(n_vertices) # output
        for i in inputs[0]:
            G.add_edge(-1, i)
        for o in outputs[0]:
            G.add_edge(o, n_vertices)
        return G

    @property
    def input_shapes(self):
        return [self[0].shape]

    def get_arch_modules(self):
        ans = []
        for name, module in self.get_modules():
            if isinstance(module, smo.Join):
                ans.append(module)
        return ans

    def get_net_modules(self, active_only=False):
        ans = []
        for name, module in self.get_modules():
            if isinstance(module,
                          smo.Module) and not isinstance(module, smo.Join):
                if active_only:
                    if module._value is not None:
                        ans.append(module)
                    else:
                        pass
                else:
                    ans.append(module)
        return ans

    def get_net_parameters(self, grad_only=False):
        param = OrderedDict()
        for key, val in self.get_parameters(grad_only).items():
            if 'join' not in key:
                param[key] = val
        return param

    def get_arch_parameters(self, grad_only=False):
        param = OrderedDict()
        for key, val in self.get_parameters(grad_only).items():
            if 'join' in key:
                param[key] = val
        return param

    def get_latency(self, estimator, active_only=True):
        latencies = {}
        for mi in self.get_net_modules(active_only=active_only):
            if type(mi) in self.modules_to_profile:
                latencies[mi.name] = estimator.predict(mi)
        return latencies

    def __call__(self, input):
        self.reset_value()
        self[0]._value = input
        return self._recursive_call()

    def summary(self):
        r"""Summary of the model."""
        str_summary = ''
        for mi in self.get_arch_modules():
            mi._sel_p.forward()
            str_summary += mi.name + "/"
            str_summary += mi.parents[np.argmax(mi._join_parameters.d)].name
            str_summary += "/" + str(np.max(mi._sel_p.d)) + "\n"

        str_summary += "Instantiated modules are:\n"
        for mi in self.get_net_modules(active_only=True):
            if isinstance(mi, smo.Module):
                try:
                    mi._eval_prob.forward()
                except Exception:
                    pass
                str_summary += mi.name + " chosen with probability "
                str_summary += str(mi._eval_prob.d) + "\n"
        return str_summary

    def save(self, output_path):
        gvg = self.get_gv_graph()
        gvg.render(output_path+'/graph')


if __name__ == '__main__':
    import nnabla as nn
    input_1 = smo.Input(name='input_1', value=nn.Variable((10, 16, 32, 32)))
    input_2 = smo.Input(name='input_2', value=nn.Variable((10, 32, 16, 16)))

    conv = Conv(name='test_conv',
                parents=[input_1, input_2],
                channels=64,
                kernel=(3, 3),
                pad=(1, 1))
    c3x3 = Conv3x3(name='test_c3x3',
                   parents=[input_1, input_2],
                   channels=64)
    c5x5 = Conv5x5(name='test_c5x5',
                   parents=[input_1, input_2],
                   channels=64)
    mp3x3 = MaxPool3x3(name='test_mp3x3',
                       parents=[input_1, input_2],
                       channels=64)
    ap3x3 = AvgPool3x3(name='test_ap3x3',
                       parents=[input_1, input_2],
                       channels=64)
    net = TrainNet(name='test_net')

    net.reset_value()
    out = net(nn.Variable((10,3,32,32)))
    gvg = net.get_gv_graph(active_only=True)
    gvg.render('test_random')

#n_vertices = 5
#modules = {0: 'Conv3x3',
           #1: 'Conv5x5',
           #2: 'MaxPool',
           #3: 'AvgPool',
           #4: 'GavgPool'}

#g = random_dnn(n_vertices=n_vertices,
               #input_channels=3,
               #output_channels=512,
               #candidates=modules,
               #min_channels=32,
               #max_channels=512)
#import pdb; pdb.set_trace()
#random_classes  = {}
#random_channels = {}


#plt.figure(1)
#pos = nx.spring_layout(g)
#nx.draw(g, pos=pos)
#nx.draw_networkx_labels(g, pos=pos)
#plt.show()
