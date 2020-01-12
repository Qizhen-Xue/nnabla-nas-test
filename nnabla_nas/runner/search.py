import json
import os

import nnabla as nn
import nnabla.functions as F
import nnabla.utils.learning_rate_scheduler as LRS
from nnabla.ext_utils import get_extension_context
from nnabla.logger import logger

import nnabla_nas.utils as ut
from nnabla_nas.dataset import DataLoader
from nnabla_nas.dataset.cifar10.cifar10_data import data_iterator_cifar10
from nnabla_nas.optimizer import Optimizer, Solver
from ..visualization import visualize

class Searcher(object):

    def __init__(self, model, conf):
        # dataset configuration
        data = data_iterator_cifar10(conf['minibatch_size'], True)
        # list of transformers
        train_transform, valid_transform = ut.dataset_transformer(conf)
        split = int(conf['train_portion'] * data.size)
        self.train_loader = DataLoader(
            data.slice(rng=None, slice_start=0, slice_end=split),
            train_transform
        )
        self.valid_loader = DataLoader(
            data.slice(rng=None, slice_start=split, slice_end=50000),
            valid_transform
        )

        # solver configurations
        model_solver = Solver(conf['model_optim'], conf['model_lr'])
        arch_solver = Solver(conf['arch_optim'], conf['arch_lr'],
                             beta1=0.5, beta2=0.999)  # this is for Adam

        max_iter = conf['epoch'] * len(self.train_loader) // conf['batch_size']
        lr_scheduler = LRS.__dict__[conf['model_lr_scheduler']](
            conf['model_lr'],
            max_iter=max_iter
        )
        self.model_optim = Optimizer(
            solver=model_solver,
            grad_clip=conf['model_grad_clip_value'] if
            conf['model_with_grad_clip'] else None,
            weight_decay=conf['model_weight_decay'],
            lr_scheduler=lr_scheduler
        )
        self.arch_optim = Optimizer(
            solver=arch_solver,
            grad_clip=conf['arch_grad_clip_value'] if
            conf['arch_with_grad_clip'] else None,
            weight_decay=conf['arch_weight_decay']
        )

        self.model = model
        self.criteria = lambda o, t: F.mean(F.softmax_cross_entropy(o, t))
        self.conf = conf

    def run(self):
        """Run the training process."""
        conf = self.conf
        model = self.model
        model_optim = self.model_optim
        arch_optim = self.arch_optim
        one_train_epoch = len(self.train_loader) // conf['batch_size']

        # monitor the training process
        monitor = ut.get_standard_monitor(
            one_train_epoch, conf['monitor_path'])
        # write out the configuration
        ut.write_to_json_file(
            content=conf,
            file_path=os.path.join(conf['monitor_path'], 'search_config.json')
        )

        ctx = get_extension_context(
            conf['context'], device_id=conf['device_id'])
        nn.set_default_context(ctx)

        # input and target variables for training
        train_input = nn.Variable(model.input_shape)
        train_target = nn.Variable((conf['minibatch_size'], 1))

        warmup = conf['warmup']
        n_micros = conf['batch_size'] // conf['minibatch_size']

        model.train()
        arch_modules = model.get_arch_modues()  # avoid run through all modules

        train_out = model(ut.image_augmentation(train_input))
        train_loss = self.criteria(train_out, train_target) / n_micros
        train_out.persistent = True
        train_loss.persistent = True

        # assigning parameters
        model_optim.set_parameters(model.get_net_parameters())
        arch_optim.set_parameters(model.get_arch_parameters())

        # input and target variables for validating
        valid_input = nn.Variable(model.input_shape)
        valid_target = nn.Variable((conf['minibatch_size'], 1))
        valid_out = model(valid_input)
        valid_loss = self.criteria(valid_out, valid_target) / n_micros
        valid_out.persistent = True
        valid_loss.persistent = True

        # whether we need to sample everytime
        requires_sample = conf['mode'] != 'full'

        for cur_epoch in range(conf['epoch']):
            monitor.reset()

            for i in range(one_train_epoch):
                curr_iter = i + one_train_epoch * cur_epoch

                if requires_sample:
                    # update the arch modues
                    for m in arch_modules:
                        m._update_active_idx()

                    # sample one graph
                    train_out = model(train_input)
                    train_loss = self.criteria(
                        train_out, train_target) / n_micros

                # clear grad
                model_optim.zero_grad()

                error = loss = 0
                # mini batches update
                for _ in range(n_micros):
                    train_input.d, train_target.d = self.train_loader.next()
                    train_loss.forward(clear_no_need_grad=True)
                    train_loss.backward(clear_buffer=True)
                    error += ut.categorical_error(train_out.d, train_target.d)
                    loss += train_loss.d.copy()

                model_optim.update(curr_iter)
                # add info to the monitor
                monitor['train_loss'].update(loss)
                monitor['train_err'].update(error/n_micros)

                # clear grad
                arch_optim.zero_grad()

                error = loss = 0
                # mini batches update
                for _ in range(n_micros):
                    valid_input.d, valid_target.d = self.valid_loader.next()
                    valid_loss.forward(clear_no_need_grad=True)
                    error += ut.categorical_error(valid_out.d, valid_target.d)
                    loss += valid_loss.d.copy()
                    if warmup == 0 and model._mode == 'full':
                        valid_loss.backward(clear_buffer=True)

                if warmup == 0 and model._mode != 'full':
                    # perform control variate
                    for v in arch_optim.get_parameters().values():
                        v.g = v.g*(loss - conf['control_variate'])

                if warmup == 0:
                    arch_optim.update(curr_iter)

                # add info to the monitor
                monitor['valid_loss'].update(loss)
                monitor['valid_err'].update(error/n_micros)

                if i % conf['print_frequency'] == 0:
                    monitor.display(i)

            # write losses and save model after each epoch
            monitor.write(cur_epoch)

            # saving the architecture parameters
            name = os.path.join(conf['model_save_path'], conf['model_name'])
            if conf['shared_params']:
                ut.save_dart_arch(model, name + '.json')
                if conf['visualize']:
                    outp = os.path.join(conf['monitor_path'], 'visual', str(cur_epoch))
                    visualize(name + '.json', model._num_choices, outp)
            else:
                model.save_parameters(name + '.h5', model.get_arch_parameters())

            warmup -= warmup > 0

        monitor.close()

        return self
