import optuna
from mlopt.learners.learner import Learner
from mlopt.learners.xgboost import settings as xgbs
from mlopt import settings as stg
from mlopt import error as e
import time
import copy


class XGBoostObjective(object):
    def __init__(self, dtrain, bounds, n_classes):
        self.bounds = copy.deepcopy(bounds)
        self.n_classes = n_classes
        import xgboost as xgb
        self.xgb = xgb
        self.dtrain = dtrain

    def __call__(self, trial):
        params = xgbs.PARAMETERS
        params.update({
            'objective': 'multi:softprob',
            'eval_metric': 'mlogloss',
            'booster': 'gbtree',
            'num_class': self.n_classes,
            'lambda': trial.suggest_float(
                'lambda', *self.bounds['lambda'], log=True),
            'alpha': trial.suggest_float(
                'alpha', *self.bounds['alpha'], log=True),
            'max_depth': trial.suggest_int(
                'max_depth', *self.bounds['max_depth']),
            'eta': trial.suggest_float(
                'eta', *self.bounds['eta'], log=True),
            'gamma': trial.suggest_float(
                'gamma', *self.bounds['gamma'], log=True),
        })
        n_boost_round = trial.suggest_int(
            'n_boost_round', *self.bounds['n_boost_round'])

        pruning_callback = optuna.integration.XGBoostPruningCallback(
            trial, "test-mlogloss")
        history = self.xgb.cv(params, self.dtrain,
                              num_boost_round=n_boost_round,
                              callbacks=[pruning_callback]
                              )

        mean_loss = history["test-mlogloss-mean"].values[-1]
        return mean_loss


class XGBoost(Learner):
    """XGBoost Learner class. """

    def __init__(self,
                 **options):
        """
        Initialize XGBoost Learner class.

        Parameters
        ----------
        options : dict
            Learner options as a dictionary.
        """
        if not XGBoost.is_installed():
            e.value_error("XGBoost not installed")

        import xgboost as xgb
        self.xgb = xgb

        self.name = stg.XGBOOST
        self.n_input = options.pop('n_input')
        self.n_classes = options.pop('n_classes')
        self.options = {}

        self.options['bounds'] = options.pop(
            'bounds', xgbs.PARAMETER_BOUNDS)

        not_specified_bounds = \
            [x for x in xgbs.PARAMETER_BOUNDS.keys()
             if x not in self.options['bounds'].keys()]
        for p in not_specified_bounds:  # Assign remaining keys
            self.options['bounds'][p] = xgbs.PARAMETER_BOUNDS[p]

        # Pick minimum between n_best and n_classes
        self.options['n_best'] = min(options.pop('n_best', stg.N_BEST),
                                     self.n_classes)

        # Pick number of hyperopt_trials
        self.options['n_train_trials'] = options.pop('n_train_trials',
                                                     stg.N_TRAIN_TRIALS)

        # Mute optuna
        optuna.logging.set_verbosity(optuna.logging.INFO)

    @classmethod
    def is_installed(cls):
        try:
            import xgboost
            xgboost
        except ImportError:
            return False
        return True

    def train(self, X, y):

        self.n_train = len(X)
        dtrain = self.xgb.DMatrix(X, label=y)

        stg.logger.info("Train XGBoost")

        start_time = time.time()
        objective = XGBoostObjective(dtrain, self.options['bounds'],
                                     self.n_classes)

        sampler = optuna.samplers.TPESampler(seed=0)  # Deterministic
        pruner = optuna.pruners.MedianPruner(n_warmup_steps=5)
        study = optuna.create_study(sampler=sampler, pruner=pruner,
                                    direction="minimize")
        study.optimize(objective, n_trials=self.options['n_train_trials'],
                       #  show_progress_bar=True
                       )
        self.best_params = study.best_trial.params

        self.print_trial_stats(study)

        # Train again
        stg.logger.info("Train with best parameters")
        params = xgbs.PARAMETERS  # Fixed parameters
        params.update({k: v for k, v in self.best_params.items()
                       if k != 'n_boost_round'})
        self.bst = self.xgb.train(
            params=params,
            dtrain=dtrain,
            num_boost_round=self.best_params['n_boost_round']
        )

        # Print timing
        end_time = time.time()
        stg.logger.info("Training time %.2f" % (end_time - start_time))

    def predict(self, X):
        y = self.bst.predict(self.xgb.DMatrix(X))
        return self.pick_best_class(y, n_best=self.options['n_best'])

    def save(self, file_name):
        self.bst.save_model(file_name + ".json")

    def load(self, file_name):
        self.bst = self.xgb.Booster()
        self.bst.load_model(file_name + ".json")
