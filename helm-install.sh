#!/usr/bin/env bash

namespace="$(pulumi config get ci_namespace)"
values="support/${USER}-values.yaml"
timeout="10000s"
version="$(pulumi config get ci_version)"

[[ -z "$version" ]] && {
    echo "Cannot find ci_version in pulumi config. Please run 'pulumi config set ci_version the.chart.version' and try again." >&2
    exit 1
}

kubectl get ns $namespace > /dev/null 2>&1 || kubectl create ns $namespace

helm upgrade \
    -i cloudbees-ci cloudbees/cloudbees-core \
    -n $namespace \
    -f $values \
    --version $version \
    --timeout $timeout
