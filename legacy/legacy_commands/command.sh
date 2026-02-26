# install requirements
pip install -r requirements.txt

# run fineweb
python fineweb.py

# remove .git
rm -rf .git

# then 

torchrun --standalone --nproc_per_node=2 train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 10000 --interval_size 50 --lambda_r 0.1 --mod --model_path checkpoints/model_gpt2-mini_mod_999.pth

python train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.1 --mod --model_path checkpoints/model_gpt2-mini_mod_999.pth

python train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.1 --mod --compile > output_sparse.txt 2>&1


torchrun --standalone --nproc_per_node=2 train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --total_batch_size 524288 --max_steps 2000 --interval_size 100 --lambda_r 0.0 --mod --compile --model_path checkpoints/model_gpt2-mini_mod_1999.pth> output_sparse_large_cont.txt 2>&1 

python train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.01 --penalty_type mse --density 0.3 --mode > output_mode.txt 2>&1

torchrun --standalone --nproc_per_node=2 train_gpt2.py --train --model_type gpt2-mini --batch_size 8 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.003 --penalty_type mse --density 0.3 --mode --n_experts 8 --compile > output_mode_8.txt 2>&1


python train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.0 --mode > output_mode_deterministic.txt 2>&1

torchrun --standalone --nproc_per_node=2 train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.0 --mode --compile > output_mode_deterministic_compile.txt 2>&1

python train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.0 --mode > output_mode_inside_p.txt 2>&1

torchrun --standalone --nproc_per_node=2 train_gpt2.py --train --model_type gpt2-mini --batch_size 16 --learning_rate_schedule trapezoid --total_batch_size 524288 --max_steps 1000 --interval_size 50 --lambda_r 0.0 --mod --compile > output_mod_inside_p_compile.txt 2>&1