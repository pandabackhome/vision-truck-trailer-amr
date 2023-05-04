#
#     This file is part of rockit.
#
#     rockit -- Rapid Optimal Control Kit
#     Copyright (C) 2019 MECO, KU Leuven. All rights reserved.
#
#     Rockit is free software; you can redistribute it and/or
#     modify it under the terms of the GNU Lesser General Public
#     License as published by the Free Software Foundation; either
#     version 3 of the License, or (at your option) any later version.
#
#     Rockit is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#     Lesser General Public License for more details.
#
#     You should have received a copy of the GNU Lesser General Public
#     License along with CasADi; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
#

"""
Motion planning
===============

Simple motion planning for vehicle with trailer
"""

from rockit import *
import matplotlib.pyplot as plt
import numpy as np
from numpy import pi, cos, sin, tan
from casadi import vertcat, horzcat
from plot_trailer import *
from simulator import *
import yaml

show_figures = True
use_simulator = False
save_for_gif = False

refine = 2
Ts = 0.1

# Environment
og = 0*pi/180
sg = sin(og)
cg = cos(og)

xcr = 0.5
ycr = 2.
pcr = vertcat(xcr, ycr)

xcl = -0.5
ycl = 2.4
pcl = vertcat(xcl, ycl)

n1_1 = vertcat(-cg, sg)
w1_1 = vertcat(n1_1, -n1_1.T @ pcl)

n2_1 = -n1_1
w2_1 = vertcat(n2_1, -n2_1.T @ pcr)

n1_2 = vertcat(sg, cg)
w1_2 = vertcat(n1_2, -n1_2.T @ pcl)

n2_2 = -n1_2
w2_2 = vertcat(n2_2, -n2_2.T @ pcr)

# Parameters
with open('truck_trailer_para.yaml', 'r') as file:
    para = yaml.safe_load(file)

L0 = para['truck']['L']
M0 = para['truck']['M']
W0 = para['truck']['W']
L1 = para['trailer1']['L']
M1 = para['trailer1']['M']
W1 = para['trailer1']['W']

x1_t0 = 0.
y1_t0 = 0.
theta1_t0 = pi/2
theta0_t0 = pi/2

x1_tf = 1.5
y1_tf = (ycl + ycr)/2
theta1_tf = 0.
theta0_tf = 0.

def create_stage(ocp, t0, T, N, M, w):
	stage = ocp.stage(t0=t0, T=T)

	# Trailer model
	theta1 = stage.state()
	x1     = stage.state()
	y1     = stage.state()

	theta0 = stage.state()
	x0     = x1 + L1*cos(theta1) + M0*cos(theta0)
	y0     = y1 + L1*sin(theta1) + M0*sin(theta0)

	delta0 = stage.control(order=1)
	v0     = stage.control(order=1)

	beta01 = theta0 - theta1

	dtheta0 = v0/L0*tan(delta0)
	dtheta1 = v0/L1*sin(beta01) - M0/L1*cos(beta01)*dtheta0
	v1 = v0*cos(beta01) + M0*sin(beta01)*dtheta0

	stage.set_der(theta1, dtheta1)
	stage.set_der(x1,     v1*cos(theta1))
	stage.set_der(y1,     v1*sin(theta1))

	stage.set_der(theta0, dtheta0)

	# Path constraints
	stage.subject_to(-.2 <= (v0 <= .2))
	stage.subject_to(-1 <= (stage.der(v0) <= 1))

	stage.subject_to(-pi/6 <= (delta0 <= pi/6))
	stage.subject_to(-pi/10 <= (stage.der(delta0) <= pi/10))

	stage.subject_to(-pi/2 <= (beta01 <= pi/2))

	stage.method(MultipleShooting(N=N, M=M, intg='rk'))

	# Room constraint
	veh_vertices = vert_vehic(x0, y0, theta0, W0/2, W0/2, L0, M0)
	for veh_vertex in veh_vertices:
		phom = vertcat(veh_vertex[0], veh_vertex[1], 1)
		stage.subject_to(w.T @ phom <= 0)
	veh_vertices = vert_vehic(x1, y1, theta1, W1/2, W1/2, L1, M1)
	for veh_vertex in veh_vertices:
		phom = vertcat(veh_vertex[0], veh_vertex[1], 1)
		stage.subject_to(w.T @ phom <= 0)
	
	# Minimal time
	stage.add_objective(stage.T)
	
	return stage, theta1, x1, y1, theta0, x0, y0, delta0, v0

