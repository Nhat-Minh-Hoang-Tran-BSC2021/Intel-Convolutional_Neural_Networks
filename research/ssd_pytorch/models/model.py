# Copyright (c) 2018-2019, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import List, Tuple

import torch
import torch.nn as nn
from torch import Tensor
from torchvision.models import mobilenet_v2


class SSDMobileNetV2FeatureExtractor(nn.Module):
    # See details at
    # https://github.com/tensorflow/models/blob/master/research/object_detection/models/ssd_mobilenet_v2_keras_feature_extractor.py#L28

    def __init__(self, is_training=False, num_layers=6):
        """Constructor.

        Args:
            is_training: Whether the network is in training mode.
            num_layers: Number of SSD layers.
        """
        super().__init__()
        self.is_training = is_training
        self.num_layers = num_layers

        backbone = mobilenet_v2(pretrained=True)
        # The output of feature_extractor should have shape of (N, x, 38, 38)
        self.feature_extractor = nn.Sequential(
            *list(backbone.features.children())[:7]
        )
        self.out_channels = [32, 512, 512, 256, 256, 256]

    def forward(self, x):
        return self.feature_extractor(x)


class SSD300(nn.Module):
    """Instantiates the SSD architecture.

    Reference:
    - [SSD: Single Shot MultiBox Detector](
        https://arxiv.org/abs/1512.02325
    )
    - [SSD300 v1.1 For PyTorch](
        https://github.com/NVIDIA/DeepLearningExamples/tree/master/PyTorch/Detection/SSD
    )
    """

    def __init__(self,
                 backbone=SSDMobileNetV2FeatureExtractor(),
                 num_classes=81,
                 weights=None):
        super().__init__()
        self.input_shape = (3, 300, 300)
        self.num_classes = num_classes
        self.feature_extractor = backbone
        self._build_feature_layers(self.feature_extractor.out_channels)
        self.num_defaults = [4, 6, 6, 6, 4, 4]
        self.loc = []
        self.conf = []

        # Convolutional Filters
        # Each filter produces either a score for a category,
        # or a shape offset relative to the default box coordinates
        for nd, oc in zip(self.num_defaults,
                          self.feature_extractor.out_channels):
            self.loc.append(
                nn.Conv2d(oc, nd * 4, kernel_size=3, padding=1)
            )
            self.conf.append(
                nn.Conv2d(oc, nd * self.num_classes, kernel_size=3, padding=1)
            )

        self.loc = nn.ModuleList(self.loc)
        self.conf = nn.ModuleList(self.conf)
        self._init_weights()

    def _build_feature_layers(self, input_size: List[int]) -> nn.ModuleList:
        """Multi-scale feature maps.

        They correspond to conv7, conv8_2, conv9_2, conv10_2, and conv11_2
        in the `SSD: Single Shot MultiBox Detector` paper. See details at
        https://github.com/weiliu89/caffe/blob/ssd/examples/ssd/ssd_pascal.py
        """
        self.feature_blocks = []
        for i, (input_size, output_size, channels) in enumerate(
                zip(input_size[:-1], input_size[1:],
                    [256, 256, 128, 128, 128])):

            if i < 3:
                layer = nn.Sequential(
                    nn.Conv2d(input_size, channels, kernel_size=1, bias=False),
                    nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(channels, output_size, kernel_size=3,
                              padding=1, stride=2, bias=False),
                    nn.BatchNorm2d(output_size),
                    nn.ReLU(inplace=True),
                )
            else:
                layer = nn.Sequential(
                    nn.Conv2d(input_size, channels, kernel_size=1, bias=False),
                    nn.BatchNorm2d(channels),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(channels, output_size,
                              kernel_size=3, bias=False),
                    nn.BatchNorm2d(output_size),
                    nn.ReLU(inplace=True),
                )

            self.feature_blocks.append(layer)

        self.feature_blocks = nn.ModuleList(self.feature_blocks)

    def _init_weights(self):
        layers = [*self.feature_blocks, *self.loc, *self.conf]
        for layer in layers:
            for param in layer.parameters():
                if param.dim() > 1:
                    nn.init.xavier_uniform_(param)

    def bbox_view(self,
                  src: Tensor,
                  loc: nn.ModuleList,
                  conf: nn.ModuleList) -> Tuple[Tensor, Tensor]:
        """Shape the classifier to the view of bboxes."""
        ret = [
            (
                l(s).view(s.shape[0], 4, -1),
                c(s).view(s.shape[0], self.num_classes, -1),
            )
            for s, l, c in zip(src, loc, conf)
        ]

        locs, confs = list(zip(*ret))
        locs = torch.cat(locs, 2).contiguous()
        confs = torch.cat(confs, 2).contiguous()
        return locs, confs

    def forward(self, x):
        x = self.feature_extractor(x)

        detection_feed = [x]
        for layer in self.feature_blocks:
            x = layer(x)
            detection_feed.append(x)

        # Feature Map 38x38x4, 19x19x6, 10x10x6, 5x5x6, 3x3x4, 1x1x4
        locs, confs = self.bbox_view(detection_feed, self.loc, self.conf)

        # For SSD 300, shall return N x {num_locs, num_classes} x 8732 results
        return locs, confs
