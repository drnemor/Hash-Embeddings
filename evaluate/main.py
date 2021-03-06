# -*- coding: utf-8 -*-

##### SETTING UP #####
import argparse
import sys
import os
import time
from timeit import default_timer

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

parentddir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))
sys.path.append(parentddir)

from torchsample.modules import ModuleTrainer
from torchsample.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from torchsample.metrics import CategoricalAccuracy

from evaluate.pipeline.helpers import train_valid_test_datasets
from evaluate.pipeline.model import ModelNoDict, ModelDict

##### FUNCTIONS #####


def default_config():
    return {'no_shuffle': False,
            'no_checkpoint': False,
            'val_loss_callback': False,
            'epochs': 300,
            'batch_size': 64,
            'validation_size': 0.05,
            'seed': 1234,
            'patience': 10,
            'verbose': 3,
            'plateau_reduce_lr': [4, 0.5],
            'no_cuda': False,
            'num_workers': 0,
            'num_features_range': [4, 100],
            'no_append_weight': False,
            'old_hashembed': False,
            'agg_mode': 'sum',

            'dictionnary': False,
            'no_hashembed': False,
            'ngrams_range': [1, 3],
            'dim': 20,
            'num_buckets': 10**6,
            'num_embeding': 10**7,
            'num_hash': 2,
            'model': 'embed-softmax',
            'experiment': 'custom',
            'dataset': 'ag',
            }


def default_experiment(args):
    if args.experiment == 'custom':
        return args

    defaultsConfig = default_config()
    args.no_shuffle = defaultsConfig['no_shuffle']
    args.no_checkpoint = defaultsConfig['no_checkpoint']
    args.val_loss_callback = defaultsConfig['val_loss_callback']
    args.epochs = defaultsConfig['epochs']
    args.batch_size = defaultsConfig['batch_size']
    args.validation_size = defaultsConfig['validation_size']
    args.seed = defaultsConfig['seed']
    args.patience = defaultsConfig['patience']
    args.verbose = defaultsConfig['verbose']
    args.plateau_reduce_lr = defaultsConfig['plateau_reduce_lr']
    args.no_cuda = defaultsConfig['no_cuda']
    args.num_workers = defaultsConfig['num_workers']
    args.num_features_range = defaultsConfig['num_features_range']
    args.no_append_weight = defaultsConfig['no_append_weight']
    args.old_hashembed = defaultsConfig['old_hashembed']
    args.num_hash = defaultsConfig['num_hash']
    args.agg_mode = defaultsConfig['agg_mode']

    if args.experiment == 'hash-embed-nodict':
        args.dictionnary = False
        args.ngrams_range = [1, 3]
        args.dim = 20
        args.num_buckets = 10**6
        args.num_embeding = 10**7
        args.no_hashembed = False
        args.model = 'embed-softmax'

    elif args.experiment == 'std-embed-nodict':
        args.dictionnary = False
        args.ngrams_range = [1, 3]
        args.dim = 20
        args.num_buckets = 10**6
        args.num_embeding = 10**7
        args.no_hashembed = True
        args.model = 'embed-softmax'

    elif args.experiment == 'std-embed-dict':
        args.dictionnary = True
        args.ngrams_range = [1, 10]
        args.dim = 200
        # cross validate args.num_embeding = [10K, 25K, 50K, 300K, 500K, 1M]
        # args.num_embeding = 25000 # didn't have ime to cv
        args.no_hashembed = True
        args.model = 'embed-3L-softmax'

    elif args.experiment == 'hash-embed-dict':
        args.dictionnary = True
        args.ngrams_range = [1, 10]
        args.dim = 200
        # cross validation for args.num_buckets = [500, 10K, 50K, 100K, 150K]
        # args.num_buckets = 10000 # didn't have ime to cv
        args.num_embeding = 10**6
        args.no_hashembed = False
        args.model = 'embed-3L-softmax'

    elif args.experiment == 'ensemble-hash-embed-dict':
        args.dictionnary = True
        args.ngrams_range = [1, 10]
        args.dim = 200
        args.num_buckets = 50000
        args.num_embeding = 10**6
        args.no_hashembed = True
        args.model = 'ensemble-embed-3L-softmax'

    return args


