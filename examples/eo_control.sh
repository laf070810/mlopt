#!/bin/bash
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --cpus-per-task=5
#SBATCH --mem-per-cpu=15G
#SBATCH --gres=gpu:1
#SBATCH --partition=sched_mit_sloan_gpu
#SBATCH --time=0-24:00
#SBATCH -o /pool001/stellato/output/output_%A_N%a.txt
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=bartolomeo.stellato@gmail.com

# Activate environment
source activate python37

# module load gurobi/8.0.1
export GRB_LICENSE_FILE="/home/software/gurobi/gurobi.lic"

SLURM_PARTITION=`squeue -h -o "%P" -j$SLURM_JOB_ID`;
if [[ $SLURM_PARTITION == *"interactive"* ]]; then
    # TODO: Fix this
    export IAI_LICENSE_FILE="/home/stellato/iai_interactive.lic"
elif [[ $SLURM_PARTITION == *"gpu"* ]]; then
    module load sloan/cuda/9.0
    export IAI_LICENSE_FILE="/home/stellato/iai_gpu.lic"
fi

# Run actual script
python online_optimization/control/online_control.py --horizon $SLURM_ARRAY_TASK_ID
