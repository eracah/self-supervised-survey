
# coding: utf-8

# In[17]:


import sys
from torch import nn
import torch
from torchvision.utils import make_grid
import numpy as np
import json
import gym
from gym_minigrid.register import env_list
from gym_minigrid.minigrid import Grid
from matplotlib import pyplot as plt
from gym_minigrid.wrappers import *
from PIL import Image
from torchvision.transforms import Compose,Normalize,Resize,ToTensor, Grayscale
import numpy as np
from copy import deepcopy
from functools import partial
import math
from pathlib import Path
from collections import namedtuple


# In[28]:


def discretize_heading(heading):
    """takes 2D unit vector of heading and bins it to 4 directions right,down,left,up
       0: right
       1: down
       2: left
       3: up """
    
    minigrid_headings = [[1, 0],[ 0, -1],[-1 , 0],[0, 1]]
    direction = minigrid_headings.index(list(heading))
    return direction


# In[19]:


def setup_env(env_name):
    env = gym.make(env_name)
    if "MiniGrid" in env_name:
        action_space = range(3)
    else:
        action_space = list(range(env.action_space.n))
    num_actions = len(action_space)
    return env, action_space


# In[20]:


def classification_acc(y_logits,y_true):
    y_guess = torch.argmax(y_logits,dim=1)
    acc = (float(torch.sum(torch.eq(y_true,y_guess)).data) / y_true.size(0))*100
    return acc


# In[21]:



def convert_frame(obs, resize_to=(84,84),to_tensor=False):
    pil_image = Image.fromarray(obs, 'RGB')
    
    transforms = [Resize(resize_to)] if resize_to != (-1,-1) else []
    if to_tensor:
        transforms.extend([ToTensor(),Normalize([0.5,0.5,0.5],[0.5,0.5,0.5])])
    transforms = Compose(transforms)
    frame = transforms(pil_image)
    if to_tensor:
        DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
        frame= frame.to(DEVICE)
    else:
        frame = np.asarray(frame)


    
    return frame

def convert_frames(frames,resize_to=(64,64),to_tensor=False):
    convert = partial(convert_frame,resize_to=resize_to,to_tensor=to_tensor)
    return torch.stack([convert(frame) for frame in frames])
        


# In[24]:


def get_trans_tuple(with_agent_pos=False, with_agent_heading=False):
        tuple_fields = ['x0','x1','a', 'r', 'done']
        
        if with_agent_pos:
            tuple_fields.extend(["x0_coords","x1_coords"])
        if with_agent_heading:
            tuple_fields.extend(["x0_heading","x1_heading"])
        
        Transition = namedtuple("Transition",tuple(tuple_fields))
        return Transition
        


# In[26]:


def collect_one_data_point(env=gym.make("MiniGrid-Empty-6x6-v0"),
                     policy=lambda x0: np.random.choice(3),
                     convert_fxn=convert_frame,**kwargs):
    x0 = env.render("rgb_array")
    action = policy(convert_fxn(x0,to_tensor=True))
    x0 = convert_fxn(x0,to_tensor=False)
    
    with_agent_pos = kwargs["with_agent_pos"] if "with_agent_pos" in kwargs else False
    with_agent_heading = kwargs["with_agent_heading"] if "with_agent_heading" in kwargs else False
    
    Transition = get_trans_tuple(with_agent_pos, with_agent_heading)
    
    if with_agent_pos:
        x0_coords = env.agent_pos
    if with_agent_heading:
        x0_heading = discretize_heading(env.get_dir_vec())
    
    
    _, reward, done, _ = env.step(action)
    x1 = convert_fxn(env.render("rgb_array"))
    trans_list =  [x0,x1,action,reward,done]
    
    if with_agent_pos:
        x1_coords = env.agent_pos
        trans_list.extend([x0_coords, x1_coords])
    if with_agent_heading:
        x1_heading = discretize_heading(env.get_dir_vec())
        trans_list.extend([x0_heading, x1_heading])
    return Transition(*trans_list)

