## Requirements
It is assumed that you have `kubectl`, `helm`, and `aws` (cli v2) installed locally. If you don't have at least `python 3.12` or greater, install it. We're going to create a virtual environment to run everything - activate the venv and install our requirements.
```
pip install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate{.sh,.zsh,.fish} # whatever suits your shell
pip install -r requirements.txt
```

## Setting some initial configuration values
1. Initialize a new stack with your local username
2. By default, the cluster will be locked down. We'll set _your_ ip so you can reach it via kubectl commands.
3. Set the namespace we're going to use. I chose 'core'. It can be whatever you want.
```
pulumi stack init ${USER}
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

## Create Infrastructure
```
pulumi preview
pulumi up
```

## Create Helm values for CI & Install
Create your own **helm** values from `support/ci-example-values.yaml` with the following script. _This should be considered a starting point._
```
./create-helm-values.sh
```
Once you are satisfied with `support/${USER}-values.yaml`...
```
./helm-install.sh
```

## Finish Infrastructure Setup
> [!NOTE]
> We will be using Subdomains for controllers. Because of this, we need the ALB DNS Name in order to create a * A-Record so all requests end up on the same LB. The CI application knows how to route once traffic gets there.
> This creates a wildcard Route53 DNS record pointing to the LB created by the aws-load-balancer-controller in K8s, gathering up the data so you don't have to..
```
./finish-setup.sh
```

# Teardown
## Why scripted?
We need to remove a couple resources before `pulumi destroy` will work.
```
./before-destroy.sh
pulumi destroy
```