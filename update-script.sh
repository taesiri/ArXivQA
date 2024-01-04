#!/bin/bash

# Change directory to /Users/m/Github/ArXivQA
cd /Users/m/Github/ArXivQA || {
    echo "Error: Failed to change directory to /Users/m/Github/ArXivQA. Please make sure the directory exists and try again."
    exit 1
}

source ~/miniconda3/bin/activate

# Check if conda is installed
if ! command -v conda &> /dev/null
then
    echo "Error: conda not found. Please install conda and try again."
    exit 1
fi

# Activate the conda environment
echo "Activating conda environment 'torch12'"
conda activate torch12 || {
    echo "Error: Failed to activate conda environment 'torch12'. Please make sure it is installed and try again."
    exit 1
}

# Remove the cache directory
echo "Removing cache directory '~/.cache/huggingface/datasets/taesiri___arxiv_qa'"
rm -fr ~/.cache/huggingface/datasets/taesiri___arviv_qa || {
    echo "Error: Failed to remove cache directory '~/.cache/huggingface/datasets/taesiri___arxiv_qa'. Please make sure it exists and try again."
    exit 1
}

# Run the update_dataset.py script
echo "Running 'python update_dataset.py'"
python update_dataset.py || {
    echo "Error: Failed to run 'python update_dataset.py'. Please make sure it is executable and try again."
    exit 1
}

# Run the readme-generator.py script
echo "Running 'python readme-generator.py'"
python readme-generator.py || {
    echo "Error: Failed to run 'python readme-generator.py'. Please make sure it is executable and try again."
    exit 1
}

# Perform git commit and push
echo "Performing git commit and push"
git add . || {
    echo "Error: Failed to add files to git. Please make sure git is installed and try again."
    exit 1
}
git commit -m "update dataset" || {
    echo "Error: Failed to commit changes to git. Please make sure git is installed and try again."
    exit 1
}
git push origin main || {
    echo "Error: Failed to push changes to git. Please make sure git is installed and try again."
    exit 1
}

# Exit with success status
echo "Script completed successfully."
exit 0