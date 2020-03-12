import tarfile

import numpy as np
from nnabla import random
from nnabla.logger import logger
from nnabla.utils.data_iterator import data_iterator
from nnabla.utils.data_source import DataSource
from nnabla.utils.data_source_loader import download
from sklearn.model_selection import train_test_split


def download_data(train=True):
    data_uri = "https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz"
    logger.info('Getting labeled data from {}.'.format(data_uri))

    r = download(data_uri)  # file object returned
    with tarfile.open(fileobj=r, mode="r:gz") as fpin:
        if train:
            images = []
            labels = []
            for member in fpin.getmembers():
                if "data_batch" not in member.name:
                    continue
                fp = fpin.extractfile(member)
                data = np.load(fp, encoding="bytes", allow_pickle=True)
                images.append(data[b"data"])
                labels.append(data[b"labels"])
            size = 50000
            images = np.concatenate(images).reshape(size, 3, 32, 32)
            labels = np.concatenate(labels).reshape(-1, 1)
        else:
            for member in fpin.getmembers():
                if "test_batch" not in member.name:
                    continue
                fp = fpin.extractfile(member)
                data = np.load(fp, encoding="bytes", allow_pickle=True)
                images = data[b"data"].reshape(10000, 3, 32, 32)
                labels = np.array(data[b"labels"]).reshape(-1, 1)
    return (images, labels)


class CifarDataSource(DataSource):

    def _get_data(self, position):
        image = self._images[self._indexes[position]]
        label = self._labels[self._indexes[position]]
        return (image, label)

    def __init__(self, images, labels, shuffle=False, rng=None):
        super(CifarDataSource, self).__init__(shuffle=shuffle, rng=rng)
        self._train = True
        self._images = images
        self._labels = labels
        self._size = self._labels.size
        self._variables = ('x', 'y')
        if rng is None:
            rng = np.random.RandomState(313)
        self.rng = rng
        self.reset()

    def reset(self):
        if self._shuffle:
            self._indexes = self.rng.permutation(self._size)
        else:
            self._indexes = np.arange(self._size)
        super(CifarDataSource, self).reset()

    @property
    def images(self):
        """Get copy of whole data with a shape of (N, 1, H, W)."""
        return self._images.copy()

    @property
    def labels(self):
        """Get copy of whole label with a shape of (N, 1)."""
        return self._labels.copy()


def get_data(train, comm, rng):
    # download the data
    images, labels = download_data(train)

    n = len(labels)
    if rng is None:
        rng = random.prng

    if train:
        index = rng.randint(0, n, size=n)
    else:
        index = np.arange(n)

    num = n // comm.n_procs

    selected_idx = index[num*comm.rank:num*(comm.rank + 1)]

    return images[selected_idx], labels[selected_idx]


def get_data_iterators(batch_size,
                       comm,
                       train=True,
                       portion=1,
                       rng=None,
                       with_memory_cache=False,
                       with_file_cache=False):

    if train:
        images, labels = get_data(True, comm, rng)
        train_size = int(len(labels) * portion)
        X_train, X_test, y_train, y_test = train_test_split(
            images, labels,
            stratify=labels,
            train_size=train_size,
            random_state=random.prng
        )
        train = data_iterator(
            CifarDataSource(X_train, y_train, shuffle=True, rng=rng),
            batch_size[0],
            rng,
            with_memory_cache,
            with_file_cache
        )
        valid = data_iterator(
            CifarDataSource(X_test, y_test, shuffle=True, rng=rng),
            batch_size[1],
            rng,
            with_memory_cache,
            with_file_cache
        )
    else:
        images, labels = get_data(True, comm, rng)
        train = data_iterator(
            CifarDataSource(images, labels, shuffle=True, rng=rng),
            batch_size[0],
            rng,
            with_memory_cache,
            with_file_cache
        )
        images, labels = get_data(False, comm, rng)
        valid = data_iterator(
            CifarDataSource(images, labels, shuffle=False, rng=rng),
            batch_size[1],
            rng,
            with_memory_cache,
            with_file_cache
        )

    return train, valid