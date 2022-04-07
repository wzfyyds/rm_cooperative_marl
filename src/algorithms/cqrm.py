import numpy as np
import random, time

from src.tester.tester import Tester
from src.Environments.load_env import *
from src.Agent.cqrm_agent import CentralizedAgent
import matplotlib.pyplot as plt


def run_qlearning_task(epsilon,
                       tester,
                       centralized_agent,
                       show_print=False):
    """
    This code runs one q-learning episode. q-functions, and accumulated reward values of agents
    are updated accordingly. If the appropriate number of steps have elapsed, this function will
    additionally run a test episode.

    Parameters
    ----------
    epsilon : float
        Numerical value in (0,1) representing likelihood of choosing a random action.
    tester : Tester object
        Object containing necessary information for current experiment.
    centralized_agent : CentralizedAgent object
        Centralized agent object representing the entire team of agents.
    show_print : bool
        Optional flag indicating whether or not to print output statements to terminal.
    """
    # Initializing parameters and the game
    learning_params = tester.learning_params
    testing_params = tester.testing_params

    num_agents = centralized_agent.num_agents

    centralized_agent.reset_state()
    centralized_agent.initialize_reward_machine()

    num_steps = learning_params.max_timesteps_per_task

    env = load_testing_env(tester)  # in Centralized-QRM, training_env=testing_env

    for t in range(num_steps):
        # Update step count
        tester.add_step()

        # Perform a q-learning step.
        if not (centralized_agent.is_task_complete):
            current_u = centralized_agent.u
            s, a = centralized_agent.get_next_action(epsilon, learning_params)
            r, l, s_new = env.environment_step(s, a)
            # a = np.copy(env.last_action) # due to MDP slip
            centralized_agent.update_agent(s_new, a, r, l, learning_params)

            # update Q-functions of other RM states
            for u in centralized_agent.rm.U:
                if not (u == current_u) and not (u in centralized_agent.rm.T):
                    l = env.get_mdp_label(s, s_new, u)
                    r = 0
                    u_temp = u
                    u2 = u
                    for e in l:
                        # Get the new reward machine state and the reward of this step
                        u2 = centralized_agent.rm.get_next_state(u_temp, e)
                        r = r + centralized_agent.rm.get_reward(u_temp, u2)
                        # Update the reward machine state
                        u_temp = u2
                    centralized_agent.update_q_function(s, s_new, u, u2, a, r, learning_params)

        # If enough steps have elapsed, test and save the performance of the agents.
        if testing_params.test and tester.get_current_step() % testing_params.test_freq == 0:
            t_init = time.time()
            step = tester.get_current_step()

            # Need to create a copy of the agent for testing. If we pass the agent directly
            # mid-episode to the test function, the test will reset the world-state and reward machine 
            # state before the training episode has been completed.
            centralized_agent_copy = CentralizedAgent(centralized_agent.rm_file, centralized_agent.s_i,
                                                      centralized_agent.num_states, centralized_agent.actions)
            centralized_agent_copy.q = centralized_agent.q  # Pass the q function directly. Note that the q-function will be updated during testing.

            # Run a test of the performance of the agents
            testing_reward, trajectory, testing_steps = run_centralized_qrm_test(centralized_agent_copy,
                                                                                 tester,
                                                                                 learning_params,
                                                                                 testing_params,
                                                                                 show_print=show_print)

            if 0 not in tester.results.keys():
                tester.results[0] = {}
            if step not in tester.results[0]:
                tester.results[0][step] = []
            tester.results[0][step].append(testing_reward)

            # Save the testing trace
            if 'trajectories' not in tester.results.keys():
                tester.results['trajectories'] = {}
            if step not in tester.results['trajectories']:
                tester.results['trajectories'][step] = []
            tester.results['trajectories'][step].append(trajectory)

            # Save how many steps it took to complete the task
            if 'testing_steps' not in tester.results.keys():
                tester.results['testing_steps'] = {}
            if step not in tester.results['testing_steps']:
                tester.results['testing_steps'][step] = []
            tester.results['testing_steps'][step].append(testing_steps)

            if len(tester.steps) == 0 or tester.steps[-1] < step:
                tester.steps.append(step)

        # If the agents has completed its task, reset it to its initial state.
        if centralized_agent.is_task_complete:
            centralized_agent.reset_state()
            centralized_agent.initialize_reward_machine()

            # Make sure we've run at least the minimum number of training steps before breaking the loop
            if tester.stop_task(t):
                break

        # checking the steps time-out
        if tester.stop_learning():
            break


