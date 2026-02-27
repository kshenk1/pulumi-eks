#!/usr/bin/env bash

set -eo pipefail

declare -a valid_actions=(create delete)

script_action="$1"; shift

[[ -z "$script_action" ]] && echo "Missing action" >&2 && exit 1

list_str=" ${valid_actions[*]} "

[[ "$list_str" == "${list_str/ $script_action /}" ]] && {
    echo "Error: '$script_action' is invalid. Use one of: ${valid_actions[*]}" >&2 && exit 1
}

[[ "$script_action" = "delete" ]] && {
    [[ -x "ecr-access.sh" ]] && {
        echo "Running 'ecr-access.sh delete' first..."
        ./ecr-access delete
    }
}

timeout="180" # 3 minutes
interval="5"
elapsed="0"
_alb_dns_name=""

# This is here for on create. Right after helm install, it might take a couple seconds to a minute for this to show up.
# on "destroy", it'll already be there and we'll just get the name and move past looping.
while [[ -z "$_alb_dns_name" && $elapsed -lt $timeout ]]; do
    _alb_dns_name="$(kubectl get ingress -n core -o jsonpath='{.items[*].status.loadBalancer.ingress[*].hostname}')"
    if [[ -z "$_alb_dns_name" ]]; then
        remaining=$((timeout - elapsed))
        echo -en "Waiting for ALB DNS name to be available... (${remaining}s remaining) \r"
        sleep $interval
        elapsed=$((elapsed + interval))
    fi
done

[[ -z "$_alb_dns_name" ]] && { 
    echo "Error: ALB DNS name not available after $timeout seconds." >&2 && exit 1
}

[[ "$script_action" = "create" ]] && {
    export action="UPSERT"
} || {
    export action="DELETE"
}

export alb_dns_name=$_alb_dns_name
export hosted_zone_name="$(pulumi stack output zone_name)"
export canonical_zone_id="$(aws elbv2 describe-load-balancers \
    --query "LoadBalancers[?DNSName=='$alb_dns_name'].[CanonicalHostedZoneId]" \
    --output text)"
hosted_zone_id="$(pulumi stack output hosted_zone_id)"

echo "           ACTION: $action"
echo " hosted_zone_name: $hosted_zone_name"
echo "   hosted_zone_id: $hosted_zone_id"
echo "     alb_dns_name: $alb_dns_name"
echo "canonical_zone_id: $canonical_zone_id"

## update dns-update.json
envsubst < support/dns-update.json.template > support/dns-update.json

## do the zone update
aws route53 change-resource-record-sets \
    --hosted-zone-id $hosted_zone_id \
    --change-batch file://support/dns-update.json

[[ "$script_action" = "delete" ]] && {
    namespace="$(pulumi config get ci_namespace)"
    helm uninstall cloudbees-ci -n $namespace
    kubectl delete ns $namespace
} || {
    echo "Finished DNS update. Please allow a few minutes for propagation before accessing $hosted_zone_name"
}
