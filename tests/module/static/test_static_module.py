import nnabla as nn
from nnabla_nas.module import static as smo
from nnabla_nas import module as mo


def test_static_module():
    module_1 = smo.Module(name='module_1')
    module_2 = smo.Module(parents=[module_1],
                          name='module_2')

    assert module_1.children[0] == module_2
    assert module_2.parents[0] == module_1

    class MyModule(smo.Module):
        def __init__(self, parents):
            smo.Module.__init__(self, parents=parents)
            self.linear = mo.Linear(in_features=5, out_features=3)

        def call(self, *input):
            return self.linear(*input)

    input = smo.Input(value=nn.Variable((8, 5)))
    my_mod = MyModule(parents=[input])
    output = my_mod()

    assert 'linear' in my_mod.modules
    assert len(my_mod.modules) == 1
    assert output.shape == (8, 3)
    assert my_mod.shape == (8, 3)

    my_mod.reset_value()
    assert my_mod._value is None
    assert my_mod._shape == -1
    input.value = nn.Variable((10, 5))
    assert my_mod.shape == (10, 3)

    params = my_mod.get_parameters()
    assert len(params) == 2


if __name__ == '__main__':
    test_static_module()