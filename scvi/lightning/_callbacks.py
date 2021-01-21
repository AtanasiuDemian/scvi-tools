import warnings

import numpy as np
import torch
from copy import deepcopy
from pytorch_lightning.callbacks import Callback
from pytorch_lightning.utilities import rank_zero_info


class SubSampleLabels(Callback):
    def __init__(self):
        super().__init__()

    def on_epoch_start(self, trainer, pl_module):
        trainer.train_dataloader.resample_labels()
        super().on_epoch_start(trainer, pl_module)


class SaveBestState(Callback):
    r"""
    Save the best model state and restore into model.

    Parameters
    ----------
    monitor
        quantity to monitor.
    verbose
        verbosity, True or False.
    mode
        one of ["min", "max"].
    period
        Interval (number of epochs) between checkpoints.

    Examples
    --------
    from scvi.lightning import Trainer
    from scvi.lightning import SaveBestState
    """

    def __init__(
        self,
        monitor: str = "elbo_validation",
        mode: str = "min",
        verbose=False,
        period=1,
    ):
        super().__init__()

        self.monitor = monitor
        self.verbose = verbose
        self.period = period
        self.epochs_since_last_check = 0
        self.best_model_state = None

        if mode not in ["min", "max"]:
            raise ValueError(
                f"SaveBestState mode {mode} is unknown",
            )

        if mode == "min":
            self.monitor_op = np.less
            self.best_model_metric_val = np.Inf
            self.mode = "min"
        elif mode == "max":
            self.monitor_op = np.greater
            self.best_model_metric_val = -np.Inf
            self.mode = "max"
        else:
            if "acc" in self.monitor or self.monitor.startswith("fmeasure"):
                self.monitor_op = np.greater
                self.best_model_metric_val = -np.Inf
                self.mode = "max"
            else:
                self.monitor_op = np.less
                self.best_model_metric_val = np.Inf
                self.mode = "min"

    def check_monitor_top(self, current):
        return self.monitor_op(current, self.best_model_metric_val)

    def on_epoch_end(self, trainer, pl_module):
        logs = trainer.callback_metrics
        self.epochs_since_last_check += 1

        if self.epochs_since_last_check >= self.period:
            self.epochs_since_last_check = 0
            current = logs.get(self.monitor)

            if current is None:
                warnings.warn(
                    f"Can save best model state only with {self.monitor} available,"
                    " skipping.",
                    RuntimeWarning,
                )
            else:
                if isinstance(current, torch.Tensor):
                    current = current.item()
                if self.check_monitor_top(current):
                    self.best_model_state = deepcopy(pl_module.model.state_dict())
                    self.best_model_metric_val = current

                    if self.verbose:
                        rank_zero_info(
                            f"\nEpoch {trainer.current_epoch:05d}: {self.monitor} reached."
                            f" Model best state updated."
                        )

    def on_train_end(self, trainer, pl_module):

        pl_module.model.load_state_dict(self.best_model_state)
