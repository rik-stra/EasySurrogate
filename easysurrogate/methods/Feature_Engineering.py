import numpy as np
from itertools import chain
import tkinter as tk
import h5py
from scipy import stats

"""
===============================================================================
CLASS FOR FEATURE ENGINEERING SUBROUTINES
===============================================================================
"""


class Feature_Engineering:

    def __init__(self, **kwargs):
        print('Creating feature engineering object')

    def standardize_data(self, standardize_X=True, standardize_y=True):
        """
        Standardize the training data
        """

        if standardize_X:
            X_mean = np.mean(self.X, axis=0)
            X_std = np.std(self.X, axis=0)
        else:
            X_mean = 0.0
            X_std = 1.0

        if standardize_y:
            y_mean = np.mean(self.y, axis=0)
            y_std = np.std(self.y, axis=0)
        else:
            y_mean = 0.0
            y_std = 1.0

        return (self.X - X_mean) / X_std, (self.y - y_mean) / y_std

    def lag_training_data(self, X, y, lags, **kwargs):
        """
        Create time-lagged supervised training data X, y

        Parameters:
            X: features. Either an array of dimension (n_samples, n_features)
               or a list of arrays of dimension (n_samples, n_features)

            y: training target. Array of dimension (n_samples, n_outputs)

            lags: list of lists, containing the integer values of lags
                  Example: if X=[X_1, X_2] and lags = [[1], [1, 2]], the first
                  feature array X_1 is lagged by 1 (time) step and the second
                  by 1 and 2 (time) steps.

        Returns:
            X_train, y_trains (arrays), of lagged features and target data. Every
            row of X_train is one (time) lagged feature vector. Every row of y_train
            is a target vector at the next (time) step
        """

        # compute the max number of lags in lags
        lags_flattened = list(chain(*lags))
        max_lag = np.max(lags_flattened)

        # total number of data samples
        n_samples = y.shape[0]

        # if X is one array, add it to a list anyway
        if isinstance(X, np.ndarray):
            tmp = []
            tmp.append(X)
            X = tmp

        # True/False on wether the X features are symmetric arrays or not
        if 'X_symmetry' in kwargs:
            self.X_symmetry = kwargs['X_symmetry']
        else:
            self.X_symmetry = np.zeros(len(X), dtype=bool)

        # compute target data at next (time) step
        if y.ndim == 2:
            y_train = y[max_lag:, :]
        elif y.ndim == 1:
            y_train = y[max_lag:]
        else:
            print("Error: y must be of dimension (n_samples, ) or (n_samples, n_outputs)")
            return

        # a lag list must be specified for every feature in X
        if len(lags) != len(X):
            print('Error: no specified lags for one of the featutes in X')
            return

        # compute the lagged features
        C = []
        idx = 0
        for X_i in X:

            # if X_i features are symmetric arrays, only select upper triangular part
            if self.X_symmetry[idx]:
                idx0, idx1 = np.triu_indices(X_i.shape[1])
                X_i = X_i[:, idx0, idx1]

            for lag in np.sort(lags[idx])[::-1]:
                begin = max_lag - lag
                end = n_samples - lag

                if X_i.ndim == 2:
                    C.append(X_i[begin:end, :])
                elif X_i.ndim == 1:
                    C.append(X_i[begin:end])
                else:
                    print("Error: X must contains features of dimension (n_samples, ) or (n_samples, n_features)")
                    return
            idx += 1

        # C is a list of lagged features, turn into a single array X_train
        X_train = C[0]

        if X_train.ndim == 1:
            X_train = X_train.reshape([y_train.shape[0], 1])

        for X_i in C[1:]:

            if X_i.ndim == 1:
                X_i = X_i.reshape([y_train.shape[0], 1])

            X_train = np.append(X_train, X_i, axis=1)

        # initialize the storage of features
        self.init_feature_history(lags)

        return X_train, y_train

    def get_feat_history(self):
        """
        Return the features from the feat_history dict based on the lags
        specified in self.lags

        Returns:
            X_i: array of lagged features of dimension (feat1.size + feat2.size + ...,)
        """
        X_i = []

        idx = 0
        for i in range(self.n_feat_arrays):
            for lag in self.lags[idx]:
                begin = self.max_lag - lag

                X_i.append(self.feat_history[i][begin])
            idx += 1

        return np.array(list(chain(*X_i)))

    def bin_data(self, y, n_bins):
        """
        Bin the data y in to n_bins non-overlapping bins

        Parameters
        ----------
        y, array, size (number of samples, number of variables): Data
        n_bins, int: Number of (equidistant) bins to be used.

        Returns
        -------
        None.

        """

        n_samples = y.shape[0]

        if y.ndim == 2:
            n_vars = y.shape[1]
        else:
            n_vars = 1
            y = y.reshape([n_samples, 1])

        self.binnumbers = np.zeros([n_samples, n_vars]).astype('int')
        self.y_binned = {}
        self.y_binned_mean = {}
        y_idx_binned = np.zeros([n_samples, n_bins * n_vars])
        self.bins = {}
        self.n_vars = n_vars

        for i in range(n_vars):

            self.y_binned[i] = {}
            self.y_binned_mean[i] = {}

            bins = np.linspace(np.min(y[:, i]), np.max(y[:, i]), n_bins + 1)
            self.bins[i] = bins

            count, _, self.binnumbers[:, i] = \
                stats.binned_statistic(y[:, i], np.zeros(n_samples), statistic='count', bins=bins)

            unique_binnumbers = np.unique(self.binnumbers[:, i])

            offset = i * n_bins

            for j in unique_binnumbers:
                idx = np.where(self.binnumbers[:, i] == j)
                self.y_binned[i][j - 1] = y[idx, i]
                self.y_binned_mean[i][j - 1] = np.mean(y[idx, i])
                y_idx_binned[idx, offset + j - 1] = 1.0

        return y_idx_binned

    def init_feature_history(self, lags):
        """
        Initialize the feat_history dict. This dict keeps track of the features
        arrays that were used up until 'max_lag' steps ago.

        Parameters:

            lags: list of lists, containing the integer values of lags
                  Example: if X=[X_1, X_2] and lags = [[1], [1, 2]], the first
                  feature array X_1 is lagged by 1 (time) step and the second
                  by 1 and 2 (time) steps.
        """
        self.lags = []

        for l in lags:
            self.lags.append(np.sort(l)[::-1])

        self.max_lag = np.max(list(chain(*lags)))

        self.feat_history = {}

        # the number of feature arrays that make up the total input feature vector
        self.n_feat_arrays = len(lags)

        for i in range(self.n_feat_arrays):
            self.feat_history[i] = []

    def append_feat(self, X):
        """
        Append the feature vectors in X to feat_history dict

        Parameters:

            X: features. Either an array of dimension (n_samples, n_features)
               or a list of arrays of dimension (n_samples, n_features)
        """

        # if X is one array, add it to a list anyway
        if isinstance(X, np.ndarray):
            X = [X]
            # tmp = []
           # tmp.append(X)
           # X = tmp

        for i in range(self.n_feat_arrays):

            if not isinstance(X[i], np.ndarray):
                X[i] = np.array([X[i]])

            # if X_i features are symmetric arrays, only select upper trian. part
            if self.X_symmetry[i]:
                idx0, idx1 = np.triu_indices(X[i].shape[1])
                X[i] = X[i][idx0, idx1]

            if X[i].ndim != 1:
                X[i] = X[i].flatten()

            self.feat_history[i].append(X[i])

            # if max number of features is reached, remove first item
            if len(self.feat_history[i]) > self.max_lag:
                self.feat_history[i].pop(0)

    def recursive_moments(self, X_np1, mu_n, sigma2_n, N):
        """
        Recursive formulas for the mean and variance. Computes the new moments
        when given a new sample and the old moments.

        Arguments
        ---------
        + X_np1: a new sample of random variable X
        + mu_n: the sample mean of X, not including X_np1
        + sigma2_n: the variance of X, not including X_np1
        + N: the total number of samples thus far

        Returns
        -------
        The mean and variance, updated based on the new sample

        """
        mu_np1 = mu_n + (X_np1 - mu_n) / (N + 1)
        sigma2_np1 = sigma2_n + mu_n**2 - mu_np1**2 + (X_np1**2 - sigma2_n - mu_n**2) / (N + 1)

        return mu_np1, sigma2_np1

    # def estimate_embedding_dimension(self, y, N):

    #     for n in range(3, N+1):

    #         lags_n = range(1, n)
    #         lags_np1 = range(1, n+1)
    #         y_n, _ = self.lag_training_data(y, np.zeros(y.size), [lags_n])
    #         y_np1, _ = self.lag_training_data(y, np.zeros(y.size), [lags_np1])

    #         L = y_np1.shape[0]
    #         dist_n = np.zeros(L)
    #         dist_np1 = np.zeros(L)

    #         for l in range(L):
    #             # d = np.linalg.norm(y_n - y_n[l], axis = 0)
    #             d = np.sum((y_n - y_n[l])**2, axis=1)
    #             a, d_min = np.partition(d, 1)[0:2]
    #             # d = np.linalg.norm(y_np1 - y_np1[l], axis = 0)
    #             d = np.sum((y_np1 - y_np1[l])**2, axis=1)
    #             _, d_min2 = np.partition(d, 1)[0:2]

    #             dist_n[l] = d_min
    #             dist_np1[l] = d_min2

    #         test = np.abs((dist_n - dist_np1)/dist_n)

    #         print(len(lags_n))
    #         print(np.where(test > 20)[0].size)
