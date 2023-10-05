'''DLP DQN Lab'''
__author__ = 'chengscott'
__copyright__ = 'Copyright 2020, NCTU CGI Lab'
import argparse
from collections import deque, namedtuple
import itertools
import random
import time

import gym
import numpy as np
import torch
import torch.nn as nn
from torch.utils.tensorboard import SummaryWriter
from atari_wrappers import wrap_deepmind, make_atari

# Transition = namedtuple('Transition', ('state', 'action', 'reward', 'next_state', 'done'))
class ReplayMemory(object):
    __slots__ = ['buffer']

    ## TODO ##
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, state, action, reward, next_state, done):
        """Saves a transition"""
        self.buffer.append(tuple([tuple(state), tuple(action), tuple(reward), tuple(next_state), tuple(done)]))

    def sample(self, batch_size):
        """Sample a batch of transitions"""
        transitions = random.sample(self.buffer, batch_size)
        # print(transitions)
        return (torch.tensor(x, dtype=torch.float, device='cuda')
                for x in zip(*transitions))

    def __len__(self):
        return len(self.buffer)


class Net(nn.Module):
    def __init__(self, num_classes=4, init_weights=True):
        super(Net, self).__init__()

        self.cnn = nn.Sequential(nn.Conv2d(4, 32, kernel_size=8, stride=4),
                                        nn.ReLU(True),
                                        nn.Conv2d(32, 64, kernel_size=4, stride=2),
                                        nn.ReLU(True),
                                        nn.Conv2d(64, 64, kernel_size=3, stride=1),
                                 nn.ReLU(True)
                                        )
                                        
        self.classifier = nn.Sequential(nn.Linear(7*7*64, 512),
                                        nn.ReLU(True),
                                        nn.Linear(512, num_classes)
                                        )
        if init_weights:
            self._initialize_weights()

    def forward(self, x):
        x = x.float() / 255.
        x = self.cnn(x)
        x = torch.flatten(x, start_dim=1)
        x = self.classifier(x)
        return x

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0.0)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.constant_(m.weight, 1.0)
                nn.init.constant_(m.bias, 0.0)
            elif isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                nn.init.constant_(m.bias, 0.0)


class DQN:
    def __init__(self, args):
        self._behavior_net = Net().to(args.device)
        self._target_net = Net().to(args.device)
        # initialize target network
        self._target_net.load_state_dict(self._behavior_net.state_dict())
        self._target_net.eval()
        self._optimizer = torch.optim.Adam(self._behavior_net.parameters(), lr=args.lr, eps=1.5e-4)

        ## TODO ##
        """Initialize replay buffer"""
        self._memory = ReplayMemory(capacity=args.capacity)

        ## config ##
        self.device = args.device
        self.batch_size = args.batch_size
        self.gamma = args.gamma
        self.freq = args.freq
        self.target_freq = args.target_freq

    def select_action(self, state, epsilon, action_space):
        '''epsilon-greedy based on behavior network'''
        ## TODO ##
        if random.random() <= epsilon:
            action = action_space.sample()
        else:
            with torch.no_grad():
                state = torch.tensor(state, device=self.device)
                state = state.permute(2, 0, 1)
                state = state.view((1, 4, 84, 84))
                outputs = self._behavior_net(state)
                _, action = torch.max(outputs, 1)
                action = action.item()

        # if epsilon > args.epsilon_end \
        #     and self.step > self.args.observe_steps:
        #     old_e = self.epsilon
        #     interval = self.args.epsilon_start - self.args.epsilon_end
        #     self.epsilon -= interval / float(self.args.explore_steps)
        #     # print('epsilon: ', old_e, ' -> ', self.epsilon)

        return action

    def append(self, state, action, reward, next_state, done):
        ## TODO ##
        """Push a transition into replay buffer"""
        self._memory.push(state, [action], [reward / 10], next_state, [int(done)])

    def update(self, total_steps):
        if total_steps % self.freq == 0:
            self._update_behavior_network(self.gamma)
        if total_steps % self.target_freq == 0:
            self._update_target_network()

    def _update_behavior_network(self, gamma):
        # sample a minibatch of transitions
        state, action, reward, next_state, done = self._memory.sample(self.batch_size)
        state = state.permute(0, 3, 1, 2)
        next_state = next_state.permute(0, 3, 1, 2)
        # print(state.shape)
        ## TODO ##
        q_value = self._behavior_net(state).gather(1, action.long())
        with torch.no_grad():
           q_next = torch.max(self._target_net(next_state), 1)[0].view(-1,1)
        #    print(f'q_next= {q_next.shape}')
           q_target = reward + q_next * gamma * (1.0 - done)
        criterion = nn.MSELoss()
        loss = criterion(q_value, q_target)
        # optimize
        self._optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self._behavior_net.parameters(), 5)
        self._optimizer.step()

    def _update_target_network(self):
        '''update target network by copying from behavior network'''
        ## TODO ##
        self._target_net.load_state_dict(self._behavior_net.state_dict())

    def save(self, model_path, checkpoint=False):
        if checkpoint:
            torch.save({
                'behavior_net': self._behavior_net.state_dict(),
                'target_net': self._target_net.state_dict(),
                'optimizer': self._optimizer.state_dict(),
            }, model_path)
        else:
            torch.save({
                'behavior_net': self._behavior_net.state_dict(),
            }, model_path)

    def load(self, model_path, checkpoint=False):
        model = torch.load(model_path)
        self._behavior_net.load_state_dict(model['behavior_net'])
        if checkpoint:
            self._target_net.load_state_dict(model['target_net'])
            self._optimizer.load_state_dict(model['optimizer'])