def stitch_stages(ocp, stage1, stage2):
	# Stitch time
	ocp.subject_to(stage1.tf == stage2.t0)
	# Stitch states
	for i in range(len(stage1.states)):
		ocp.subject_to(stage2.at_t0(stage2.states[i]) == stage1.at_tf(stage1.states[i]))

ocp = Ocp()

# Stage 1 - Approach
N_1 = 10
M_1 = 2
T_1 = 10.
N_2 = 5
M_2 = 2
T_2 = 10.
N_3 = 10
M_3 = 2
T_3 = 10.

stage_1, theta1_1, x1_1, y1_1, theta0_1, x0_1, y0_1, delta0_1, v0_1 = \
		create_stage(ocp, FreeTime(0), FreeTime(T_1), N_1, M_1, horzcat(w1_1, w2_1, w1_2))

# Initial constraints
ocp.subject_to(stage_1.t0 == 0)
ocp.subject_to(stage_1.at_t0(x1_1) == x1_t0)
ocp.subject_to(stage_1.at_t0(y1_1) == y1_t0)
ocp.subject_to(stage_1.at_t0(theta1_1) == theta1_t0)
ocp.subject_to(stage_1.at_t0(theta0_1) == theta0_t0)

# Stage 2 - Corner
stage_2, theta1_2, x1_2, y1_2, theta0_2, x0_2, y0_2, delta0_2, v0_2 = \
		create_stage(ocp, FreeTime(T_1), FreeTime(T_2), N_2, M_2, horzcat(w1_2, w2_2, w1_1))
stitch_stages(ocp, stage_1, stage_2)

# Final constraint
ocp.subject_to(stage_2.at_tf(x1_2) == x1_tf)
ocp.subject_to(stage_2.at_tf(y1_2) == y1_tf)
ocp.subject_to(stage_2.at_tf(theta1_2) == theta1_tf)
ocp.subject_to(stage_2.at_tf(theta0_2) == theta0_tf)

# Pick a solution method
options = { "expand": True,
			"verbose": False,
			"print_time": True,
			"error_on_fail": True,
			"ipopt": {	"linear_solver": "ma57",
						"tol": 1e-8}}
ocp.solver('ipopt', options)

# Make it concrete for this ocp

theta1_1s = stage_1.sample(theta1_1, grid='control')[1]
x1_1s     = stage_1.sample(x1_1, 	 grid='control')[1]
y1_1s     = stage_1.sample(y1_1, 	 grid='control')[1]
theta0_1s = stage_1.sample(theta0_1, grid='control')[1]
delta0_1s = stage_1.sample(delta0_1, grid='control')[1]
v0_1s     = stage_1.sample(v0_1, 	 grid='control')[1]

theta1_2s = stage_2.sample(theta1_2, grid='control')[1]
x1_2s     = stage_2.sample(x1_2, 	 grid='control')[1]
y1_2s     = stage_2.sample(y1_2, 	 grid='control')[1]
theta0_2s = stage_2.sample(theta0_2, grid='control')[1]
delta0_2s = stage_2.sample(delta0_2, grid='control')[1]
v0_2s     = stage_2.sample(v0_2, 	 grid='control')[1]

sampler1  = stage_1.sampler([theta1_1, x1_1, y1_1, theta0_1, x0_1, y0_1, delta0_1, v0_1])
sampler2  = stage_2.sampler([theta1_2, x1_2, y1_2, theta0_2, x0_2, y0_2, delta0_2, v0_2])

t1 = ocp.value(stage_1.T)
t2 = t1 + ocp.value(stage_2.T)

solve_ocp = ocp.to_function('solve_ocp',
							[ocp.value(stage_1.T), theta1_1s, x1_1s, y1_1s, theta0_1s, delta0_1s, v0_1s, \
							 ocp.value(stage_2.T), theta1_2s, x1_2s, y1_2s, theta0_2s, delta0_2s, v0_2s], \
							[t1, theta1_1s, x1_1s, y1_1s, theta0_1s, delta0_1s, v0_1s, \
							 t2, theta1_2s, x1_2s, y1_2s, theta0_2s, delta0_2s, v0_2s, ocp.gist])

