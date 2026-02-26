## Requirements
It is assumed that you have `kubectl`, `helm`, and `aws` (cli v2) installed locally. If you don't have at least `python 3.12` or greater, install it. We're going to create a virtual environment to run everything - activate the venv and install our requirements.
```
pip install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate{.sh,.zsh,.fish} # whatever suits your shell
pip install -r requirements.txt
```

## Access to the EKS Cluster
By default, the cluster will be locked down. We'll set _your_ ip so you can reach it via kubectl commands.
```
pulumi config set myip "$(dig +short myip.opendns.com @resolver1.opendns.com)/32"
pulumi config set ci_namespace core
```
> [!NOTE]
> These values will be written to `Pulumi.${USER}.yaml`. If it doesn't exist, it will be created. If it exists, values you set will be added to this file.

## Local Configuration
Have a look at `Pulumi.cbci.yaml`. This is what's available to tweak. These are all default values and exist in Pulumi ESC. Add the following to the top of your `Pulumi.${USER}.yaml` to pull in those default values:
```
environment:
  - pulumi-eks/cbci
```
This looks for a cbci environment configuration for the **pulumi-eks** project. Anything you want to override you need to add to your `Pulumi.${USER}.yaml`.

## pulumi up
```
pulumi preview
pulumi up
```

## install CI
Create your own **helm** values from `support/ci-example-values.yaml` with the following script. _This should be considered a starting point._
```
./create-helm-values.sh
```
Once you are satisfied with `support/${USER}-values.yaml`...
```
./helm-install.sh
```

## get alb by dns name
> [!NOTE]
> This creates a wildcard Route53 DNS record pointing to the LB created by the aws-load-balancer-controller in K8s
```
./finish-setup.sh
```

# Teardown
## delete the A-record we created outside of pulumi
Change Action to DELETE
```
aws route53 change-resource-record-sets \
    --hosted-zone-id $hosted_zone_id \
    --change-batch file://support/dns-update.json
```