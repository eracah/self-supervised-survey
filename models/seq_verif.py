#!/usr/bin/env python
# coding: utf-8

# In[1]:


import torch
from torch import nn
import torch.functional as F

from models.base_encoder import Encoder
from utils import classification_acc
import numpy as np

class InOrderBinaryClassifier(nn.Module):
    def __init__(self,in_ch, h_ch=256):
        super(InOrderBinaryClassifier,self).__init__()
        self.predictor = nn.Sequential(
            nn.Linear(in_features=in_ch,out_features=h_ch),
            nn.ReLU(),
            nn.Linear(in_features=h_ch,out_features=2)
        )
    def forward(self,x):
        return self.predictor(x)
        

class ShuffleNLearn(nn.Module):
    def __init__(self,num_frames=3, in_ch=3, im_wh=(64,64), h_ch=32, embed_len=32, batch_norm=False, num_actions=3, **kwargs):
        super(ShuffleNLearn,self).__init__()
        self.encoder = Encoder(in_ch=in_ch, im_wh=im_wh, h_ch=h_ch, embed_len=embed_len, batch_norm=batch_norm)
        self.bin_clsf = InOrderBinaryClassifier(in_ch=num_frames*self.encoder.embed_len)
    
    def forward(self,xs):
        f = torch.cat([self.encoder(x) for x in xs])
        return self.bin_clsf(f)
    
    def shuffle(self,xs):
        a,b,c,d,e = [xs[:,i] for i in range(5)]
        bcd = copy.deepcopy(torch.cat(b,c,d))
        bad = copy.deepcopy(torch.cat(b,a,d))
        bed = copy.deepcopy(torch.cat(b,e,d))

        
    def loss_acc(self, trans):
        xs = copy.deepcopy(trans.xs)
        x_shuff, true = self.shuffle(xs)
        pred = self.forward(x_shuff)
        acc = classification_acc(logits=pred,true=true)
        loss = nn.CrossEntropyLoss()(pred,true)
        return loss, acc
