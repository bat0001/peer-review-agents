#!/usr/bin/env bash
cd nanochat_260111
python scripts/tok_train.py \
    --vocab_size 65536 \
    --max_chars 2000000000
