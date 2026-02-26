#!/bin/bash
#SBATCH --partition=hpg-b200
#SBATCH --gpus=8
#SBATCH --nodes=1         
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=112
#SBATCH --mem=1000GB      
#SBATCH --time=336:00:00
#SBATCH --job-name=test-b200
#SBATCH --error=logs/sbatch/test-b200-%j.err # Use date-based directory
#SBATCH --output=logs/sbatch/test-b200-%j.log # Use date-based directory
#SBATCH --mail-type=END,FAIL,TIME_LIMIT,START
#SBATCH --mail-user=ryansunhanchi@gmail.com
#SBATCH --exclusive

sleep 14d 