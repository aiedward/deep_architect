import deep_architect.core as co
import deep_architect.modules as mo
import deep_architect.searchers.common as seco
from deep_architect.hyperparameters import D


class KerasModule(co.Module):
    """Class for taking Keras code and wrapping it in a DeepArchitect module.

    This class subclasses :class:`deep_architect.core.Module` as therefore inherits all
    the functionality associated to it (e.g., keeping track of inputs, outputs,
    and hyperparameters). It also enables to do the compile and forward
    operations for these types of modules once a module is fully specified,
    i.e., once all the hyperparameters have been chosen.

    The compile operation in this case creates all the variables used for the
    fragment of the computational graph associated to this module.
    The forward operation takes the variables that were created in the compile
    operation and constructs the actual computational graph fragment associated
    to this module.

    .. note::
        This module is abstract, meaning that it does not actually implement
        any particular Keras computation. It simply wraps Keras
        functionality in a DeepArchitect module. The instantiation of the Keras
        variables is taken care by the `compile_fn` function that takes a two
        dictionaries, one of inputs and another one of outputs, and
        returns another function that takes a dictionary of inputs and creates
        the computational graph. This functionality makes extensive use of closures.

        The keys of the dictionaries that are passed to the compile
        and forward function match the names of the inputs and hyperparameters
        respectively. The dictionary returned by the forward function has keys
        equal to the names of the outputs.

        This implementation is very similar to the implementation of the Tensorflow
        helper :class:`deep_architect.helpers.tensorflow_support.TensorflowModule`.

    Args:
        name (str): Name of the module
        compile_fn ((dict[str,object], dict[str,object]) -> (dict[str,object] -> dict[str,object])):
            The first function takes two dictionaries with
            keys corresponding to `input_names` and `output_names` and returns
            a function that takes a dictionary with keys corresponding to
            `input_names` and returns a dictionary with keys corresponding
            to `output_names`. The first function may also return
            two additional dictionaries mapping Tensorflow placeholders to the
            values that they will take during training and test.
        name_to_hyperp (dict[str,deep_architect.core.Hyperparameter]): Dictionary of
            hyperparameters that the model depends on. The keys are the local
            names of the hyperparameters.
        input_names (list[str]): List of names for the inputs.
        output_names (list[str]): List of names for the outputs.
        scope (deep_architect.core.Scope, optional): Scope where the module will be
            registered.

    """

    def __init__(self,
                 name,
                 compile_fn,
                 name_to_hyperp,
                 input_names,
                 output_names,
                 scope=None):
        co.Module.__init__(self, scope, name)
        hyperparam_dict = {}
        for h in name_to_hyperp:
            if not isinstance(name_to_hyperp[h], co.Hyperparameter):
                hyperparam_dict[h] = D([name_to_hyperp[h]])
            else:
                hyperparam_dict[h] = name_to_hyperp[h]

        self._register(input_names, output_names, hyperparam_dict)
        self._compile_fn = compile_fn

    def _compile(self):
        input_name_to_val = self._get_input_values()
        hyperp_name_to_val = self._get_hyperp_values()

        self._fn = self._compile_fn(input_name_to_val, hyperp_name_to_val)

    def _forward(self):
        input_name_to_val = self._get_input_values()
        output_name_to_val = self._fn(input_name_to_val)
        self._set_output_values(output_name_to_val)

    def _update(self):
        pass


def keras_module(name,
                 compile_fn,
                 name_to_hyperp,
                 input_names,
                 output_names,
                 scope=None):
    return KerasModule(name, compile_fn, name_to_hyperp, input_names,
                       output_names, scope).get_io()


def siso_keras_module(name, compile_fn, name_to_hyperp, scope=None):
    return KerasModule(name, compile_fn, name_to_hyperp, ['in'], ['out'],
                       scope).get_io()


def siso_keras_module_from_keras_layer_fn(layer_fn,
                                          name_to_hyperp,
                                          scope=None,
                                          name=None):

    def compile_fn(di, dh):
        m = layer_fn(**dh)

        def forward_fn(di):
            return {"out": m(di["in"])}

        return forward_fn

    if name is None:
        name = layer_fn.__name__

    return siso_keras_module(name, compile_fn, name_to_hyperp, scope)


class KerasRandomModel:

    def __init__(self, search_space_fn, hyperp_value_lst=None):

        inputs, outputs = mo.buffer_io(*search_space_fn())
        if hyperp_value_lst is not None:
            seco.specify(outputs, hyperp_value_lst)
            self.hyperp_value_lst = hyperp_value_lst
        else:
            self.hyperp_value_lst = seco.random_specify(outputs)

        self.inputs = inputs
        self.outputs = outputs
        # precomputed for efficiency reasons. not necessary for static graphs.
        self._module_seq = co.determine_module_eval_seq(inputs)

    def forward(self, input_name_to_val):
        input_to_val = {
            self.inputs[name]: val for (name, val) in input_name_to_val.items()
        }
        co.forward(input_to_val, self._module_seq)
        output_name_to_val = {
            name: ox.val for (name, ox) in self.outputs.items()
        }
        return output_name_to_val

    def get_hyperp_values(self):
        return self.hyperp_value_lst