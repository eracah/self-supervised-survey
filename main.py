
# coding: utf-8

# In[1]:


import random
from models.setup import setup_model
from data.utils import setup_env
import argparse
from evaluations.utils import classification_acc
import argparse
import sys
import copy
import torch
from functools import partial
from torch import nn
from torch.optim import Adam, RMSprop
import numpy as np
from pathlib import Path
import time
from data.tr_val_test_splitter import setup_tr_val_test
from comet_ml import Experiment
import os
from utils import get_child_dir, get_hyp_str


# In[2]:


model_names = ['inv_model', 'vae', 'raw_pixel', 'lin_proj', 'rand_cnn']
model_names = model_names + ["forward_" + model_name for model_name in model_names ]

def setup_args():
    test_notebook= True if "ipykernel_launcher" in sys.argv[0] else False
    tmp_argv = copy.deepcopy(sys.argv)
    if test_notebook:
        sys.argv = [""]
    
    parser = argparse.ArgumentParser()

    parser.add_argument("--lr", type=float, default=0.00025)
    parser.add_argument("--env_name",type=str, default="originalGame-v0"),
    parser.add_argument("--resize_to",type=int, nargs=2, default=[224, 224])
    parser.add_argument("--batch_size",type=int,default=32)
    parser.add_argument("--epochs",type=int,default=10000)
    parser.add_argument("--hidden_width",type=int,default=32)
    parser.add_argument("--embed_len",type=int,default=32)
    parser.add_argument("--seed",type=int,default=4)
    parser.add_argument("--model_name",choices=model_names,default="inv_model")
    parser.add_argument("--beta",type=float,default=2.0)
    parser.add_argument("--tr_size",type=int,default=60000)
    parser.add_argument("--val_size",type=int,default=10000)
    parser.add_argument("--test_size",type=int,default=10000)
    parser.add_argument('--mode', choices=['train','train_forward', 'eval', 'test'], default="train")
    parser.add_argument("--buckets",type=int,default=20)
    parser.add_argument("--label_name",type=str,default="y_coord")
    parser.add_argument("--frames_per_trans",type=int,default=2)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--model_type",type=str,default="classifier")
    #parser.add_argument("--eval_mode",type=str,default="infer")
    args = parser.parse_args()
    args.resize_to = tuple(args.resize_to)
    sys.argv = tmp_argv
    args.device = "cuda" if torch.cuda.is_available() else "cpu"
    if test_notebook:
        args.test_notebook=True
        args.workers=1
        args.batch_size =2 
        args.tr_size = 4
        args.test_size=4
        args.val_size = 4
        args.resize_to = (64,64)
        args.mode="test"
        args.model_name = "forward_inv_model"
    else:
        args.test_notebook = False

    return args


# In[2]:


# In[3]:


class Trainer(object):
    def __init__(self, model, args, experiment):
        self.model = model
        self.args = args
        self.model_name = self.args.model_name
        self.experiment = experiment
        
        #self.opt_template = partial(Adam,params=self.model.parameters())
        
        #self.opt = None
        self.opt = Adam(params=self.model.parameters(),lr=args.lr)
        self.epoch=0
        self.max_epochs = 10000

    def one_iter(self, trans, update_weights=True):
        if update_weights:
            self.opt.zero_grad()
        loss, acc = self.model.loss_acc(trans)
        if update_weights:
            loss.backward()
            self.opt.step()
        return float(loss.data),acc
    
    def one_epoch(self, buffer,mode="train"):
        update_weights = True if mode=="train" else False
        losses, accs = [], []
        for trans in buffer:
            loss,acc = self.one_iter(trans,update_weights=update_weights)
            losses.append(loss)
            accs.append(acc)
        
        if mode == "train":
            print("Epoch %i: "%self.epoch)
        print("\t%s"%mode)
        if args.mode == "eval" or args.mode == "test":
            print("\t %s"%(args.label_name))
        
        avg_loss = np.mean(losses)
        self.experiment.log_metric(avg_loss, mode + "_loss", step=self.epoch)
        print("\t\tLoss: %8.4f"%(avg_loss))
        if None in accs:
            avg_acc =None
        else:
            avg_acc = np.mean(accs)
            self.experiment.log_metric(avg_acc, mode + "_acc", step=self.epoch)
            print("\t\tAccuracy: %9.3f%%"%(100*avg_acc))
        return avg_loss, avg_acc
    
    def test(self,test_set):
        self.model.eval()
        test_loss, test_acc = self.one_epoch(test_set,mode="test")
        self.experiment.log_metric("test_acc",test_acc)
        return test_acc
        
    def train(self, tr_buf, val_buf, model_dir):
        state_dict = self.model.state_dict()
        val_acc = -np.inf
        best_val_loss = np.inf
        while self.epoch < self.max_epochs:
            self.epoch+=1
            self.model.train()
            self.experiment.train()
            tr_loss,tr_acc = self.one_epoch(tr_buf,mode="train")
            state_dict = self.model.encoder.state_dict() if self.args.mode == "train" else self.model.state_dict()
            torch.save(state_dict, model_dir / "cur_model.pt")
            
            self.model.eval()
            self.experiment.validate()
            val_loss, val_acc = self.one_epoch(val_buf,mode="val")
            
            if self.epoch == 1 or val_loss < best_val_loss:
                best_val_loss = copy.deepcopy(val_loss)
                old = [f for f in model_dir.glob("best_model*")]
                for f in old:
                    os.remove(str(f))
                #print("hey")
                save_path = model_dir / Path(("best_model_%f.pt"%best_val_loss).rstrip('0').rstrip('.'))
                #print(save_path)
                torch.save(state_dict,save_path )




def setup_exp(args):
    exp_name = ("nb_" if args.test_notebook else "") + "_".join([args.mode, args.model_name, get_hyp_str(args)])
    experiment = Experiment(api_key="kH9YI2iv3Ks9Hva5tyPW9FAbx",
                            project_name="self-supervised-survey",
                            workspace="eracah")
    experiment.set_name(exp_name)
    experiment.log_multiple_params(args.__dict__)
    return experiment



def setup_dir(args,exp_id,basename=".models"):
    dir_ = Path(basename) / get_child_dir(args,mode=args.mode) / Path(exp_id)
    dir_.mkdir(exist_ok=True,parents=True)
    return dir_


# In[3]:


# In[4]:


if __name__ == "__main__":
    args = setup_args()
    

    experiment = setup_exp(args)
    env = setup_env(args)

    print("starting to load buffers")
    bufs = setup_tr_val_test(args)
    

    # setup models before dirs because some args get changed in this fxn
    model = setup_model(args, env)
    

    model_dir = setup_dir(basename=".models",args=args,exp_id=experiment.id)
    print(model_dir)

    ims_dir = setup_dir(basename=".images",args=args,exp_id=experiment.id)
    
    #update params
    experiment.log_multiple_params(args.__dict__)
    
    trainer = Trainer(model, args, experiment)
    if args.mode == "test":
        trainer.test(bufs[0])
    else:
        trainer.train(*bufs,model_dir)

