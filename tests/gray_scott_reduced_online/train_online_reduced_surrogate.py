"""
A 2D Gray-Scott reaction diffusion model, with reduced sungrid scale surrogate.

Numerical method:
Craster & Sassi, spectral algorithmns for reaction-diffusion equations, 2006.

Reduced SGS:
W. Edeling, D. Crommelin, Reducing data-driven dynamical subgrid scale
models by physical constraints, Computer & Fluids, 2020.

This script runs the Gray-Scott model at two resolutions, and uses the higher resolution model
to compute the statistics of interest, and drive a reduced subgrid-scale term. This script is
used to generate training data for the predictive phase.
"""

import numpy as np
import easysurrogate as es
import time
import matplotlib.pyplot as plt
import GrayScott_2D as gs


def draw():
    """
    simple plotting routine
    """
    plt.clf()

    ax1 = fig.add_subplot(221)
    ax2 = fig.add_subplot(222)
    ax3 = fig.add_subplot(223)
    ax4 = fig.add_subplot(224)

    # ct = ax1.contourf(xx, yy, u, 100)
    # ct = ax2.contourf(xx, yy, v, 100)

    ax1.plot(T, plot_dict_LR[0], label='model')
    ax1.plot(T, plot_dict_HR[0], 'o', label='ref')
    ax1.legend(loc=0)
    ax2.plot(T, plot_dict_LR[1], label='model')
    ax2.plot(T, plot_dict_HR[1], 'o', label='ref')
    ax2.legend(loc=0)
    ax3.plot(T, plot_dict_LR[2], label='model')
    ax3.plot(T, plot_dict_HR[2], 'o', label='ref')
    ax3.legend(loc=0)
    ax4.plot(T, plot_dict_LR[3], label='model')
    ax4.plot(T, plot_dict_HR[3], 'o', label='ref')
    ax4.legend(loc=0)

    plt.tight_layout()

    plt.pause(0.1)


def qoi_func(X_hat, **kwargs):
    """
    The subroutine that computes the quantities of interest.

    Parameters
    ----------
    X_hat : array (complex)
        The Fourier coefficients of X.
    **kwargs : keyword arguments
        Used to specify the number of gridpoints in 1D (N), and the Fourier coefficients
        of np.ones([N, N]) (V_hat_1).

    Returns
    -------
    array
        The spatial integral of X and the spatial integral of X**2/2.

    """
    if X_hat.shape[0] == 2**8:
        V_hat_1 = kwargs['V_hat_1_HR']
    else:
        V_hat_1 = kwargs['V_hat_1_LR']

    N = X_hat.shape[0]

    # first moment of X
    integral1 = np.dot(V_hat_1.flatten(), np.conjugate(X_hat.flatten())) / N**4
    # second moment of X
    integral2 = 0.5 * np.dot(X_hat.flatten(), np.conjugate(X_hat.flatten())) / N**4

    return np.array([integral1.real, integral2.real])


def compute_int(X1_hat, X2_hat, N):
    """
    Compute the integral of X1*X2 using the Fourier expansion
    """
    integral = np.dot(X1_hat.flatten(), np.conjugate(X2_hat.flatten())) / N**4
    return integral.real


plt.close('all')
plt.rcParams['image.cmap'] = 'seismic'

#########################
# Gray Scott parameters #
#########################

# number of points in one direction for the low-resolution (LR) model
N_LR = 2**7
# number of points in one direction for the high-resolution (HR) model
N_HR = 2**8

# domain size [-L, L]
L = 1.25

# diffusion coefficients
epsilon_u = 2e-5
epsilon_v = 1e-5

# alpha pattern
feed = 0.02
kill = 0.05

# beta pattern
# feed = 0.02
# kill = 0.045

# epsilon pattern
# feed = 0.02
# kill = 0.055

# time step HR model
dt_HR = 0.1
# multiplier which regulates the difference between the HR and LR time step
dt_multiplier = 1
# time step LR model
dt_LR = dt_multiplier * dt_HR

# LR solver
gray_scott_LR = gs.GrayScott_2D(N_LR, L, dt_LR, feed, kill, epsilon_u, epsilon_v)
# HR solver
gray_scott_HR = gs.GrayScott_2D(N_HR, L, dt_HR, feed, kill, epsilon_u, epsilon_v)

#######################
# Easysurrogate setup #
#######################

# create campaign
campaign = es.Campaign()

# number of stats to track per PDE  (we have 2 PDEs)
N_Q = 2

# reduced basis function for the average concentrations of u and v
V_hat_1_LR = np.fft.fft2(np.ones([N_LR, N_LR]))
V_hat_1_HR = np.fft.fft2(np.ones([N_HR, N_HR]))

# create a reduced SGS surrogate object
surrogate = es.methods.Reduced_Surrogate(N_Q, N_LR)

# add surrogate to campaign
campaign.add_app(name="gray_scott_reduced", surrogate=surrogate)

# load the dQ surrogate
dQ_campaign = es.Campaign(load_state=True)
dQ_surr = dQ_campaign.surrogate

# store the surrogate used to predict dQ
campaign.surrogate.set_dQ_surr(dQ_surr)
# online learning nudging time scale
tau_nudge = 1.0
# length of the moving window (in time steps) in which the online training data is stored
window_length = 1
#
batch_size = window_length
#
M = 1
# store the online learning parameters
campaign.surrogate.set_online_training_parameters(tau_nudge, dt_LR, window_length)

###########################
# End Easysurrogate setup #
###########################

# user flags
plot = True
store = True
state_store = True
restart = False

sim_ID = 'test_gray_scott_reduced'

