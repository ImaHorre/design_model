import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from scipy.sparse import lil_matrix
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import spsolve
from screeninfo import get_monitors

def define_parameters(Mcl, Mcd, Mcw, mcd, mcw, mcl, pitch, constriction_ratio):

    constriction_l = mcl * constriction_ratio  # Constriction length
    Nmc = int(np.floor(Mcl / pitch))  # Number of microchannels

    mu_water = 0.00089
    mu_oil = 0.03452
    emulsion_ratio = 0.3
    droplet_radius = 0.5 * 10 ** -6
    droplet_volume = 4 / 3 * 3.14 * droplet_radius ** 3
    print(droplet_volume)
    production_frequency = 50
    Q_oil = production_frequency * droplet_volume * Nmc
    Q_water = Q_oil / emulsion_ratio

    # hydraulic_resistance_mc_darwinMF = 12 * mu_oil * mcl / (1 - (0.63 * mcd ** 4))
    # hydraulic_resistance_Omc_Elveflow = 12 * mu_oil * constriction_l / (mcw * mcd ** 3) * 1 / (
    #             1 - (0.63 * mcd / mcw) * np.tan(1.57 * (mcw / mcd)))
    # hydraulic_resistance_OMc_Elveflow = 12 * mu_oil * pitch / (Mcw * Mcd ** 3) * 1 / (
    #             1 - (0.63 * Mcd / Mcw) * np.tan(1.57 * (Mcw / Mcd)))
    # hydraulic_resistance_WMc_Elveflow = 12 * mu_water * pitch / (Mcw * Mcd ** 3) * 1 / (
    #             1 - (0.63 * Mcd / Mcw) * np.tan(1.57 * (Mcw / Mcd)))

    hydraulic_resistance_mc_darwinMF = 12 * mu_oil * mcl / (1 - (0.63 * mcd ** 4))
    hydraulic_resistance_Omc_Elveflow = 12 * mu_oil * constriction_l / (mcw * mcd ** 3) * 1 / (
                1 - (0.63 * mcd / mcw))
    hydraulic_resistance_OMc_Elveflow = 12 * mu_oil * pitch / (Mcw * Mcd ** 3) * 1 / (
                1 - (0.63 * Mcd / Mcw))
    hydraulic_resistance_WMc_Elveflow = 12 * mu_water * pitch / (Mcw * Mcd ** 3) * 1 / (
                1 - (0.63 * Mcd / Mcw))


    R_Omc = hydraulic_resistance_Omc_Elveflow
    R_OMc = hydraulic_resistance_OMc_Elveflow
    R_WMc = hydraulic_resistance_WMc_Elveflow

    Q_O = Q_oil
    Q_W = Q_water

    return Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W

def generate_conduction_matrix(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W):
    r1 = R_WMc
    r2 = R_Omc
    r3 = R_OMc
    QOut = Q_O + Q_W
    number_of_nodes = 2*Nmc + 2
    A = lil_matrix((number_of_nodes,number_of_nodes))

    A[0,:3] = [-1/r3, 0, 1/r3]
    A[1,:4] = [0, -1/r1, 0, 1/r1]
    A[2,:5] = [0, 0, -1/r3-1/r2, 1/r2, 1/r3]
    A[3,:6] = [0, 0, 1/r2, -1/r1-1/r2, 0, 1/r1]
    A[4, -4:] = [-1/r3, 0, 1/r3+1/r2, -1/r2]
    A[5, -1:] = [1/r1]

    oil_conductance_vector = [-1/r3, 0, 2/r3+1/r2, -1/r2,  -1/r3]
    water_conductance_vector = [1/r1, 1/r2, -2/r1-1/r2, 0, 1/r1]

    for i in range(Nmc-2):
        A[2*i+6, 2+2*i:2+2*i+5] = oil_conductance_vector
        A[2*i+7, 3+2*i:3+2*i+5] = water_conductance_vector

    B = np.zeros([number_of_nodes])
    B[:6] = [Q_O, Q_W, Q_O, Q_W, 0, -QOut]
    A = A.tocsr() # Convert to Compressed Sparse Row format

    return A, B