# Solve func
t1_sol, theta1_1sol, x1_1sol, y1_1sol, theta0_1sol, delta0_1sol, v0_1sol, \
	t2_sol,	theta1_2sol, x1_2sol, y1_2sol, theta0_2sol, delta0_2sol, v0_2sol, gist_sol = \
		 solve_ocp(T_1, theta1_t0,     x1_t0, np.linspace(y1_t0,y1_tf,N_1+1), theta0_t0,  							  0., .1,\
			 	   T_2, np.linspace(theta1_t0,theta1_tf,N_2+1), x1_t0, y1_tf, np.linspace(theta0_t0,theta0_tf,N_2+1), 0., 0.)

t1_ctrl = np.arange(0., t1_sol, Ts)
t2_ctrl = np.arange(t1_sol, t2_sol, Ts)
[theta1_1ctrl, x1_1ctrl, y1_1ctrl, theta0_1ctrl, x0_1ctrl, y0_1ctrl, delta0_1ctrl, v0_1ctrl] = sampler1(gist_sol, t1_ctrl)
[theta1_2ctrl, x1_2ctrl, y1_2ctrl, theta0_2ctrl, x0_2ctrl, y0_2ctrl, delta0_2ctrl, v0_2ctrl] = sampler2(gist_sol, t2_ctrl)

theta1_ctrl = np.concatenate([theta1_1ctrl, theta1_2ctrl])
x1_ctrl     = np.concatenate([x1_1ctrl, x1_2ctrl])
y1_ctrl     = np.concatenate([y1_1ctrl, y1_2ctrl])
theta0_ctrl = np.concatenate([theta0_1ctrl, theta0_2ctrl])
x0_ctrl     = np.concatenate([x0_1ctrl, x0_2ctrl])
y0_ctrl     = np.concatenate([y0_1ctrl, y0_2ctrl])
delta0_ctrl = np.concatenate([delta0_1ctrl, delta0_2ctrl])
v0_ctrl     = np.concatenate([v0_1ctrl, v0_2ctrl])
t_ctrl      = np.concatenate([t1_ctrl, t2_ctrl])

result_yaml = {
	"x": {
		"px1": x1_ctrl,
		"py1": y1_ctrl,
		"theta1": theta1_ctrl,
		"px0": x0_ctrl,
		"py0": y0_ctrl,
		"theta0": theta0_ctrl},
	"u": {
		#"omega": dtheta0_ctrl,
		"delta": delta0_ctrl,
		"v_l": v0_ctrl},
	"t": t_ctrl
	}

with open('truck_trailer_x_u.yaml', 'w') as file:
    yaml.dump(result_yaml, file)

Nsim = len(t_ctrl)
if use_simulator:
	# -------------------------------
	# Logging variables
	# -------------------------------
	theta1_sim = np.zeros(Nsim)
	x1_sim     = np.zeros(Nsim)
	y1_sim     = np.zeros(Nsim)

	theta0_sim = np.zeros(Nsim)
	x0_sim     = np.zeros(Nsim)
	y0_sim     = np.zeros(Nsim)

	x_current = vertcat(theta1_t0, x1_t0, y1_t0, theta0_t0)

	simu = simulator_delta_init()

	for k in range(Nsim-1):
		beta01_sim = theta0_sim[k] - theta1_sim[k]
		beta01_ctrl = theta0_ctrl[k] - theta1_ctrl[k]
		error = beta01_ctrl - beta01_sim
		# if error > 0.:
		# 	print('iter:', k, '\t beta01 error:', error, '\t -correction')
		# 	delta0_ctrl[k] = delta0_ctrl[k] - .02
		# elif error < -0.:
		# 	print('iter:', k, '\t beta01 error:', error, '\t +correction')
		# 	delta0_ctrl[k] = delta0_ctrl[k] + .02

		u = vertcat(delta0_ctrl[k], v0_ctrl[k])
		dt = t_ctrl[k+1] - t_ctrl[k]
		x_next = simulator(simu, x_current, u, dt)

		theta1_sim[k+1] = x_next[0]
		x1_sim[k+1]     = x_next[1]
		y1_sim[k+1]     = x_next[2]

		theta0_sim[k+1] = x_next[3]
		x0_sim[k+1]     = x_next[1] + L1*cos(x_next[0]) + M0*cos(x_next[3])
		y0_sim[k+1]     = x_next[2] + L1*sin(x_next[0]) + M0*sin(x_next[3])

		x_current = x_next

