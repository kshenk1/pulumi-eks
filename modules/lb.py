import json
import pulumi
import base64
from pulumi import Input
from typing import Optional, TypedDict
import pulumi_aws as aws
import pulumi_kubernetes as k8s
import pulumi_tls as tls


class LBArgs(TypedDict, total=False):
    resource_prefix: Input[str]
    oidc_provider_arn: Input[str]
    oidc_provider_url: Input[str]
    cluster_name: Input[str]

class LoadBalancer(pulumi.ComponentResource):
    def __init__(self, k8s_provider: k8s.Provider, stepparent: object, name: str, args: LBArgs, opts:Optional[pulumi.ResourceOptions] = None):
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
            opts=pulumi.ResourceOptions(parent=self)
        )

        sa_name = "aws-load-balancer-controller"
        sa_namespace = "kube-system"

        # Note: In production, use the official fine-grained policy from
        # https://raw.githubusercontent.com/kubernetes-sigs/aws-load-balancer-controller/main/docs/install/iam_policy.json

        with open("iam_policy.json") as f:
            lb_policy_json = f.read()

        alb_policy = aws.iam.Policy(f"{name}-alb-policy",
            description="IAM policy for AWS Load Balancer Controller",
            policy=lb_policy_json,
            opts=pulumi.ResourceOptions(parent=self)
        )
        aws.iam.RolePolicyAttachment(f"{name}-alb-policy-attachment",
            role=lb_controller_role.name,
            policy_arn=alb_policy.arn,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # 3. Kubernetes service account annotated with the role ARN
        lb_sa = k8s.core.v1.ServiceAccount(f"{name}-sa",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=sa_name,
                namespace=sa_namespace,
                annotations={
                    "eks.amazonaws.com/role-arn": lb_controller_role.arn,
                },
            ),
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[stepparent])
        )

        # If we allow the chart to create the TLS certs, they will be regenerated on every update, 
        # causing unnecessary LB controller restarts.
        local_tls = Tls(stepparent, f"{name}-tls", {
            "sa_namespace": sa_namespace,
        })

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
                "webhook": {
                    "certManager": {
                        "enabled": False,
                    },
                    "caBundle": local_tls.ca_bundle,
                    "tlsSecret": local_tls.secret_name,
                    "certSecretAnnotations": {
                        "pulumi.com/patchForce": "true",
                    },
                },
            },
            opts=pulumi.ResourceOptions(parent=self, provider=k8s_provider, depends_on=[lb_sa, local_tls])
        )

        self.lb_controller_role_arn = lb_controller_role.arn
        self.service_account_name = sa_name

        self.register_outputs({
            "lb_controller_role_arn": self.lb_controller_role_arn,
            "service_account_name": self.service_account_name,
        })

class TlsArgs(TypedDict, total=False):
    sa_namespace: Input[str]

class Tls(pulumi.ComponentResource):
    def __init__(self, stepparent: object, name: str, args: TlsArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Tls", name, args, opts)

        # Create a stable private key for the CA (stored in state, never regenerated)
        ca_key = tls.PrivateKey(f"{name}-ca-key",
            algorithm="RSA",
            rsa_bits=2048,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a stable private key for the server cert
        server_key = tls.PrivateKey(f"{name}-server-key",
            algorithm="RSA",
            rsa_bits=2048,
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a self-signed CA certificate
        ca_cert = tls.SelfSignedCert(f"{name}-ca-cert",
            private_key_pem=ca_key.private_key_pem,
            is_ca_certificate=True,
            validity_period_hours=87600,  # 10 years
            allowed_uses=[
                "cert_signing",
                "key_encipherment",
                "digital_signature",
            ],
            subject=tls.SelfSignedCertSubjectArgs(
                common_name="aws-load-balancer-controller-ca",
            ),
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Create a CSR for the server cert
        server_csr = tls.CertRequest(f"{name}-server-csr",
            private_key_pem=server_key.private_key_pem,
            subject=tls.CertRequestSubjectArgs(
                common_name="aws-load-balancer-webhook",
            ),
            dns_names=[
                "aws-load-balancer-webhook-service",
                f"aws-load-balancer-webhook-service.{args['sa_namespace']}",
                f"aws-load-balancer-webhook-service.{args['sa_namespace']}.svc",
            ],
            opts=pulumi.ResourceOptions(parent=self)
        )

        # Sign the server cert with the CA
        server_cert = tls.LocallySignedCert(f"{name}-server-cert",
            cert_request_pem=server_csr.cert_request_pem,
            ca_private_key_pem=ca_key.private_key_pem,
            ca_cert_pem=ca_cert.cert_pem,
            validity_period_hours=87600,  # 10 years
            allowed_uses=[
                "key_encipherment",
                "digital_signature",
                "server_auth",
            ],
            opts=pulumi.ResourceOptions(parent=self)
        )

        self.secret_name = "aws-load-balancer-tls-ci"

        def skip_tls_secret(args):
            if args.type_ == "kubernetes:core/v1:Secret" and "aws-load-balancer-tls" in args.name:
                return None  # skip this resource
            return args

        # Create the TLS secret with stable cert/key data
        tls_secret = k8s.core.v1.Secret(f"{name}-alb-tls-ci",
            metadata=k8s.meta.v1.ObjectMetaArgs(
                name=self.secret_name,
                namespace=args['sa_namespace']
            ),
            type="kubernetes.io/tls",
            string_data={
                "tls.crt": server_cert.cert_pem,
                "tls.key": server_key.private_key_pem,
                "ca.crt": ca_cert.cert_pem,
            },
            opts=pulumi.ResourceOptions(parent=self, depends_on=[stepparent], transformations=[skip_tls_secret])
        )

        # Pass the CA bundle to the Helm chart so webhooks use it
        ca_bundle = ca_cert.cert_pem.apply(
            lambda pem: base64.b64encode(pem.encode()).decode()
        )

        self.ca_bundle = ca_bundle

        self.register_outputs({
            "ca_bundle": self.ca_bundle,
            "secret_name": self.secret_name,
        })
