#!/usr/bin/env bash

namespace="core"
values="kshenk-values.yaml"
timeout="10000s"
version="3.35786.0+7b6bb59b13c7"

helm upgrade \
    -i cloudbees-ci cloudbees/cloudbees-core \
    -n $namespace \
    -f $values \
    --version $version \
    --timeout $timeout