def make_graphs(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W):
    conduction_matrix, answer_vector = generate_conduction_matrix(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W)
    result = spsolve(conduction_matrix, answer_vector)

    Oc_pressures = -result[2::2][::-1]
    Wc_pressures = -result[3::2][::-1]

    Oc_pressures = Oc_pressures
    Wc_pressures = Wc_pressures

    flows = -(Wc_pressures - Oc_pressures)/R_Omc
    flows = flows * 60 * 10 ** 12

    delaminating_force = Oc_pressures[0] * Mcw

    average_flow = Q_O / Nmc * 60 * 10 ** 12
    flow_difference =  (np.max(flows) - average_flow)/average_flow * 100

    print("Oil channel start and end pressure [Pa]: ", Oc_pressures[0], Oc_pressures[-1])
    print("Water channel start and end pressure [Pa]: ", Wc_pressures[0], Wc_pressures[-1])
    print("Delaminating force [N/m]", delaminating_force)
    print("Flow difference [%]", flow_difference)



    Area = (2*Mcw+mcl)*Mcl
    plt.plot(flows, label=f"(Main channel width [um]: {Mcw * 10 ** 6:.4g}, microchannel length [um]: {mcl * 10 ** 6:.4g}, Area [cm^2]: {Area * 10 ** 4:.4g}, delaminating force [N/m]: {delaminating_force:.4g})") # mm, um, cm^2

    plt.legend()
    plt.xlabel('Microchannel number')
    plt.ylabel('Flow rate: [nL/minute]')
    plt.title(f"Flow distribution for: Main channel length [mm]: {Mcl * 10 ** 3:.4g}, \n  Main channel depth [um]: {Mcd * 10 ** 6:.4g}, \n microchannel width [um]: {mcw * 10 ** 6:.4g} \n Total flow of oil [L/hour]: {Q_O * 3600 * 1000:.4g}")

