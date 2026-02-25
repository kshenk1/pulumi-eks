## pulumi config set your ip
pulumi config set myip "$(dig +short myip.opendns.com @resolver1.opendns.com)/32"

## update Pulumi.cbci.yaml

## pulumi up
pulumi up

## install CI
./helm-install.sh

## get alb by dns name
kubectl get ingress -n core -o jsonpath='{.items[*].status.loadBalancer.ingress[*].hostname}'
aws elbv2 describe-load-balancers \
    --query "LoadBalancers[?DNSName=='{{alb_dns_name}}'].[LoadBalancerName,CanonicalHostedZoneId]" \
    --output table

## update dns-update.json

## do the zone
pulumi stack output hosted_zone_id
aws route53 change-resource-record-sets \
  --hosted-zone-id {{hosted_zone_id}}\
  --change-batch file://dns-update.json

