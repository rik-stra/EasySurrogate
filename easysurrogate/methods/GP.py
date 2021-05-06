import numpy as np
import pickle
import tkinter as tk
from tkinter import filedialog
from scipy.stats import rv_discrete
import h5py

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import DotProduct, WhiteKernel, Matern, RBF, ConstantKernel
from sklearn.metrics import mean_squared_error as mse

import mogp_emulator as mogp
from mogp_emulator import GaussianProcess, MultiOutputGP
from mogp_emulator.MeanFunction import Coefficient, LinearMean, MeanFunction


class GP:

    def __init__(
                 self,
                 X,
                 y,
                 n_out=1,
                 kernel='Matern',
                 length_scale=1.0,
                 prefactor=True,
                 bias=False,
                 noize=1e-8,
                 save=True,
                 load=False,
                 name='GP',
                 on_gpu=False,
                 backend='scikit-learn',
                 standardize_X=True,
                 standardize_y=True,
                 **kwargs):

        self.backend = backend
        self.n_train = X.shape[0]

        try:
            self.n_in = X.shape[1]
        except IndexError:
            self.n_in = 1

        try:
            self.n_out = y.shape[1]
        except IndexError:
            self.n_out = 1

        self.on_gpu = on_gpu

        # sciki-learn specific part
        if self.backend == 'scikit-learn':
            self.kernel = ConstantKernel(constant_value=1.0,
                                         constant_value_bounds=(1e-6, 1e+6))

            if kernel == 'Matern':
                self.kernel *= Matern([length_scale]*self.n_in)
            elif kernel == 'RBF':
                self.kernel *= RBF(length_scale=[length_scale]*self.n_in,
                                   length_scale_bounds=[length_scale*1e-4, length_scale*1e+4])

            if bias:
                self.kernel += ConstantKernel(constant_value=1.0,
                                              constant_value_bounds=(1e-5, 1e+5))

            noize_val = 1e-8
            bounds_val = (noize_val * 1e-3, noize_val * 1e+3)
            if noize == 'adaptive':
                noize_val = 1e-12
                bounds_val = 'fixed'
            elif isinstance(noize, float):
                noize_val = noize
                bounds_val = (noize_val * 1e-3, noize_val * 1e+3)
            if noize is not False:
                self.kernel += WhiteKernel(noise_level=noize_val,
                                           noise_level_bounds=bounds_val)

            self.instance = GaussianProcessRegressor(kernel=self.kernel, n_restarts_optimizer=5, normalize_y=True)  #, random_state=42

        # MOGP specific part
        elif self.backend == 'mogp':

            kernel_argument = ''

            if kernel == 'Matern':
                kernel_argument += 'Matern52'

            if kernel == 'RBF':
                kernel_argument += 'SquaredExponential'

            if isinstance(noize, float):
                noize_argument = noize
            elif noize == 'fit' or noize is True:
                noize_argument = 'fit'
            elif noize == 'adaptive':
                noize_argument = 'adaptive'
            else:
                noize_argument = 'adaptive'  # redundant, but keeping a default option for future

            if bias:
                raise NotImplementedError('Non-stationary kernels are not implemented in MOGP')

            #mean = Coefficient() + Coefficient() * LinearMean()

            if self.n_out == 1:
                self.instance = GaussianProcess(X, y.reshape(-1), kernel=kernel_argument, nugget=noize_argument)
            else:
                self.instance = MultiOutputGP(X, y.T, kernel=kernel_argument, nugget=noize_argument)
                #TODO MultiOutputGP() has no kernel, fix printing

        else:
            raise NotImplementedError('Currently supporting only scikit-learn and mogp backend')

        self.train(X, y)

        if backend == 'scikit-learn':
            self.kernel = self.instance.kernel_

    def train(self, X, y):
        if self.backend == 'scikit-learn':
            self.instance.fit(X, y)
        if self.backend == 'mogp':
            self.instance = mogp.fit_GP_MAP(self.instance)

    def predict(self, X_i):
        if self.backend == 'scikit-learn':
            # for single sample X_i should be nparray(1, n_feat)
            m, v = self.instance.predict(X_i.reshape(1, -1), return_std=True)
        elif self.backend == 'mogp':
            m, v, d = self.instance.predict(X_i)
        else:
            raise NotImplementedError('Non-stationary kernels are not implemented in MOGP')
        return m, v

    def forward(self, X_i):  # for no cases when required different from predict at GP case
        m, v = self.instance.predict(X_i)
        return m  # for single sample should be nparray(1,n_feat)

    def print_model_info(self):
        print('===============================')
        print('Gaussian Process parameters')
        print('===============================')
        if self.backend == 'scikit-learn':
            # print('Kernel params =', self.instance.kernel_.get_params())
            print('Kernel =', self.instance.kernel_)
            print('Kernel theta =', self.instance.kernel_.theta)
        if self.backend == 'mogp':
            print('Kernel theta =', self.instance.theta)
        print('Output dimensionality =', self.n_out)
        print('Input dimensionality =', self.n_in)
        print('On GPU =', self.on_gpu)
        print('===============================')