def visualize_microfluidic_chip(Mcl, Mcw, mcw, mcl, Nmc, pressures=None, flows=None):
    """
    Visualizes a microfluidic chip with two vertical channels connected by n horizontal microchannels.

    Args:
        n (int): Number of microchannels connecting the two large channels.
        pressures (list, optional): List of pressures at each node, where node numbering follows:
                                     [top of left channel, ...horizontal microchannels..., bottom of right channel].
        flows (list, optional): List of flows in each horizontal microchannel. Positive values indicate flow
                                 from the left to right channel.
    """

    # Q_O = 1
    # Q_W = 9
    #
    # R_WMc = 2
    # R_Omc = 100
    #Calculate flows
    conduction_matrix, answer_vector = generate_conduction_matrix(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W)
    result = spsolve(conduction_matrix, answer_vector)

    print("Nmc = ", Nmc)

    Oc_pressures = -result[2::2][::-1]
    Wc_pressures = -result[3::2][::-1]

    # Oc_pressures = Oc_pressures
    # Wc_pressures = Wc_pressures

    flows = -(Wc_pressures - Oc_pressures) / R_Omc
    flows = flows * 60 * 10 ** 12

    # Initialize figure
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.set_xlim(-10, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")

    # Calculate normalised sizes
    max_width = 10
    max_height = 10
    width = 2 * Mcw + mcl
    Mcw_adjusted = max_width * Mcw / width
    mcl_adjusted = max_width * mcl / width
    Mcl_adjusted = max_height

    # Draw vertical channels
    left_channel = patches.Rectangle((-Mcw_adjusted-mcl_adjusted/2, 0), Mcw_adjusted, Mcl_adjusted, linewidth=2, edgecolor="black", facecolor="lightblue")
    right_channel = patches.Rectangle((mcl_adjusted/2, 0), Mcw_adjusted, Mcl_adjusted, linewidth=2, edgecolor="black", facecolor="lightblue")
    ax.add_patch(left_channel)
    ax.add_patch(right_channel)

    # Draw horizontal microchannels
    microchannel_positions = np.linspace(0.5, Mcl_adjusted-0.5, Nmc)
    for i, y in enumerate(microchannel_positions):
        ax.plot([-mcl_adjusted/2, mcl_adjusted/2], [y, y], color="blue", linewidth=1.5)
        if flows[0]:
            direction = "→" if flows[i] > 0 else "←"
            fontsize = max(8, min(15, abs(flows[i]) * 50))  # Font size proportional to flow, capped between 8 and 15
            # ax.text(0.75, y, f"{direction} {abs(flows[i]):.2f}", fontsize=fontsize, ha="center", va="center",
            #         color="darkred")
            ax.text(0.75, y, f"{direction} ", fontsize=fontsize, ha="center", va="center",
                    color="darkred")

    # Annotate pressures
    max_annotations = 10  # Set the maximum number of annotations
    step = max(1, len(microchannel_positions) // max_annotations)

    if Oc_pressures[0]:
        ax.text(-Mcl_adjusted, Mcl_adjusted, f"P_in: {Oc_pressures[-1]:.2f}", fontsize=10, ha="right", va="center",
                color="purple")
        for i, y in enumerate(microchannel_positions[::step]):
            ax.text(-Mcl_adjusted, y, f"{Oc_pressures[i * step]:.2f}", fontsize=8, ha="right", va="center",
                    color="purple")
        # ax.text(-Mcl_adjusted, 0, f"P_out: {Oc_pressures[0]:.2f}", fontsize=10, ha="right", va="center", color="purple")

    if Wc_pressures[0]:
        ax.text(Mcl_adjusted, Mcl_adjusted, f"P_in: {Wc_pressures[-1]:.2f}", fontsize=10, ha="right", va="center",
                color="purple")
        for i, y in enumerate(microchannel_positions[::step]):
            ax.text(Mcl_adjusted, y, f"{Wc_pressures[i * step]:.2f}", fontsize=8, ha="right", va="center",
                    color="purple")
        # ax.text(Mcl_adjusted, 0, f"P_out: {Wc_pressures[0]:.2f}", fontsize=10, ha="right", va="center", color="purple")

    # Title and show
    ax.set_title("Microfluidic Chip Flow and Pressure Visualization", fontsize=14)
    plt.show()

    plt.plot(flows)
    plt.show()

def make_contour_plot(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W):
    conduction_matrix, answer_vector = generate_conduction_matrix(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W)
    result = np.linalg.solve(conduction_matrix, answer_vector)
    print("QO = ", Q_O)
    print(np.sum((result[3::2] - result[2::2]) / R_Omc))

    print("Nmc = ", Nmc)

    Oc_pressures = -result[2::2][::-1]
    Wc_pressures = -result[3::2][::-1]

    Oc_pressures = Oc_pressures / 100
    Wc_pressures = Wc_pressures / 100  # Millibar

    flows = []

    for i in range(len(Oc_pressures)):
        flow = -(Wc_pressures[i] - Oc_pressures[i]) / R_Omc
        flows.append(float(flow))
        # flows.append(float(flow * 10 ** 15))

    plt.plot(flows, label=(str(Mcw)[:6], str(mcl)[:6]))

    plt.legend()
    plt.xlabel('Microchannel number')
    plt.ylabel('Flow rate')
    return flows

Mcl = 2040* 10 ** -3
Mcd = 100 * 10 ** -6  # Main channel depth
Mcw = 500 * 10 ** -6  # Main channel width
mcd = 0.3 * 10 ** -6  # Microchannel depth
mcw = 1 * 10 ** -6  # Microchannel width if mcw/mcd >= 2.89 the model breaks
mcl = 200 * 10 ** -6  # Microchannel length
pitch = 3 * 10 ** -6  # Pitch of the microchannels
constriction_ratio = 1 #

#
# Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W = define_parameters(Mcl, Mcd, Mcw, mcd, mcw, mcl, pitch, constriction_ratio)
# #
# visualize_microfluidic_chip(Mcl, Mcw, mcw, mcl, Nmc)
# make_graphs(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W)
# plt.show()
# Flow graphs:
for i in range(1, 2):
    Mcw = (0 + 500 * i) * 10 ** -6
    for j in range(1, 2):
        mcl = (0 + 200 * j) * 10 ** -6
        Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W = define_parameters(Mcl, Mcd, Mcw, mcd, mcw, mcl, pitch, constriction_ratio)
        print("Nmc = ", Nmc)
        make_graphs(Nmc, R_OMc, R_WMc, R_Omc, Q_O, Q_W)

average_flow = Q_O / Nmc * 60 * 10 ** 12
print(average_flow)
average_flows = [average_flow] * Nmc

tolerance = 0.05 * average_flow
plt.axhline(average_flow, color='red', linestyle='--', linewidth=1, label=f'Fixed Value ({average_flow})')
# Add the transparent bar
plt.fill_between(range(Nmc), average_flow - tolerance, average_flow + tolerance, color='red', alpha=0.2, label='±5% Range')



# Get the dimensions of the second monitor
monitors = get_monitors()
if len(monitors) > 1:
    second_monitor = monitors[1]  # Assuming the second monitor is at index 1
    second_monitor_x = second_monitor.x
    second_monitor_y = second_monitor.y
    second_monitor_width = second_monitor.width
    second_monitor_height = second_monitor.height
else:
    print("No second monitor detected. Using primary monitor.")
    second_monitor_x = 0
    second_monitor_y = 0
    second_monitor_width = 1920  # Default width (adjust if necessary)
    second_monitor_height = 1080  # Default height (adjust if necessary)

manager = plt.get_current_fig_manager()
manager.window.geometry(f"{second_monitor_width}x{second_monitor_height}+{second_monitor_x}+{second_monitor_y}")

plt.show()



