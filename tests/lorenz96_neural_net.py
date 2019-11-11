def rhs_X(X, B):
    """
    Compute the right-hand side of X
    
    Parameters:
        - X (array, size K): large scale variables
        - B (array, size K): SGS term
        
    returns:
        - rhs_X (array, size K): right-hand side of X
    """
    
    rhs_X = np.zeros(K)
    
    #first treat boundary cases (k=1, k=2 and k=K)
    rhs_X[0] = -X[K-2]*X[K-1] + X[K-1]*X[1] - X[0] + F
    
    rhs_X[1] = -X[K-1]*X[0] + X[0]*X[2] - X[1] + F
    
    rhs_X[K-1] = -X[K-3]*X[K-2] + X[K-2]*X[0] - X[K-1] + F
    
    #treat interior points
    for k in range(2, K-1):
        rhs_X[k] = -X[k-2]*X[k-1] + X[k-1]*X[k+1] - X[k] + F
        
    rhs_X += B
        
    return rhs_X


def step_X(X_n, f_nm1, B):
    """
    Time step for X equation, using Adams-Bashforth
    
    Parameters:
        - X_n (array, size K): large scale variables at time n
        - f_nm1 (array, size K): right-hand side of X at time n-1
        - B (array, size K): SGS term
        
    Returns:
        - X_np1 (array, size K): large scale variables at time n+1
        - f_nm1 (array, size K): right-hand side of X at time n
    """
    
    #right-hand side at time n
    f_n = rhs_X(X_n, B)
    
    #adams bashforth
    X_np1 = X_n + dt*(3.0/2.0*f_n - 0.5*f_nm1)
    
    return X_np1, f_n

def wave_variance(X):
    
    X_hat = np.fft.rfft(X, axis=0, norm='ortho')
    X_hat_mean = np.mean(X_hat, axis=0)
    X_hat_var = np.mean(np.abs(X_hat - X_hat_mean)**2, axis=0)
    
    return X_hat_var

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import easysurrogate as es
import h5py, os
from itertools import chain

plt.close('all')

#Lorenz96 parameters
K = 18
J = 20
F = 10.0
h_x = -1.0
h_y = 1.0
epsilon = 0.5

##trimodal Lorenz96 parameters
#K = 32
#J = 16
#F = 18.0
#h_x = -3.2
#h_y = 1.0
#epsilon = 0.5

dt = 0.01
t_end = 1000.0
t = np.arange(0.0, t_end, dt)

make_movie = False
store = False
train = True

HOME = os.path.abspath(os.path.dirname(__file__))

#load training data
store_ID = 'L96'
QoI = ['X_data', 'B_data', 'pinn_data', 'Y_data', 'rhs_Y']
h5f = h5py.File(HOME + '/samples/' + store_ID + '.hdf5', 'r')

print('Loading', HOME + '/samples/' + store_ID + '.hdf5')

for q in QoI:
    print(q)
    vars()[q] = h5f[q][:]

feat_eng = es.methods.Feature_Engineering(X_data, B_data)

lags = [[1, 10, 20, 30]]
max_lag = np.max(list(chain(*lags)))

X_train, y_train = feat_eng.lag_training_data([X_data], lags = lags)

if train:
   
    #standard regression neural net
    surrogate = es.methods.ANN(X=X_train, y=y_train, n_layers=3, n_neurons=128, n_out=K,
                               activation='hard_tanh', activation_out='linear',
                               batch_size=256, loss = 'squared',
                               lamb=0.0, decay_step=10**5, decay_rate=0.9, standardize_X=False,
                               standardize_y=False, save=True)
    
    surrogate.train(10000, store_loss = True)
else:    
    surrogate = es.methods.ANN(X=X_train, y=y_train)
    surrogate.load_ANN()

surrogate.get_n_weights()

n_feat = surrogate.n_in

for i in range(max_lag):
    feat_eng.append_feat([X_data[i]], max_lag)

X_n = X_data[max_lag]
B_n = B_data[max_lag]

X_nm1 = X_data[max_lag-1]
B_nm1 = B_data[max_lag-1]

#initial right-hand sides
f_nm1 = rhs_X(X_nm1, B_nm1)

#allocate memory for solutions
sol = np.zeros([t.size, K])

#start time integration
idx = 0
for t_i in t[max_lag:]:

    #ANN SGS solve
    feat = feat_eng.get_feat_history()
    B_n = surrogate.feed_forward(feat.reshape([1, feat.size])).flatten()
    
    #solve large-scale equation
    X_np1, f_n = step_X(X_n, f_nm1, B_n)
    feat_eng.append_feat([X_np1, B_n], max_lag)

    #store solutions
    sol[idx, :] = X_n
    idx += 1

    #update variables
    X_n = X_np1
    f_nm1 = f_n
    
    if np.mod(idx, 1000) == 0:
        print('t =', np.around(t_i, 1), 'of', t_end)
    
#############   
# Plot PDEs #
#############
    
fig = plt.figure()
ax = fig.add_subplot(111, xlabel=r'$X_k$')

post_proc = es.methods.Post_Processing()
X_dom_surr, X_pde_surr = post_proc.get_pde(sol.flatten()[0:-1:10])
X_dom, X_pde = post_proc.get_pde(X_data.flatten()[0:-1:10])

ax.plot(X_dom, X_pde, 'ko', label='L96')
ax.plot(X_dom_surr, X_pde_surr, label='ANN')

plt.yticks([])

plt.legend(loc=0)

plt.tight_layout()

#############   
# Plot ACFs #
#############

fig = plt.figure()
ax = fig.add_subplot(111, ylabel='ACF', xlabel='time')

R_data = post_proc.auto_correlation_function(X_data[:,0], max_lag=1000)
R_sol = post_proc.auto_correlation_function(sol[:, 0], max_lag=1000)

dom = np.arange(R_data.size)*dt

ax.plot(dom, R_data, 'ko', label='L96')
ax.plot(dom, R_sol, label='ANN')

leg = plt.legend(loc=0)

plt.tight_layout()

#############   
# Plot CCFs #
#############

fig = plt.figure()
ax = fig.add_subplot(111, ylabel='CCF', xlabel='time')

C_data = post_proc.cross_correlation_function(X_data[:,0], X_data[:,1], max_lag=1000)
C_sol = post_proc.cross_correlation_function(sol[:, 0], sol[:, 1], max_lag=1000)

dom = np.arange(C_data.size)*dt

ax.plot(dom, C_data, 'ko', label='L96')
ax.plot(dom, C_sol, label='ANN')

leg = plt.legend(loc=0)

plt.tight_layout()

plt.show()