#!/usr/bin/env bash

set -eo pipefail

declare -a valid_actions=(create delete)

action="$1"; shift

[[ -z "$action" ]] && echo "Missing action" >&2 && exit 1

list_str=" ${valid_actions[*]} "

[[ "$list_str" == "${list_str/ $action /}" ]] && {
    echo "Error: '$action' is invalid. Use one of: ${valid_actions[*]}" >&2 && exit 1
}

resource_prefix="$(pulumi config get resource_prefix)"
ci_namespace="$(pulumi config get ci_namespace)"
cluster_name=$resource_prefix

policy_name="${resource_prefix}-${ci_namespace}-ECRPullAccess"
policy_file="support/ecr-pull-policy.json"
eks_sa_name="ci-pull-images"
agent_namespace="${ci_namespace}-builds"
aws_account_id="$(aws sts get-caller-identity --query Account --output text)"
policy_arn="arn:aws:iam::$aws_account_id:policy/$policy_name"

aws iam get-policy --policy-arn $policy_arn > /dev/null 2>&1
policy_exists="$?"

[[ "$action" = "create" ]] && {
    [[ "$policy_exists" -eq 0 ]] && {
        echo "Warning: IAM Policy $policy_arn already exists"
        echo "This was probably already ran..."
        exit 0
    }
    echo "Creating iam policy $policy_name ..."
    aws iam create-policy \
        --policy-name $policy_name \
        --policy-document file://$policy_file

    echo "Creating iam service account $eks_sa_name ..."
    eksctl create iamserviceaccount \
        --name $eks_sa_name \
        --namespace $agent_namespace \
        --cluster $cluster_name \
        --attach-policy-arn $policy_arn \
        --approve \
        --override-existing-serviceaccounts
}

[[ "$action" = "delete" ]] && {
    [[ "$policy_exists" -gt 0 ]] && {
        echo "Warning: IAM Policy $policy_arn does NOT exist"
        exit 0
    }
    echo "Deleting iam service account $eks_sa_name ..."
    eksctl delete iamserviceaccount \
        --name $eks_sa_name \
        --namespace $agent_namespace \
        --cluster $cluster_name \
        --wait

    echo "Deleting iam policy $policy_name"
    aws iam delete-policy --policy-arn $policy_arn
}
