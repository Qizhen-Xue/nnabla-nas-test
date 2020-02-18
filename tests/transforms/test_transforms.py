import nnabla as nn
import numpy as np
import pytest
from nnabla.testing import assert_allclose

from nnabla_nas.dataset.transforms import Normalize
from nnabla_nas.dataset.transforms import RandomCrop
from nnabla_nas.dataset.transforms import RandomHorizontalFlip
from nnabla_nas.dataset.transforms import RandomVerticalFlip
from nnabla_nas.dataset.transforms import Resize


def test_normalize():
    mean = (0.49139968, 0.48215827, 0.44653124)
    std = (0.24703233, 0.24348505, 0.26158768)
    scale = 1. / 255
    tran = Normalize(mean=mean, std=std, scale=scale)

    input = np.random.randn(16, 3, 32, 32)
    m = np.reshape(mean, (1, 3, 1, 1))
    s = np.reshape(std, (1, 3, 1, 1))
    output = (input * scale - m) / s

    input_var = nn.Variable.from_numpy_array(input)
    output_var = tran(input_var)
    output_var.forward()
    assert print(tran) is None
    assert_allclose(output_var.d, output)


@pytest.mark.parametrize('size', [(16, 16), (48, 50)])
@pytest.mark.parametrize('interpolation', ['linear', 'nearest'])
def test_resize(size, interpolation):
    input = nn.Variable((16, 3, 32, 32))
    tran = Resize(size=size, interpolation=interpolation)
    output = tran(input)
    assert print(tran) is None
    assert output.shape == (16, 3, ) + size


def test_random_horizontal_flip():
    input = nn.Variable((16, 3, 32, 32))
    tran = RandomHorizontalFlip()
    output = tran(input)
    assert print(tran) is None
    assert output.shape == input.shape


def test_random_vertical_flip():
    input = nn.Variable((16, 3, 32, 32))
    tran = RandomVerticalFlip()
    output = tran(input)
    assert print(tran) is None
    assert output.shape == input.shape


def test_random_crop():
    input = nn.Variable((16, 3, 32, 32))
    tran = RandomCrop(shape=(3, 16, 16), pad_width=(4, 4, 4, 4))
    output = tran(input)
    assert print(tran) is None
    assert output.shape == (16, 3, 16, 16)
