from mlopt.learners.learner import Learner
from mlopt.learners.optimal_tree import settings as octstg
from mlopt import settings as stg
from mlopt.utils import pandas2array, get_n_processes
from mlopt import error as e
import shutil
from subprocess import call
import time
import os
import sys

class OptimalTree(Learner):

    def __init__(self,
                 **options):
        """
        Initialize OptimalTrees class.

        Parameters
        ----------
        options : dict
            Learner options as a dictionary.
        """
        if not OptimalTree.is_installed():
            e.value_error("Interpretable AI not installed")

        # Import julia and IAI module
        from interpretableai import iai
        self.iai = iai
        from julia import Distributed
        self.nprocs = Distributed.nprocs

        # Define name
        self.name = stg.OPTIMAL_TREE

        # Assign settings
        self.n_input = options.pop('n_input')
        self.n_classes = options.pop('n_classes')
        self.options = {}
        self.options['hyperplanes'] = options.pop('hyperplanes', False)
        #  self.options['fast_num_support_restarts'] = \
        #      options.pop('fast_num_support_restarts', [20])
        self.options['parallel'] = options.pop('parallel_trees', True)
        self.options['cp'] = options.pop('cp', None)
        self.options['max_depth'] = options.pop('max_depth',
                octstg.DEFAULT_TRAINING_PARAMS['max_depth'])
        self.options['minbucket'] = options.pop('minbucket',
                octstg.DEFAULT_TRAINING_PARAMS['minbucket'])
        # Pick minimum between n_best and n_classes
        self.options['n_best'] = min(options.pop('n_best', stg.N_BEST),
                                     self.n_classes)
        self.options['save_svg'] = options.pop('save_svg', False)

        # Get fraction between training and validation
        self.options['frac_train'] = options.pop('frac_train', stg.FRAC_TRAIN)

        # Load Julia
        n_cpus = get_n_processes()

        n_cur_procs = self.nprocs()
        if n_cur_procs < n_cpus and self.options['parallel']:
            # Add processors to match number of cpus
            Distributed.addprocs((n_cpus - n_cur_procs))

        # Assign optimaltrees options
        self.optimaltrees_options = {'random_seed': 1}
        self.optimaltrees_options['max_depth'] = self.options['max_depth']
        self.optimaltrees_options['minbucket'] = self.options['minbucket']
        if self.options['hyperplanes']:
            self.optimaltrees_options['hyperplane_config'] = \
                {'sparsity': 'all'}

        if self.options['cp']:
            self.optimaltrees_options['cp'] = self.options['cp']

    @classmethod
    def is_installed(cls):
        try:
            from interpretableai import iai
        except:
            return False
        return True

    def train(self, X, y):

        # Convert X to array
        self.n_train = len(X)
        # X = pandas2array(X)

        info_str = "Training trees "
        if self.options['parallel']:
            info_str += "on %d processors" % self.nprocs()
        else:
            info_str += "\n"
        stg.logger.info(info_str)

        # Start time
        start_time = time.time()

        # Create grid search
        self._grid = \
            self.iai.GridSearch(
                self.iai.OptimalTreeClassifier(
                    random_seed=self.optimaltrees_options['random_seed']
                ), **self.optimaltrees_options)

        # Train classifier
        self._grid.fit(X, y,
                       train_proportion=self.options['frac_train'])

        # Extract learner
        self._lnr = self._grid.get_learner()

        # End time
        end_time = time.time()
        stg.logger.info("Tree training time %.2f" % (end_time - start_time))

    def predict(self, X):

        # Evaluate probabilities
        y = self._lnr.predict_proba(X)
        return self.pick_best_class(y.to_numpy(), n_best=self.options['n_best'])

    def save(self, file_name):
        # Save tree as json file
        self._lnr.write_json(file_name + ".json")

        # Save tree to dot file and convert it to
        # pdf for visualization purposes
        if self.options['save_svg']:
            if shutil.which("dot") is not None:
                self._lnr.write_dot(file_name + ".dot")
                call(["dot", "-Tsvg", "-o",
                      file_name + ".svg",
                      file_name + ".dot"])
            else:
                stg.logger.warning("dot command not found in path")

    def load(self, file_name):
        # Check if file name exists
        if not os.path.isfile(file_name + ".json"):
            e.value_error("Optimal Tree json file does not exist.")

        # Load tree from file
        self._lnr = self.iai.read_json(file_name + ".json")
