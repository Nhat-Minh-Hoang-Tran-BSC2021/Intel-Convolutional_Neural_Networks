from tensorflow import keras
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2
from tensorflow.keras.layers import GRU, LSTM, Dense, Dropout, TimeDistributed


def LRMobileNetV2(seq_length=16, frame_shape=(224, 224, 3), classes=1000,
                  weights='imagenet', dropout=0.5):
    """Long-term Recurrent MobileNetV2 architecture.

    Reference papers:
    - [Long-term Recurrent Convolutional Networks for Visual Recognition and Description]
    (https://arxiv.org/abs/1411.4389)
    - [MobileNetV2: Inverted Residuals and Linear Bottlenecks]
    (https://arxiv.org/abs/1801.04381) (CVPR 2018)

    Args:
        seq_length: Number of frames in each sample.
        frame_shape: Shape of each frame in the sample.
        classes: Number of classes to classify.
        weights: One of `None` (random initialization),
            'imagenet' (pre-training on ImageNet),
            or the path to the weights file to be loaded.
        dropout: Float between 0 and 1. Fraction of the units to drop.

    Returns:
        A `keras.Model` instance.
    """

    model = keras.Sequential()
    model.add(TimeDistributed(
        MobileNetV2(frame_shape, include_top=False, pooling='avg'),
        input_shape=((seq_length,) + frame_shape)))
    model.add(LSTM(1024, return_sequences=True))
    model.add(Dropout(dropout))
    model.add(GRU(512, return_sequences=True))
    model.add(Dropout(dropout))
    model.add(GRU(256, return_sequences=True))
    model.add(Dropout(dropout))
    model.add(GRU(128))
    model.add(Dropout(dropout))
    model.add(Dense(classes, activation='softmax', name='predictions'))

    # Load weights
    if weights != 'imagenet':
        model.load_weights(weights)

    return model
