#!/usr/bin/env bash

export alb_dns_name="$(kubectl get ingress -n core -o jsonpath='{.items[*].status.loadBalancer.ingress[*].hostname}')"
export action="DELETE"
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

namespace="$(pulumi config get ci_namespace)"
helm uninstall cloudbees-ci -n $namespace
kubectl delete ns $namespace