if show_figures:
	# Show results
	from pylab import *

	plt.figure(1)
	ax1 = plt.subplot(1, 1, 1)
	ax1.axis('equal')

	ax1.plot(x0_ctrl, y0_ctrl, color='grey')
	ax1.plot(x1_ctrl, y1_ctrl, color='r')

	ax1.plot(x1_1sol[0], y1_1sol[0],'kx')
	ax1.plot(x1_1sol[-1], y1_1sol[-1],'kx')
	ax1.plot(x1_2sol[0], y1_2sol[0],'kx')
	ax1.plot(x1_2sol[-1], y1_2sol[-1],'kx')

	draw_constraint(w1_1.full().T[0], ax1, 'red')
	draw_constraint(w2_1.full().T[0], ax1, 'red')
	draw_constraint(w1_2.full().T[0], ax1, 'red')
	draw_constraint(w2_2.full().T[0], ax1, 'red')
	ax1.set_ylim(-2, 4)

	plt.figure(2)
	ax21 = plt.subplot(1, 2, 1)
	ax22 = plt.subplot(1, 2, 2)
	ax21.plot(t_ctrl, delta0_ctrl)
	ax22.plot(t_ctrl, v0_ctrl)

	for k in range(Nsim-1):
		x0s     = x0_ctrl[k]
		y0s     = y0_ctrl[k]
		theta0s = theta0_ctrl[k]
		x1s     = x1_ctrl[k]
		y1s     = y1_ctrl[k]
		theta1s = theta1_ctrl[k]
		delta0s = delta0_ctrl[k]

		truck           = vehic_to_plot(ax1, x0s, y0s, theta0s, W0/2,  W0/2,      L0, M0, color='grey')
		truck_steer     = wheel_to_plot(ax1, x0s, y0s, theta0s,   L0,     0, delta0s,     color='k')
		truck_fixed_1   = wheel_to_plot(ax1, x0s, y0s, theta0s,    0,  W0/2,       0,     color='k')
		truck_fixed_2   = wheel_to_plot(ax1, x0s, y0s, theta0s,    0, -W0/2,       0,     color='k')
		truck_xy        = ax1.plot(x0s, y0s, 'x', color='grey')
		if use_simulator:
			truck_xy_sim = ax1.plot(x0_sim[k], y0_sim[k], '.', color='darkgrey')

		trailer         = vehic_to_plot(ax1, x1s, y1s, theta1s, W1/2,  W1/2,   .8*L1, M1, color='r')
		trailer_fixed_1 = wheel_to_plot(ax1, x1s, y1s, theta1s,    0,  W1/2,       0,     color='k')
		trailer_fixed_2 = wheel_to_plot(ax1, x1s, y1s, theta1s,    0, -W1/2,       0,     color='k')
		trailer_xy      = ax1.plot(x1s, y1s, 'x', color='r')
		if use_simulator:
			trailer_xy_sim = ax1.plot(x1_sim[k], y1_sim[k], '.', color='darkred')

		coupling     = vert_single(x0s, y0s, theta0s, -M0, 0)
		coupling_xy  = ax1.plot([x1s, coupling[0][0]], [y1s, coupling[0][1]], '-', color='k')
		coupling_dot = ax1.plot(coupling[0][0], coupling[0][1], 'o', color='k')	

		if save_for_gif:
			png_name = 'trailer'+str(k)+'.png'
			plt.savefig(png_name)

		pause(.001)
		if k < Nsim-1:
			truck.pop(0).remove()
			truck_steer.pop(0).remove()
			truck_fixed_1.pop(0).remove()
			truck_fixed_2.pop(0).remove()
			truck_xy.pop(0).remove()
			trailer.pop(0).remove()
			trailer_fixed_1.pop(0).remove()
			trailer_fixed_2.pop(0).remove()
			trailer_xy.pop(0).remove()
			coupling_xy.pop(0).remove()
			coupling_dot.pop(0).remove()

	if use_simulator:
		plt.figure(3)
		ax3 = plt.subplot(1, 1, 1)
		ax3.plot(theta0_sim - theta1_sim)
		ax3.plot(theta0_ctrl - theta1_ctrl)
		ax3.legend(['sim','ctrl'])

	show(block=True)
