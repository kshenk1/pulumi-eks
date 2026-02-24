import json
import pulumi
from pulumi import Input
from typing import Optional, TypedDict
import pulumi_aws as aws
import pulumi_kubernetes as k8s

# Grab the OIDC provider from your EKS cluster
# (if using pulumi_eks, this is available as cluster.core.oidc_provider)
# oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-west-2.amazonaws.com/id/EXAMPLE"
# oidc_provider_url = "oidc.eks.us-west-2.amazonaws.com/id/EXAMPLE"

class LBArgs(TypedDict, total=False):
    resource_prefix: Input[str]
    oidc_provider_arn: Input[str]
    oidc_provider_url: Input[str]
    cluster_name: Input[str]

class LoadBalancer(pulumi.ComponentResource):
    def __init__(self, name: str, args: LBArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:LoadBalancer", name, args, opts)

        # 1. IAM role with OIDC trust policy
        lb_controller_role = aws.iam.Role(f"{name}-role",
            assume_role_policy=pulumi.Output.all(args["oidc_provider_arn"], args["oidc_provider_url"]).apply(
                lambda _args: json.dumps({
                    "Version": "2012-10-17",
                    "Statement": [{
                        "Effect": "Allow",
                        "Principal": {"Federated": _args[0]},
                        "Action": "sts:AssumeRoleWithWebIdentity",
                        "Condition": {
                            "StringEquals": {
                                f"{_args[1]}:sub": "system:serviceaccount:kube-system:aws-load-balancer-controller",
                                f"{_args[1]}:aud": "sts.amazonaws.com",
                            }
                        },
                    }],
                })
            ),
        )

        sa_name = "aws-load-balancer-controller"
        sa_namespace = "kube-system"

        # 2. Attach the AWS-managed policy for the LB controller
        aws.iam.RolePolicyAttachment(f"{name}-policy",
            role=lb_controller_role.name,
            policy_arn="arn:aws:iam::aws:policy/ElasticLoadBalancingFullAccess",
        )
        # Note: In production, use the official fine-grained policy from
        # https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

        # 3. Kubernetes service account annotated with the role ARN
        lb_sa = k8s.core.v1.ServiceAccount(f"{name}-sa",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=sa_name,
                namespace=sa_namespace,
                annotations={
                    "eks.amazonaws.com/role-arn": lb_controller_role.arn,
                },
            ),
        )

        alb_controller = k8s.helm.v4.Chart(f"{name}-chart",
            chart="aws-load-balancer-controller",
            repository_opts=k8s.helm.v4.RepositoryOptsArgs(
                repo="https://aws.github.io/eks-charts",
            ),
            namespace=sa_namespace,
            values={
                "clusterName": args["cluster_name"],
                "serviceAccount": {
                    "create": False,  # We created it above
                    "name": sa_name,
                },
            },
        )

        self.register_outputs({
            "lb_controller_role_arn": lb_controller_role.arn,
            "service_account_name": sa_name,
        })