if plot:
    fig = plt.figure(figsize=[8, 8])
    plot_dict_LR = {}
    plot_dict_HR = {}
    T = []
    for i in range(2 * N_Q):
        plot_dict_LR[i] = []
        plot_dict_HR[i] = []

# if plot is true, draw() is called every plot_frame_rate time steps
plot_frame_rate = 100

# initial time and number of LR time steps to take
t = 0.0
n_steps = 50000

# Initial condition
if restart:
    u_hat_LR, v_hat_LR = gray_scott_LR.load_state('./restart/state_LR.pickle')
    u_hat_HR, v_hat_HR = gray_scott_HR.load_state('./restart/state_HR.pickle')
else:
    u_hat_LR, v_hat_LR = gray_scott_LR.initial_cond()
    u_hat_HR, v_hat_HR = gray_scott_HR.initial_cond()

# counters
j = 0

t0 = time.time()
# time stepping
for n in range(n_steps):

    if np.mod(n, 1000) == 0:
        print('time step %d of %d' % (n, n_steps))

    # store the states before the next update
    u_hat_HR_before = np.copy(u_hat_HR)
    v_hat_HR_before = np.copy(v_hat_HR)

    # compute the difference between the LR and the HR states. To do so,
    # the LR state muts be upscaled to the HR grid.
    Delta_u_hat = campaign.surrogate.up_scale(u_hat_LR, N_HR) - u_hat_HR
    Delta_v_hat = campaign.surrogate.up_scale(v_hat_LR, N_HR) - v_hat_HR

    # Solve the HR equation with nudging
    for i in range(dt_multiplier):
        u_hat_HR, v_hat_HR = gray_scott_HR.rk4(u_hat_HR, v_hat_HR,
                                                nudge_u_hat=Delta_u_hat / tau_nudge,
                                                nudge_v_hat=Delta_v_hat / tau_nudge)

    # compute LR and HR QoIs
    Q_HR = np.zeros(2 * N_Q)
    Q_HR[0:N_Q] = qoi_func(u_hat_HR, V_hat_1_HR=V_hat_1_HR)
    Q_HR[N_Q:] = qoi_func(v_hat_HR, V_hat_1_HR=V_hat_1_HR)

    Q_LR = np.zeros(2 * N_Q)
    Q_LR[0:N_Q] = qoi_func(u_hat_LR, V_hat_1_LR=V_hat_1_LR)
    Q_LR[N_Q:] = qoi_func(v_hat_LR, V_hat_1_LR=V_hat_1_LR)

    # pass reduced sgs terms to rk4
    u_hat_LR_before = np.copy(u_hat_LR)
    v_hat_LR_before = np.copy(v_hat_LR)
    u_hat_LR, v_hat_LR = gray_scott_LR.rk4(u_hat_LR, v_hat_LR)

    # Generate the training data for the online learning back prop step
    campaign.surrogate.generate_online_training_data(Q_LR,
                                                      [u_hat_LR_before, v_hat_LR_before],
                                                      [u_hat_LR, v_hat_LR],
                                                      [u_hat_HR_before, v_hat_HR_before],
                                                      [u_hat_HR, v_hat_HR],
                                                      qoi_func,
                                                      V_hat_1_LR=V_hat_1_LR, V_hat_1_HR=V_hat_1_HR)

    # make a prediction for the reduced sgs terms
    dQ_pred = dQ_surr.predict(Q_LR)
    reduced_dict_u = campaign.surrogate.predict([V_hat_1_LR, u_hat_LR], dQ_pred[0:N_Q])
    reduced_dict_v = campaign.surrogate.predict([V_hat_1_LR, v_hat_LR], dQ_pred[N_Q:])
    reduced_sgs_u = np.fft.ifft2(reduced_dict_u['sgs_hat'])
    reduced_sgs_v = np.fft.ifft2(reduced_dict_v['sgs_hat'])

    # update the LR state with the sgs terms in a post-processing step
    u_hat_LR += reduced_sgs_u * dt_LR
    v_hat_LR += reduced_sgs_v * dt_LR

    # update the neural network for dQ every M time steps
    if np.mod(j, M) == 0 and j != 0 and j > window_length:
        dQ_surr.train_online(batch_size=batch_size)

    # we do not want to store the full field reduced source terms
    del reduced_dict_u['sgs_hat']
    del reduced_dict_v['sgs_hat']

    # accumulate the time series in the campaign object
    campaign.accumulate_data(reduced_dict_u, names=['c_ij_u',
                                                    'inner_prods_u', 'src_Q_u',
                                                    'tau_u'])

    campaign.accumulate_data(reduced_dict_v, names=['c_ij_v',
                                                    'inner_prods_v', 'src_Q_v',
                                                    'tau_v'])

    campaign.accumulate_data({'Q_HR': Q_HR, 'Q_LR': Q_LR})

    j += 1
    t += dt_LR
    # plot while running simulation
    if np.mod(j, plot_frame_rate) == 0 and plot:

        # compute concentration field
        u = np.fft.ifft2(u_hat_LR)
        v = np.fft.ifft2(v_hat_LR)

        # append stats
        for i in range(2 * N_Q):
            plot_dict_LR[i].append(Q_LR[i])
            plot_dict_HR[i].append(Q_HR[i])
            # plot_dict_LR[i].append(dQ[i])
            # plot_dict_HR[i].append(Q_HR[i] - Q_LR[i])

        T.append(t)
        draw()

print('*************************************')
print('Simulation time = %f [s]' % (time.time() - t0))
print('*************************************')

# store the state of the system to allow for a simulation restart at t > 0
if state_store:
    gray_scott_LR.store_state('./restart/state_LR.pickle')
    gray_scott_HR.store_state('./restart/state_HR.pickle')

# store the accumulate data to a HDF5 file
if store:
    campaign.store_accumulated_data()
