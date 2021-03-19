from joblib import Parallel, delayed
from mlopt import settings as stg
import numpy as np
from mlopt import utils as u
from tqdm.auto import tqdm


def best_strategy(theta, obj_train, encoding, problem):
    """Compute best strategy between the ones in encoding."""

    problem.populate(theta)  # Populate parameters

    # Serial solution over the strategies
    results = [problem.solve(strategy=strategy) for strategy in encoding]

    # Compute cost degradation
    degradation = []
    for r in results:

        cost = r['cost']

        if r['infeasibility'] > stg.INFEAS_TOL:
            cost = np.inf

        diff = np.abs(cost - obj_train)
        if np.abs(obj_train) > stg.DIVISION_TOL:  # Normalize in case
            diff /= np.abs(obj_train)
        degradation.append(diff)

    # Find minimum one
    best_strategy = np.argmin(degradation)
    #  if degradation[best_strategy] > stg.FILTER_SUBOPT:
    #      stg.logger.warning("Sample assigned to strategy more " +
    #                         "than %.2e suboptimal." % stg.FILTER_SUBOPT)

    return best_strategy, degradation[best_strategy]


class Filter(object):
    """Strategy filter."""

    def __init__(self,
                 X_train=None,
                 y_train=None,
                 obj_train=None,
                 encoding=None,
                 problem=None):
        """Initialize strategy condenser."""
        self.X_train = X_train
        self.y_train = y_train
        self.encoding = encoding
        self.obj_train = obj_train
        self.problem = problem

    def assign_samples(self, discarded_samples, selected_strategies,
                       batch_size, parallel=True):
        """
        Assign samples to strategies choosing the ones minimizing the cost.
        """

        # Backup strategies labels and encodings
        #  self.y_full = self.y_train

        # Reassign y_labels
        # selected_strategies: find index where new labels are
        # discarded_strategies: -1
        self.y_train = np.array([np.where(selected_strategies == label)[0][0]
                                 if label in selected_strategies
                                 else -1
                                 for label in self.y_train])

        # Assign discarded samples and compute degradation
        degradation = np.zeros(len(discarded_samples))

        n_jobs = u.get_n_processes() if parallel else 1

        stg.logger.info("Assign samples to selected strategies (n_jobs = %d)"
                        % n_jobs)

        results = Parallel(n_jobs=n_jobs, batch_size=batch_size)(
            delayed(best_strategy)(self.X_train.iloc[i], self.obj_train[i],
                                   self.encoding, self.problem)
            for i in tqdm(range(len(discarded_samples)))
        )

        for i in range(len(discarded_samples)):
            sample_idx = discarded_samples[i]
            self.y_train[sample_idx], degradation[i] = results[i]

        return degradation

    def select_strategies(self, samples_fraction):
        """Select the most frequent strategies depending on the counts"""

        n_samples = len(self.X_train)
        n_strategies = len(self.encoding)
        n_samples_selected = int(samples_fraction * n_samples)

        stg.logger.info("Selecting most frequent strategies")

        # Select strategies with high frequency counts
        strategies, y_counts = np.unique(self.y_train, return_counts=True)
        assert n_strategies == len(strategies)  # Sanity check

        # Sort from largest to smallest counts and pick
        # only the first ones covering up to samples_fraction samples
        idx_sort = np.argsort(y_counts)[::-1]
        selected_strategies = []
        n_temp = 0
        for idx in idx_sort:
            n_temp += y_counts[idx]  # count selected samples
            selected_strategies.append(strategies[idx])
            if n_temp > n_samples_selected:
                break

        stg.logger.info("Selected %d strategies" % len(selected_strategies))

        return selected_strategies

    def filter(self,
               samples_fraction=stg.FILTER_STRATEGIES_SAMPLES_FRACTION,
               max_iter=stg.FILTER_MAX_ITER,
               batch_size=stg.JOBLIB_BATCH_SIZE,
               parallel=True):
        """Filter strategies."""
        n_samples = len(self.X_train)

        # Backup strategies labels and encodings
        self.y_full = self.y_train
        self.encoding_full = self.encoding

        degradation = [np.inf]
        for k in range(max_iter):

            selected_strategies = \
                self.select_strategies(samples_fraction=samples_fraction)

            # Reassign encodings and labels
            self.encoding = [self.encoding[i] for i in selected_strategies]

            # Find discarded samples
            discarded_samples = np.array([i for i in range(n_samples)
                                          if self.y_train[i]
                                          not in selected_strategies])

            stg.logger.info("Samples fraction at least %.3f %%" % (100 * samples_fraction))
            stg.logger.info("Discarded strategies for %d samples (%.2f %%)" %
                            (len(discarded_samples),
                             (100 * len(discarded_samples) / n_samples)))

            # Reassign discarded samples to selected strategies
            degradation = self.assign_samples(discarded_samples,
                                              selected_strategies,
                                              batch_size=batch_size,
                                              parallel=parallel)

            if len(degradation) > 0:
                stg.logger.info("\nAverage cost degradation = %.2e %%" %
                                (100 * np.mean(degradation)))
                stg.logger.info("Max cost degradation = %.2e %%" %
                                (100 * np.max(degradation)))

                if np.mean(degradation) > stg.FILTER_SUBOPT:
                    samples_fraction = 1 - (1 - samples_fraction)/2

                    stg.logger.info("Mean degradation too high, "
                                    "trying samples_fraction = %.4f " % samples_fraction)
                    self.y_train = self.y_full
                    self.encoding = self.encoding_full
                else:
                    stg.logger.info("Acceptable degradation found")
                    break
            else:
                stg.logger.info("No more discarded points.")
                break

        if k == max_iter - 1:
            self.y_train = self.y_full
            self.encoding = self.encoding_full
            stg.logger.warning("No feasible filtering found.")

        return self.y_train, self.encoding
