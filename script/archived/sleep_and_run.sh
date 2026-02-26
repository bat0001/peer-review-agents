#!/bin/bash

# Script to wait for current job to finish then start new experiment
# Usage: ./script/sleep_and_run.sh

echo "Starting sleep script at $(date)"
echo "Will wait 2 hours before starting experiment..."

# Sleep for 2 hours (7200 seconds)
# You can adjust this time based on when your current job finishes
sleep 7200

echo "Sleep finished at $(date)"
echo "Starting experiment..."


# Run your experiment here
# torchrun --nproc_per_node=2 train.py --config configs/gec_shared.yaml > output_gec_shared_16a2_1.txt 2>&1
torchrun --nproc_per_node=2 train.py --config configs/gec_shared.yaml > output_gec_shared_16a1_1.txt 2>&1

echo "Experiment completed at $(date)" 