def parse_arguments():
    """Parses the arguments from the command line."""
    def check_pair(parser, arg, name, types=(int, int)):
        if arg[0] == "None":
            arg = None
        if arg is not None and len(arg) != 2:
            raise parser.error("{} has to be None or of length 2.".format(name))
        if arg is not None:
            try:
                arg[0] = types[0](arg[0])
                arg[1] = types[1](arg[1])
            except ValueError:
                raise parser.error("{} should be of type {}".format(name, types))
        return arg

    defaultsConfig = default_config()
    parser = argparse.ArgumentParser(description="PyTorch implementation and evaluation of HashEmbeddings, which uses multiple hashes to efficiently approximate an Embedding layer.",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Predefined experiments
    experiment = parser.add_argument_group('Predefined experiments')
    experiments = ['custom', 'std-embed-dict', 'hash-embed-dict', 'hash-embed-nodict', 'std-embed-nodict', 'ensemble-hash-embed-dict']
    experiment.add_argument('-x', '--experiment', help='Predefined experiments to run. If different than `custom` then only the dataset argument will be considered.', default=defaultsConfig['experiment'], choices=experiments)

    # Dataset options
    data = parser.add_argument_group('Dataset options')
    datasets = ['ag', 'amazon', 'amazon-polarity', 'dbpedia', 'sogou', 'yahoo', 'yelp', 'yelp-polarity']
    data.add_argument('-d', '--dataset', help='path to training data csv.', default=defaultsConfig['dataset'], choices=datasets)

    # Learning options
    learn = parser.add_argument_group('Learning options')
    learn.add_argument('--no-shuffle', action='store_true', default=defaultsConfig['no_shuffle'], help='Disables shuffling batches when training.')
    learn.add_argument('--no-checkpoint', action='store_true', default=defaultsConfig['no_checkpoint'], help='Disables model checkpoint. I.e saving best model based on validation loss.')
    learn.add_argument('--val-loss-callback', action='store_true', default=defaultsConfig['val_loss_callback'], help='Whether should monitor the callbacks (early stopping ? decrease LR on plateau/ ... on the loss rather than accuracy on validation set.')
    learn.add_argument('-e', '--epochs', type=int, default=defaultsConfig['epochs'], help='Maximum number of epochs to run for.')
    learn.add_argument('-b', '--batch-size', type=int, default=defaultsConfig['batch_size'], help='Batch size for training.')
    learn.add_argument('-v', '--validation-size', type=float, default=defaultsConfig['validation_size'], help='Percentage of training set to use as validation.')
    learn.add_argument('-s', '--seed', type=int, default=defaultsConfig['seed'], help='Random seed.')
    learn.add_argument('-p', '--patience', type=int, default=defaultsConfig['patience'], help='Patience if early stopping. None means no early stopping.')
    learn.add_argument('-V', '--verbose', type=int, default=defaultsConfig['verbose'], help='Verbosity in [0,3].')
    learn.add_argument('-P', '--plateau-reduce-lr', metavar=('PATIENCE', 'FACTOR'), nargs='*', default=defaultsConfig['plateau_reduce_lr'], help='If specified, if loss did not improve since PATIENCE epochs then multiply lr by FACTOR. [None,None] means no reducing of lr on plateau.')

    # Device options
    device = parser.add_argument_group('Device options')
    device.add_argument('--no-cuda', action='store_true', default=defaultsConfig['no_cuda'], help='Disables CUDA training, even when have one.')
    device.add_argument('-w', '--num-workers', type=int, default=defaultsConfig['num_workers'], help='Number of subprocesses used for data loading.')

    # Featurizing options
    feature = parser.add_argument_group('Featurizing options')
    feature.add_argument('--dictionnary', action='store_true', default=defaultsConfig['dictionnary'], help='Uses a dictionnary.')
    feature.add_argument('-g', '--ngrams-range', metavar=('MIN_NGRAM', 'MAX_NGRAM'), nargs='*', default=defaultsConfig['ngrams_range'], help='Range of ngrams to generate. ngrams in [minNgram,maxNgram[.')
    feature.add_argument('-f', '--num-features-range', metavar=('MIN_FATURES', 'MAX_FATURES'), nargs='*', default=defaultsConfig['num_features_range'], help='If specified, during training each phrase will have a random number of features in range [minFeatures,maxFeatures[. None if take all.')

    # Embedding options
    embedding = parser.add_argument_group('Embedding options')
    embedding.add_argument('--no-hashembed', action='store_true', default=defaultsConfig['no_hashembed'], help='Uses the default embedding.')
    embedding.add_argument('--no-append-weight', action='store_true', default=defaultsConfig['no_append_weight'], help='Whether to append the importance parameters.')
    embedding.add_argument('--old-hashembed', action='store_true', default=defaultsConfig['old_hashembed'], help='Uses the paper version of hash embeddings rather than the improved one.')
    embedding.add_argument('-D', '--dim', type=int, default=defaultsConfig['dim'], help='Dimension of word vectors. Higher improves downstream task for fixed vocabulary size.')
    embedding.add_argument('-B', '--num-buckets', type=int, default=defaultsConfig['num_buckets'], help='Number of buckets in the shared embedding table. Higher improves approximation quality.')
    embedding.add_argument('-N', '--num-embeding', type=int, default=defaultsConfig['num_embeding'], help='Number of rows in the importance matrix. Approximate the number of rows in a usual embedding. Higher will increase possible vocabulary size.')
    embedding.add_argument('-H', '--num-hash', type=int, default=defaultsConfig['num_hash'], help='Number of different hashes to use. Higher improves approximation quality.')
    aggModes = ['sum', 'concatenate', 'median']
    embedding.add_argument('-A', '--agg-mode', default=defaultsConfig['agg_mode'], choices=aggModes, help='How to aggregate the different weighted embeddings to make the final one. (weightd) Sum should be the same as making a (weghted) average because learnable weights so can learn to divide by n.')

    # Model options
    model = parser.add_argument_group('Model options')
    models = ['embed-softmax', 'embed-3L-softmax', 'ensemble-embed-3L-softmax']
    model.add_argument('-m', '--model', help='which model to use. Default is a simple softmax.', default=defaultsConfig['model'], choices=models)

    args = parser.parse_args()

    # custom errors
    args.plateau_reduce_lr = check_pair(parser, args.plateau_reduce_lr, "plateau-reduce-lr", types=(int, float))
    args.ngrams_range = check_pair(parser, args.ngrams_range, "ngrams-range")
    feature.num_features_range = check_pair(parser, args.num_features_range, "num-features-range")

    args = default_experiment(args)

    return args

###### MAIN ######


def main(args):
    """Simply redirrcts to the correct function."""
    start = default_timer()

    args.cuda = not args.no_cuda and torch.cuda.is_available()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    print("-------------------------------------------------")
    if args.verbose > 0:
        print("Ran on {}".format(time.strftime("%Y-%m-%d %H:%M")))
        print()

    print('Parameters: {}'.format(vars(args)))
    print()

    # PREPARES DATA
    if args.verbose > 1:
        print('Prepares data ...')
    train, valid, test = train_valid_test_datasets(args.dataset,
                                                   validSize=args.validation_size,
                                                   isHashingTrick=not args.dictionnary,
                                                   nFeaturesRange=args.num_features_range,
                                                   ngramRange=args.ngrams_range,
                                                   seed=args.seed,
                                                   num_words=args.num_embeding,
                                                   specificArgs={'dictionnary': ['num_words']})

    num_classes = len(train.classes)
    train = DataLoader(dataset=train, batch_size=args.batch_size, shuffle=not args.no_shuffle)
    valid = DataLoader(dataset=valid, batch_size=args.batch_size, shuffle=not args.no_shuffle)
    test = DataLoader(dataset=test, batch_size=args.batch_size, shuffle=not args.no_shuffle)

    # PREPARES MODEL
    if args.verbose > 1:
        print('Prepares model ...')

    Model = ModelNoDict if args.model == 'embed-softmax' else ModelDict
    model = Model(args.num_embeding,
                  args.dim,
                  num_classes,
                  isHash=not args.no_hashembed,
                  seed=args.seed,
                  num_buckets=args.num_buckets,
                  append_weight=not args.no_append_weight,
                  aggregation_mode=args.agg_mode,
                  oldAlgorithm=args.old_hashembed)
    if args.cuda:
        model.cuda()

    if args.verbose > 1:
        model_parameters = filter(lambda p: p.requires_grad, model.parameters())
        nParams = sum([np.prod(p.size()) for p in model_parameters])
        print('Num parameters in model: {}'.format(nParams))
        print("Train on {} samples, validate on {} samples".format(len(train), len(valid)))

    # COMPILES
    trainer = ModuleTrainer(model)
    loss = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters())

    callbacks = []
    callbackMetric = "val_loss" if args.val_loss_callback else "val_acc_metric"
    if args.patience is not None:
        callbacks.append(EarlyStopping(patience=args.patience, monitor=callbackMetric))
    if args.plateau_reduce_lr is not None:
        callbacks.append(ReduceLROnPlateau(factor=args.plateau_reduce_lr[1], patience=args.plateau_reduce_lr[0], monitor=callbackMetric))
    if not args.no_checkpoint:
        modelDir = os.path.join(parentddir, 'models')
        filename = "{}.pth.tar".format(args.dataset)
        callbacks.append(ModelCheckpoint(modelDir, filename=filename, save_best_only=True, max_save=1, monitor=callbackMetric))

    metrics = [CategoricalAccuracy()]

    trainer.compile(loss=loss,
                    optimizer=optimizer,
                    callbacks=callbacks,
                    metrics=metrics)

    # TRAINS
    if args.verbose > 1:
        print('Trains ...')
    trainer.fit_loader(train,
                       val_loader=valid,
                       num_epoch=args.epochs,
                       verbose=args.verbose,
                       cuda_device=0 if args.cuda else -1)

    # EVALUATES
    print()
    evalTest = trainer.evaluate_loader(test, verbose=args.verbose, cuda_device=0 if args.cuda else -1)
    evalValid = trainer.evaluate_loader(valid, verbose=args.verbose, cuda_device=0 if args.cuda else -1)
    print("Last Model. Validation - Loss: {}, Accuracy: {}".format(evalValid['val_loss'], evalValid['val_acc_metric']))
    print("Last Model. Test - Loss: {}, Accuracy: {}".format(evalTest['val_loss'], evalTest['val_acc_metric']))

    if not args.no_checkpoint:
        checkpoint = torch.load(os.path.join(modelDir, filename))
        model.load_state_dict(checkpoint["state_dict"])
        evalTest = trainer.evaluate_loader(test, verbose=args.verbose, cuda_device=0 if args.cuda else -1)
        evalValid = trainer.evaluate_loader(valid, verbose=args.verbose, cuda_device=0 if args.cuda else -1)
        print("Best Model. Validation - Loss: {}, Accuracy: {}".format(evalValid['val_loss'], evalValid['val_acc_metric']))
        print("Best Model. Test - Loss: {}, Accuracy: {}".format(evalTest['val_loss'], evalTest['val_acc_metric']))

    if args.verbose > 1:
        print('Finished after {:.1f} min.'.format((default_timer() - start) / 60))


if __name__ == '__main__':
    args = parse_arguments()
    main(args)
