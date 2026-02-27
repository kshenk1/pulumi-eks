# Pulumi project pulumi-eks
In the beginning, this started out with a `pulumi convert ...` my current terraform to pulumi. It did a pretty good job - especially in regards to converting the resources from terraform components to pulumi components. That, and it gave me a decent scaffolding to start working with. What it was _not_ able to convert well automagically were things like flatten, merge etc. Since then, I've added new resources and filled in a lot of gaps I had with my previous setup with terraform.

This was geared towards installing Cloudbees CI, however; most of this is quite foundational and would likely need to take place for any application being served from EKS.

## Requirements
It is assumed that you have `kubectl`, `helm`, `jq`. and `aws` (cli v2) installed locally. If you don't have at least `python 3.12` or greater, install it. We're going to create a virtual environment to run everything in a moment...

# How to make it all go
* [Install Pulumi](https://www.pulumi.com/docs/install/)
* [AWS & Pulumi](https://www.pulumi.com/docs/clouds/aws/get-started/begin/) - _Most of us have this going in our local shells already_
* [Login to Pulumi Cloud](https://app.pulumi.com/signin) - If this is your first time, you may have to create an account. I used GitHub as my signin, therefore:
```
pulumi whoami
kshenk1
```
* First: Login via the CLI: `pulumi login`
* Then, follow the steps below 

```
brew install python@3.12
git clone git@github.com:kshenk1/pulumi-eks.git
cd pulumi-eks
python3.12 -m venv .venv
source .venv/bin/activate{.sh,.zsh,.fish} # whatever suits your shell
pip install -r requirements.txt
```

> [!IMPORTANT]
> The point of the bash helper scripts in here is to pull values together and perform some work for you. The intention is not to "string it all together and make it a one-button-push deployment". The scripts should not get too complicated.
> 
> ### This is an overview of what a typical workflow will look like:

| A - One-time Config | B - Setup/Install | C - Optional ECR Access | D - Teardown |
|---|---|---|---|
| 1. Creating your own Pulumi.you.yaml file | 1. `pulumi up` | 1. `./ecr-access.sh create` | 1. `./install-helper.sh destroy` |
| 2. Setting some initial pulumi values | 2. `./create-helm-values.sh` | | 2. `pulumi destroy` |
| | 3. `./helm-install.sh` | | |
| | 4. `./install-helper.sh create` | | |

## Create Pulumi.${USER}.yaml
```
cp Pulumi.cbci.yaml Pulumi.${USER}.yaml
```
> [!WARNING]
> We use combination of `myip`, `additional_eks_access_cidrs`, and `additional_alb_access_cidrs` to create the security groups allowing access to the EKS Cluster and the ALB so be sure you set these accordingly. Remove them completely if they are not needed (we don't want to leave 0.0.0.0/0 in there).

## Setting some initial Pulumi configuration values
1. Initialize a new stack with your local username
2. By default, the cluster will be locked down. We'll set _your_ ip so you can reach it via kubectl commands.
3. Set the namespace we're going to use. I chose 'core'. It can be whatever you want.
4. Set the version of CI that we want to install later. This makes it so we never have to hard-code th
```
pulumi stack init ${USER}
pulumi config set myip "$(dig +short myip.opendns.com @resolver1.opendns.com)/32"
pulumi config set ci_namespace core
pulumi config set ci_version 3.35786.0+7b6bb59b13c7
```
> [!NOTE]
> These values will be written to `Pulumi.${USER}.yaml`. You can modify the file anyway you like.

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
./install-helper.sh create
```

## Teardown
We need to remove a couple resources before `pulumi destroy` will work.
```
./install-helper.sh destroy
pulumi destroy
```

# Pulling images from ECR for builds
This is typically the next thing you'll want to do once you get moving. The following script will create the iam policy and K8s service account required to make that happen.
```
./ecr-access.sh create
```
> [!NOTE]
> The `install-helper.sh` will run this script with `destroy`, when that argument is given.
