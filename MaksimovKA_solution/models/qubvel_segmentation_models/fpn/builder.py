from keras.layers import Conv2D
from keras.layers import Concatenate
from keras.layers import Activation
from keras.layers import SpatialDropout2D
from keras.models import Model

from .blocks import pyramid_block
from .blocks import Conv
from ..utils import extract_outputs, to_tuple

import numpy as np

import keras
from distutils.version import StrictVersion

if StrictVersion(keras.__version__) < StrictVersion('2.2.3'):
    from .layers import UpSampling2D
else:
    from keras.layers import UpSampling2D

def build_fpn(backbone,
              fpn_layers,
              classes=21,
              activation='softmax',
              upsample_rates=(2,2,2),
              last_upsample=4,
              pyramid_filters=256,
              segmentation_filters=128,
              use_batchnorm=False,
              dropout=None,
              interpolation='nearest'):
    """
    Implementation of FPN head for segmentation models according to:
        http://presentations.cocodataset.org/COCO17-Stuff-FAIR.pdf

    Args:
        backbone: Keras `Model`, some classification model without top
        layers: list of layer names or indexes, used for pyramid building
        classes: int, number of output feature maps
        activation: activation in last layer, e.g. 'sigmoid' or 'softmax'
        upsample_rates: tuple of integers, scaling rates between pyramid blocks
        pyramid_filters: int, number of filters in `M` blocks of top-down FPN branch
        segmentation_filters: int, number of filters in `P` blocks of FPN
        last_upsample: rate for upsumpling concatenated pyramid predictions to
            match spatial resolution of input data
        last_upsampling_type: 'nn' or 'bilinear'
        dropout: float [0, 1), dropout rate
        use_batchnorm: bool, include batch normalization to FPN between `conv`
            and `relu` layers

    Returns:
        model: Keras `Model`
    """

    if len(upsample_rates) != len(fpn_layers):
        raise ValueError('Number of intermediate feature maps and upsample steps should match')

    # extract model layer outputs
    outputs = extract_outputs(backbone, fpn_layers, include_top=True)

    # add upsample rate `1` for first block
    upsample_rates = [1] + list(upsample_rates)

    # top - down path, build pyramid
    m = None
    pyramid = []
    for i, c in enumerate(outputs):
        m, p = pyramid_block(pyramid_filters=pyramid_filters,
                            segmentation_filters=segmentation_filters,
                            upsample_rate=upsample_rates[i],
                            use_batchnorm=use_batchnorm)(c, m)
        pyramid.append(p)


    # upsample and concatenate all pyramid layer
    upsampled_pyramid = []

    for i, p in enumerate(pyramid[::-1]):
        if upsample_rates[i] > 1:
            upsample_rate = to_tuple(np.prod(upsample_rates[:i+1]))
            p = UpSampling2D(size=upsample_rate, interpolation=interpolation)(p)
        upsampled_pyramid.append(p)

    x = Concatenate()(upsampled_pyramid)

    # final convolution
    n_filters = segmentation_filters * len(pyramid)
    x = Conv(n_filters, (3, 3), use_batchnorm=use_batchnorm, padding='same')(x)
    if dropout is not None:
        x = SpatialDropout2D(dropout)(x)

    x = Conv2D(classes, (3, 3), padding='same')(x)
    x = Activation(activation)(x)

    # upsampling to original spatial resolution
    x = UpSampling2D(size=to_tuple(last_upsample), interpolation=interpolation)(x)

    model = Model(backbone.input, x)
    return model
