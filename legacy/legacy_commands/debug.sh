# export VSCODE_DEBUG=1
export CUDA_VISIBLE_DEVICES=0,1
torchrun --nproc_per_node=2 train_gpt2.py train=true --config-name mode &> output.log
# python train_gpt2.py train=true --config-name mod

# torchrun --nproc_per_node=2 train_gpt2.py train=true --config-name mod
# torchrun --nproc_per_node=2 train_gpt2.py train=true --config-name dense