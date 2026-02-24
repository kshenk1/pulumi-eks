import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import json
import pulumi_aws as aws
import pulumi_std as std

class EksArgs(TypedDict):
    cluster_name: Input[Any]
    k8s_version: Input[Any]
    k8s_upgrade_policy: Input[Any]
    vpc_id: Input[Any]
    private_subnet_ids: Input[Any]
    vpc_cidr: Input[Any]
    enable_private_access: Input[Any]
    enable_public_access: Input[Any]
    public_access_cidrs: Input[Any]

class Eks(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: EksArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Eks", name, args, opts)

        current = aws.get_caller_identity_output()

        main_cluster = aws.iam.Role(f"{name}-main-cluster",
            name=f"{args['cluster_name']}_role",
            assume_role_policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "eks.amazonaws.com",
                    },
                    "Action": "sts:AssumeRole",
                }],
            }),
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        # Cluster Policy Attachment
        cluster__amazon_eks_cluster_policy = aws.iam.RolePolicyAttachment(f"{name}-cluster-AmazonEKSClusterPolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            role=main_cluster.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        # Service Policy Attachment
        cluster__amazon_eks_service_policy = aws.iam.RolePolicyAttachment(f"{name}-cluster-AmazonEKSServicePolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
            role=main_cluster.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        eks_sg = aws.ec2.SecurityGroup(f"{name}-eks_sg",
            name=f"{args['cluster_name']}_eks_sg",
            description="Cluster communication with worker nodes",
            vpc_id=args["vpc_id"],
            ingress=[{
                "from_port": 0,
                "to_port": 0,
                "protocol": "-1",
                "cidr_blocks": [args["vpc_cidr"]],
            }],
            egress=[{
                "from_port": 0,
                "to_port": 0,
                "protocol": "-1",
                "cidr_blocks": ["0.0.0.0/0"],
            }],
            tags={
                "Name": f"{args['cluster_name']}_eks_sg",
            },
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        main = aws.eks.Cluster(f"{name}-main",
            name=args["cluster_name"],
            version=args["k8s_version"],
            role_arn=main_cluster.arn,
            vpc_config={
                "security_group_ids": [eks_sg.id],
                "subnet_ids": args["private_subnet_ids"],
                "endpoint_private_access": args["enable_private_access"],
                "endpoint_public_access": args["enable_public_access"],
                "public_access_cidrs": args["public_access_cidrs"],
            },
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        assume_role_policy = pulumi.Output.all(
            account_id=current.account_id,
            oidc_issuer=std.replace_output(
                text=main.identities[0].oidcs[0].issuer,
                search="https://",
                replace=""
            ),
        ).apply(lambda _args: json.dumps({
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com",
                    },
                    "Action": "sts:AssumeRole",
                },
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Federated": f"arn:aws:iam::{_args[0]}:oidc-provider/{_args[1]}",
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{_args[1]}:aud": "sts.amazonaws.com",
                            f"{_args[1]}:sub": "system:serviceaccount:kube-system:ebs-csi-controller-sa",
                        },
                    },
                },
            ],
        }))


        eks_nodes = aws.iam.Role(f"{name}-eks_nodes",
            name=f"{args['cluster_name']}-eks-node-group",
            assume_role_policy=assume_role_policy,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_ebscsi_driver_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEBSCSIDriverPolicy",
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_eks_worker_node_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEKSWorkerNodePolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_ekscni_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEKS_CNI_Policy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_ec2_container_registry_read_only = aws.iam.RolePolicyAttachment(f"{name}-AmazonEC2ContainerRegistryReadOnly",
            policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_ssm_managed_instance_core = aws.iam.RolePolicyAttachment(f"{name}-AmazonSSMManagedInstanceCore",
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        autoscaling = aws.iam.Policy(f"{name}-autoscaling",
            name=f"{args['cluster_name']}-autoscaling",
            description="policy to enable autoscaling",
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Action": [
                        "autoscaling:DescribeAutoScalingGroups",
                        "autoscaling:DescribeAutoScalingInstances",
                        "autoscaling:DescribeLaunchConfigurations",
                        "autoscaling:DescribeTags",
                        "autoscaling:SetDesiredCapacity",
                        "autoscaling:TerminateInstanceInAutoScalingGroup",
                        "ec2:DescribeLaunchTemplateVersions",
                    ],
                    "Effect": "Allow",
                    "Resource": "*",
                }],
            }),
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        autoscaler = aws.iam.RolePolicyAttachment(f"{name}-autoscaler",
            policy_arn=autoscaling.arn,
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        amazon_eksefscsi_driver_policy = aws.iam.Policy(f"{name}-AmazonEKS_EFS_CSI_Driver_Policy",
            name=f"{args['cluster_name']}-efs-csi-driver-policy",
            description="policy to enable efs-csi",
            policy=json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "elasticfilesystem:DescribeAccessPoints",
                            "elasticfilesystem:DescribeFileSystems",
                            "elasticfilesystem:DescribeMountTargets",
                        ],
                        "Resource": "*",
                    },
                    {
                        "Effect": "Allow",
                        "Action": ["elasticfilesystem:CreateAccessPoint"],
                        "Resource": "*",
                        "Condition": {
                            "StringLike": {
                                "aws:RequestTag/efs.csi.aws.com/cluster": "true",
                            },
                        },
                    },
                    {
                        "Effect": "Allow",
                        "Action": "elasticfilesystem:DeleteAccessPoint",
                        "Resource": "*",
                        "Condition": {
                            "StringEquals": {
                                "aws:ResourceTag/efs.csi.aws.com/cluster": "true",
                            },
                        },
                    },
                ],
            }),
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        efs_driver_attachment = aws.iam.RolePolicyAttachment(f"{name}-efs-driver-attachment",
            policy_arn=amazon_eksefscsi_driver_policy.arn,
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        oidc_issuer_url = main.identities[0].oidcs[0].issuer

        # Fetch the TLS thumbprint (required for the OIDC provider)
        tls_cert = aws.tls.get_certificate_output(url=oidc_issuer_url)

        oidc_provider = aws.iam.OpenIdConnectProvider(f"{name}-oidc-provider",
            client_id_lists=["sts.amazonaws.com"],
            thumbprint_lists=[tls_cert.certificates[0].sha1_fingerprint],
            url=oidc_issuer_url,
        )

        # Strip the "https://" to get the bare URL for the provider
        self.oidc_provider_url = oidc_issuer_url.apply(lambda url: url.replace("https://", ""))
        self.oidc_provider_arn = oidc_provider.arn

        self.aws_iam_role_node_id = eks_nodes.id
        self.aws_iam_role_node_arn = eks_nodes.arn
        self.eks_node_role = eks_nodes
        self.eks_cluster_role_name = main_cluster.name
        self.eks_endpoint = main.endpoint
        
        self.status = main.status
        self.cluster_id = main.id
        self.cluster_name = main.name
        self.eks_security_group = eks_sg.id
        self.register_outputs({
            'aws_iam_role_node_id': eks_nodes.id, 
            'aws_iam_role_node_arn': eks_nodes.arn, 
            'eks_node_role': eks_nodes, 
            'eks_cluster_role_name': main_cluster.name, 
            'eks_endpoint': main.endpoint, 
            'status': main.status, 
            'cluster_id': main.id, 
            'cluster_name': main.name, 
            'eks_security_group': eks_sg.id,
            'oidc_provider_arn': self.oidc_provider_arn,
            'oidc_provider_url': self.oidc_provider_url,
        })