def rollout_iterator(env=gym.make("MiniGrid-Empty-6x6-v0"),
                     policy=lambda x0: np.random.choice(3),
                     convert_fxn=convert_frame, **kwargs):
    _ = env.reset()
    done = False
    while not done:
        transition = collect_one_data_point(env, policy, convert_fxn,
                                                      **kwargs)
        yield transition


# In[34]:


def mkstr(key,args={}):
    d = args.__dict__
    return "=".join([key,str(d[key])])


# In[35]:


def initialize_weights(self):
    # Official init from torch repo.
    for m in self.modules():
        if isinstance(m, nn.Conv2d):
            nn.init.kaiming_normal_(m.weight.data)
        elif isinstance(m, nn.BatchNorm2d):
            m.weight.data.fill_(1)
            m.bias.data.zero_()
        elif isinstance(m, nn.Linear):
            m.bias.data.zero_()


# In[36]:


def write_ims(index,rows,ims,name, iter_):
    num_ims = rows**2
    ims_grid = make_grid((ims.data[index] + 1) / 2, rows)
    writer.add_image(name, ims_grid, iter_)
    


# In[37]:


def write_to_config_file(dict_,log_dir):
    config_file_path = Path(log_dir) / "config.json"
    dict_string = json.dumps(dict_) + "\n"
    with open(config_file_path, "w") as f:
        f.write(dict_string)
    


# In[38]:


def save_incorrect_examples(y,action_guess,x0,x1,iter_):
    wrong_actions = y[torch.ne(action_guess,y)].long()
    num_wrong = wrong_actions.size(0)
    right_actions = y[torch.eq(action_guess,y)].long()
    num_right = right_actions.size(0)
    
    if iter_ % 50 == 0:
        try:
            write_ims(ims=x0,index=wrong_actions,rows=int(np.ceil(np.sqrt(num_wrong))),name=mode +"/debug/x0_wrong", iter_=iter_)
            write_ims(ims=x1,index=wrong_actions,rows=int(np.ceil(np.sqrt(num_wrong))),name=mode +"/debug/x1_wrong", iter_=iter_)
        except:
            print("Num wrong and right: ",num_wrong,num_right)


# In[39]:


def plot_test(x0s,x1s,ys,rs, label_list):
    def plot(x0,x1,y,i):
        from matplotlib import pyplot as plt
        get_ipython().run_line_magic('matplotlib', 'inline')
        plt.figure(i)
        plt.clf()
        sp1 = plt.subplot(1,2,1)
        sp1.imshow(x0[0])
        sp2 = plt.subplot(1,2,2)
        sp2.imshow(x1[0])
        plt.title(label_list[y])
    if len(x0s.size()) == 3:
        plot(x0s,x1s,ys,i=1)
    else:
        for i in range(x0s.size()[0]):
            plot(x0s[i],x1s[i],ys[i],i)
    plt.show()


# In[40]:


def do_k_episodes(convert_fxn,env,policy,k=1,epsilon=0.1,):
    rewards = []
    with torch.no_grad():
        for ep in range(k):
            done = False
            env.reset()
            cum_reward = 0
            while not done:
                _,_,_,reward, done = collect_one_data_point(convert_fxn=convert_fxn,
                                                            env=env,
                                                            policy=policy)
                cum_reward += float(reward)
            rewards.append(cum_reward)
        return np.mean(rewards), rewards


# In[ ]:


#directions = [[1, 0],[ 0, -1],[-1 , 0],[0, 1]]

# ind_to_str = dict(zip(range(4),["right","down","left","up"]))

# env = gym.make("MiniGrid-Empty-6x6-v0")

# _=env.reset()
# #print(env.get_dir_vec())
# for i in range(4):
#     direc = list(env.get_dir_vec())
#     direc_label = dirs.index(direc)
#     print(direc,direc_label, ind_to_str[direc_label])
#     _ = env.step(0)


