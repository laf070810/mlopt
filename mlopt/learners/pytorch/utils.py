import numpy as np
from mlopt import settings as stg


def accuracy(outputs, labels):
    """
    Compute the accuracy, given the outputs and labels for all images.

    Args:
        outputs: (np.ndarray) output of the model
        labels: (np.ndarray) batch labels

    Returns: (float) accuracy in [0,1]
    """
    outputs = np.argmax(outputs, axis=1)
    return np.sum(outputs == labels) / float(labels.size)


def log_metrics(metrics, string="Train"):
    # compute mean of all metrics in summary
    metrics_mean = {metric: np.mean([x[metric] for x in metrics])
                    for metric in metrics[0]}
    metrics_string = " ; ".join("{}: {:05.3f}".format(k, v)
                                for k, v in metrics_mean.items())
    stg.logger.info("- {} metrics: ".format(string) + metrics_string)

    return metrics_mean


def eval_metrics(outputs, labels, loss):
    outputs = outputs.detach().cpu().numpy()
    labels = labels.detach().cpu().numpy()

    # compute all metrics on this batch
    summary = {metric: METRICS[metric](outputs,
                                       labels)
               for metric in METRICS}
    summary['loss'] = loss.item()

    return summary


class RunningAverage():
    """A simple class that maintains the running average of a quantity

    Example:
    ```
    loss_avg = RunningAverage()
    loss_avg.update(2)
    loss_avg.update(4)
    loss_avg()  # Returns 3
    ```
    """

    def __init__(self):
        self.steps = 0
        self.total = 0.0

    def update(self, val):
        self.total += val
        self.steps += 1

    def __call__(self):
        return self.total/float(self.steps)


# maintain all metrics required in this dictionary- these are used in
# the training and evaluation loops
METRICS = {
    'accuracy': accuracy,
    # could add more metrics such as accuracy for each token type
}


METRICS_STEPS = 100

