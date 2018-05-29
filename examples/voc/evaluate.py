#!/usr/bin/env python

from __future__ import print_function

import argparse
import os.path as osp
import pprint

import cv2  # NOQA

import chainer
import numpy as np
import yaml

import chainer_mask_rcnn as cmr


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('log_dir', help='Log dir.')
    parser.add_argument('-g', '--gpu', type=int, default=0, help='GPU id.')
    args = parser.parse_args()

    log_dir = args.log_dir

    # XXX: see also demo.py
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # param
    params = yaml.load(open(osp.join(log_dir, 'params.yaml')))
    print('Training config:')
    print('# ' + '-' * 77)
    pprint.pprint(params)
    print('# ' + '-' * 77)

    # dataset
    test_data = cmr.datasets.SBDInstanceSegmentationDataset('val')
    class_names = test_data.class_names

    # model
    chainer.global_config.train = False
    chainer.global_config.enable_backprop = False

    if params['pooling_func'] == 'align':
        pooling_func = cmr.functions.roi_align_2d
    elif params['pooling_func'] == 'pooling':
        pooling_func = chainer.functions.roi_pooling_2d
    elif params['pooling_func'] == 'resize':
        pooling_func = cmr.functions.crop_and_resize
    else:
        raise ValueError

    pretrained_model = osp.join(args.log_dir, 'snapshot_model.npz')
    print('Using pretrained_model: %s' % pretrained_model)

    model = params['model']
    mask_rcnn = cmr.models.MaskRCNNResNet(
        n_layers=int(model.lstrip('resnet')),
        n_fg_class=len(class_names),
        pretrained_model=pretrained_model,
        pooling_func=pooling_func,
        anchor_scales=params.get('anchor_scales', (4, 8, 16, 32)),
        mean=params.get('mean', (123.152, 115.903, 103.063)),
        min_size=params.get('min_size', 600),
        max_size=params.get('max_size', 1000),
        roi_size=params.get('roi_size', 7),
    )
    if args.gpu >= 0:
        chainer.cuda.get_device_from_id(args.gpu).use()
        mask_rcnn.to_gpu()
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    test_data = chainer.datasets.TransformDataset(
        test_data, cmr.datasets.MaskRCNNTransform(mask_rcnn, train=False))

    # visualization
    # -------------------------------------------------------------------------

    test_vis_data = cmr.datasets.IndexingDataset(
        test_data, indices=[196, 204, 216, 257, 326, 473, 566, 649, 1063])
    test_vis_iter = chainer.iterators.SerialIterator(
        test_vis_data, batch_size=1, repeat=False, shuffle=False)

    class DummyTrainer(object):

        class DummyUpdater(object):

            iteration = 'best'

        updater = DummyUpdater()
        out = log_dir

    print('Visualizing...')
    visualizer = cmr.extensions.InstanceSegmentationVisReport(
        test_vis_iter, mask_rcnn,
        label_names=class_names,
        file_name='iteration=%s.jpg',
        copy_latest=False,
    )
    visualizer(trainer=DummyTrainer())
    print('Saved visualization:', osp.join(log_dir, 'iteration=best.jpg'))

    # evaluation
    # -------------------------------------------------------------------------

    test_iter = chainer.iterators.SerialIterator(
        test_data, batch_size=1, repeat=False, shuffle=False)

    print('Evaluating...')
    evaluator = cmr.extensions.InstanceSegmentationVOCEvaluator(
        test_iter, mask_rcnn, use_07_metric=True,
        label_names=class_names, show_progress=True)
    result = evaluator()

    for k in result:
        if isinstance(result[k], np.float64):
            result[k] = float(result[k])

    yaml_file = pretrained_model + '.eval_result.yaml'
    with open(yaml_file, 'w') as f:
        yaml.safe_dump(result, f, default_flow_style=False)

    print('Saved evaluation: %s' % yaml_file)
    pprint.pprint(result)


if __name__ == '__main__':
    main()
