#!/bin/bash

rm -fr  ~/.cache/huggingface/datasets/taesiri___arxiv_qa
/opt/homebrew/Caskroom/miniforge/base/envs/torch2/bin/python update_dataset.py
/opt/homebrew/Caskroom/miniforge/base/envs/torch2/bin/python readme-generator.py

# perform git commit and push
git add .
git commit -m "update dataset"
git push origin main
