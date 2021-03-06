#!/usr/bin/env bash

cd -P -- "$(dirname -- "$0")"/../

declare -a datasets=('ag' 'dbpedia' 'yelp')

for dataset in "${datasets[@]}"
do
    for i in {1..10}
    do
        seed=$RANDOM

        echo '========================================='

        echo
        echo "Iter = ""$i""; seed = ""$seed"    

        echo
        echo '--- Predict '"$dataset"' with standard hashembedding ---'
        PYTHONHASHSEED=0 python -u evaluate/main.py -d $dataset -s "$seed" --old-hashembed -B 200000 -N 2000000 | tee -a results_distribution.txt

        echo
        echo '--- Predict '"$dataset"' with improved hashembedding ---'
        PYTHONHASHSEED=0 python -u evaluate/main.py -d $dataset -s "$seed" -B 200000 -N 2000000 | tee -a results_distribution.txt
       
        echo
        echo '--- Predict '"$dataset"' without hashembedding ---'
        PYTHONHASHSEED=0 python -u evaluate/main.py -d $dataset -s "$seed" --no-hashembed -B 200000 -N 2000000 | tee -a results_distribution.txt
    done
done

