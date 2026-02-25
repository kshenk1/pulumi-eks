## Python >=3.12
```
pip install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate{.sh,.zsh,.fish} # whatever suits your shell
pip install -r requirements.txt
```

## pulumi config set your ip
```
pulumi config set myip "$(dig +short myip.opendns.com @resolver1.opendns.com)/32"
```

## update Pulumi.cbci.yaml

## pulumi up
```
pulumi up
```

## install CI
```
./helm-install.sh
```

## get alb by dns name
> [!NOTE]
> `fish` shell users will need to use the 'set varname value' syntax.
> This was written to support the standard bash shell
```
alb_dns_name="$(kubectl get ingress -n core -o jsonpath='{.items[*].status.loadBalancer.ingress[*].hostname}')"
canonical_zone_id="$(aws elbv2 describe-load-balancers \
    --query "LoadBalancers[?DNSName=='$alb_dns_name'].[CanonicalHostedZoneId]" \
    --output text)"
```

## update dns-update.json
using the $canonical_zone_id and $alb_dns_name

## do the zone
```
hosted_zone_id="$(pulumi stack output hosted_zone_id)"

aws route53 change-resource-record-sets \
    --hosted-zone-id $hosted_zone_id \
    --change-batch file://dns-update.json
```

# Teardown
## delete the A-record we created outside of pulumi
Change Action to DELETE and EvaluateTargetHealth to False
```
aws route53 change-resource-record-sets \
    --hosted-zone-id $hosted_zone_id \
    --change-batch file://dns-update.json
```