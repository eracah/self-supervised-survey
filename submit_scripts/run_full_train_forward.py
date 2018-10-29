#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

games = ["Pitfall-v0", "PrivateEye-v0"] 
encoders = ["inv_model", "vae", "rand_cnn"]
lrs = [0.1,0.01, 0.001]
main_file = "main.py"
mode= "train_forward"
seed = 5
for game in games:
    for lr in lrs:
        for enc in encoders:
            args = ["sbatch", "./submit_scripts/run_gpu.sl","%s --model_name %s --env_name %s --mode %s"%(main_file,enc,game,mode),"--tr_size %i --val_size %i --batch_size %i"%(10000,1000,64), "--lr %f"%(lr),"--seed %i"%(seed)]
            print(" ".join(args))
            subprocess.run(args)
        

