#!/usr/bin/env bash
ls 
cd nanochat_260111
which python
python -u -m nanochat.dataset -n -1 -w 8 # -u to unbuffer stdout

cd ../ # go back to the root directory