def run_centralized_qrm_test(centralized_agent,
                             tester,
                             learning_params,
                             testing_params,
                             show_print=True):
    """
    Run a test of the q-learning with reward machine method with the current q-function. 

    Parameters
    ----------
    centralized_agent : CentralizedAgent object
        Centralized agent object representing the entire team of agents.
    learning_params : LearningParameters object
        Object storing parameters to be used in learning.
    Testing_params : TestingParameters object
        Object storing parameters to be used in testing.

    Ouputs
    ------
    testing_reard : float
        Reward achieved by agent during this test episode.
    trajectory : list
        List of dictionaries containing information on current step of test.
    step : int
        Number of testing steps required to complete the task.
    """
    num_agents = centralized_agent.num_agents
    testing_env = load_testing_env(tester)

    centralized_agent.reset_state()
    centralized_agent.initialize_reward_machine()

    testing_reward = 0
    trajectory = []
    step = 0

    # Starting interaction with the environment
    for t in range(testing_params.num_steps):
        step = step + 1

        # Perform a step
        s, a = centralized_agent.get_next_action(-1.0, learning_params)
        r, l, s_team_next = testing_env.environment_step(s, a)

        # trajectory.append({'s' : np.array(s_team, dtype=int), 'a' : np.array(a_team, dtype=int), 'u': int(testing_env.u)})

        testing_reward = testing_reward + r
        # a = np.copy(testing_env.last_action)
        centralized_agent.update_agent(s_team_next, a, r, l, learning_params, update_q_function=False)
        # if centralized_agent.is_task_complete:
        if testing_env.reward_machine.is_terminal_state(testing_env.u):
            break

    if show_print:
        print('Reward of {} achieved in {} steps. Current step: {} of {}'.format(testing_reward, step,
                                                                                 tester.current_step,
                                                                                 tester.total_steps))
    return testing_reward, trajectory, step


def run_cqrm_experiment(tester,
                        num_times,
                        show_print=False):
    """
    Run the entire q-learning with reward machines experiment a number of times specified by num_times.

    Inputs
    ------
    tester : Tester object
        Test object holding true reward machine and all information relating
        to the particular tasks, world, learning parameters, and experimental results.
    num_agents : int
        Number of agents in this experiment.
    num_times : int
        Number of times to run the entire experiment (restarting training from scratch).
    show_print : bool
        Flag indicating whether or not to output text to the terminal.
    """

    learning_params = tester.learning_params
    # num_agents = tester.num_agents

    for t in range(num_times):
        start_time = time.time()
        # Reseting default step values
        tester.restart()

        rm_test_file = tester.rm_test_file

        # testing_env = MultiAgentGridWorldEnv(rm_test_file, num_agents, tester.env_settings)
        testing_env = load_testing_env(tester)

        s_i = testing_env.get_initial_team_state()
        actions = testing_env.actions

        centralized_agent = CentralizedAgent(rm_test_file, s_i, testing_env.num_states, actions)

        num_episodes = 0

        # Task loop
        epsilon = learning_params.initial_epsilon

        while not tester.stop_learning():
            num_episodes += 1

            # epsilon = epsilon*0.99

            run_qlearning_task(epsilon,
                               tester,
                               centralized_agent,
                               show_print=show_print)

        # Backing up the results
        end_time = time.time()
        print('Finished iteration ', t)
        unit_steps = 10000
        ave_time = (end_time - start_time) * unit_steps / tester.total_steps
        print('Running time %.2fs per %d steps' % (ave_time, unit_steps))

    # plot_multi_agent_results(tester)


def plot_multi_agent_results(tester):
    """
    Plot the results stored in tester.results for each of the agents.
    """

    prc_25 = list()
    prc_50 = list()
    prc_75 = list()

    # Buffers for plots
    current_step = list()
    current_25 = list()
    current_50 = list()
    current_75 = list()
    steps = list()

    plot_dict = tester.results['testing_steps']

    for step in plot_dict.keys():
        if len(current_step) < 10:
            current_25.append(np.percentile(np.array(plot_dict[step]), 25))
            current_50.append(np.percentile(np.array(plot_dict[step]), 50))
            current_75.append(np.percentile(np.array(plot_dict[step]), 75))
            current_step.append(sum(plot_dict[step]) / len(plot_dict[step]))
        else:
            current_step.pop(0)
            current_25.pop(0)
            current_50.pop(0)
            current_75.pop(0)
            current_25.append(np.percentile(np.array(plot_dict[step]), 25))
            current_50.append(np.percentile(np.array(plot_dict[step]), 50))
            current_75.append(np.percentile(np.array(plot_dict[step]), 75))
            current_step.append(sum(plot_dict[step]) / len(plot_dict[step]))

        prc_25.append(sum(current_25) / len(current_25))
        prc_50.append(sum(current_50) / len(current_50))
        prc_75.append(sum(current_75) / len(current_75))
        steps.append(step)

    plt.plot(steps, prc_25, alpha=0)
    plt.plot(steps, prc_50, color='red')
    plt.plot(steps, prc_75, alpha=0)
    plt.grid()
    plt.fill_between(steps, prc_50, prc_25, color='red', alpha=0.25)
    plt.fill_between(steps, prc_50, prc_75, color='red', alpha=0.25)
    plt.ylabel('Testing Steps to Task Completion', fontsize=15)
    plt.xlabel('Training Steps', fontsize=15)
    plt.locator_params(axis='x', nbins=5)

    plt.show()