def train(args, agent, writer):
    e_reward = 0
    print('Start Training')
    env_raw = make_atari('BreakoutNoFrameskip-v4')
    env = wrap_deepmind(env_raw, episode_life=True, clip_rewards=True, frame_stack=True)
    action_space = env.action_space
    total_steps, epsilon = 0, 1.0
    ewma_reward = 0

    for episode in range(args.episode):
        if e_reward > 350:
            break
        if episode >= 3330:
            break
        total_reward = 0
        state = env.reset()
        
        state, reward, done, _ = env.step(1) # fire first !!!
        # print(f'state.shape = {len(state[0][0])}')
        for t in itertools.count(start=1):
            if total_steps < args.warmup:
                action = action_space.sample()
            else:
                # select action
                action = agent.select_action(state, epsilon, action_space)
                # decay epsilon
                epsilon -= (1 - args.eps_min) / args.eps_decay
                epsilon = max(epsilon, args.eps_min)

            # execute action
            next_state, reward, done, _ = env.step(action)
            
            ## TODO ##
            # store transition
            agent.append(state, action, reward, next_state, done)
            state = next_state
            if total_steps >= args.warmup:
                agent.update(total_steps)

            total_reward += reward

            if total_steps % args.eval_freq == 0:
                """You can write another evaluate function, or just call the test function."""
                e_reward = test(args, agent, writer)
                agent.save(args.model + "dqn_" + str(total_steps) + ".pt")

            total_steps += 1
            if done:
                ewma_reward = 0.05 * total_reward + (1 - 0.05) * ewma_reward
                writer.add_scalar('Train/Episode Reward', total_reward, episode)
                writer.add_scalar('Train/Ewma Reward', ewma_reward, episode)
                with open("record.txt", 'a') as r:
                    r.write('Step: {}\tEpisode: {}\tLength: {:3d}\tTotal reward: {:.2f}\tEwma reward: {:.2f}\tEpsilon: {:.3f}\n'
                        .format(total_steps, episode, t, total_reward, ewma_reward, epsilon))
                print('Step: {}\tEpisode: {}\tLength: {:3d}\tTotal reward: {:.2f}\tEwma reward: {:.2f}\tEpsilon: {:.3f}'
                        .format(total_steps, episode, t, total_reward, ewma_reward, epsilon))
                break
    env.close()


def test(args, agent, writer):
    print('Start Testing')
    env_raw = make_atari('BreakoutNoFrameskip-v4')
    env = wrap_deepmind(env_raw, episode_life=False, clip_rewards=False, frame_stack=True)
    action_space = env.action_space
    e_rewards = []
    
    for i in range(args.test_episode):
        state = env.reset()
        # print(f'test state shape = {state.shape}')
        e_reward = 0
        done = False

        while not done:
            time.sleep(0.01)
            env.render()
            action = agent.select_action(state, args.test_epsilon, action_space)
            state, reward, done, _ = env.step(action)
            e_reward += reward

        print('episode {}: {:.2f}'.format(i+1, e_reward))
        e_rewards.append(e_reward)
        return e_reward
    env.close()
    print('Average Reward: {:.2f}'.format(float(sum(e_rewards)) / float(args.test_episode)))


def main():
    ## arguments ##
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-d', '--device', default='cuda')
    parser.add_argument('-m', '--model', default='ckpt2/')
    parser.add_argument('--logdir', default='log/dqnbreak')
    # train
    parser.add_argument('--warmup', default=20000, type=int)
    parser.add_argument('--episode', default=200000, type=int)
    parser.add_argument('--capacity', default=100000, type=int)
    parser.add_argument('--batch_size', default=128, type=int)
    parser.add_argument('--lr', default=0.0000625, type=float)
    parser.add_argument('--eps_decay', default=1000000, type=float)
    parser.add_argument('--eps_min', default=0.1, type=float)
    parser.add_argument('--gamma', default=.99, type=float)
    parser.add_argument('--freq', default=4, type=int)
    parser.add_argument('--target_freq', default=10000, type=int)
    parser.add_argument('--eval_freq', default=200000, type=int)
    # test
    parser.add_argument('--test_only', action='store_true')
    parser.add_argument('-tmp', '--test_model_path', default='ckpt/dqn_1000000.pt')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--test_episode', default=10, type=int)
    parser.add_argument('--seed', default=20230422, type=int)
    parser.add_argument('--test_epsilon', default=0.01, type=float)
    args = parser.parse_args()

    ## main ##
    agent = DQN(args)
    writer = SummaryWriter(args.logdir)
    if args.test_only:
        agent.load(args.test_model_path)
        test(args, agent, writer)
    else:
        # agent.load('ckpt/dqn_200000.pt')
        train(args, agent, writer)
        


if __name__ == '__main__':
    main()
