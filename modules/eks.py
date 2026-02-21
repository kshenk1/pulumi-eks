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
    vpcid: Input[Any]
    private_subnet_ids: Input[Any]
    vpc_cidr: Input[Any]
    enable_private_access: Input[Any]
    enable_public_access: Input[Any]
    public_access_cidrs: Input[Any]

class Eks(pulumi.ComponentResource):
    def __init__(self, name: str, args: EksArgs, opts:Optional[pulumi.ResourceOptions] = None):
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
            opts = pulumi.ResourceOptions(parent=self))

        # Cluster Policy Attachment
        cluster__amazon_eks_cluster_policy = aws.iam.RolePolicyAttachment(f"{name}-cluster-AmazonEKSClusterPolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSClusterPolicy",
            role=main_cluster.name,
            opts = pulumi.ResourceOptions(parent=self))

        # Service Policy Attachment
        cluster__amazon_eks_service_policy = aws.iam.RolePolicyAttachment(f"{name}-cluster-AmazonEKSServicePolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSServicePolicy",
            role=main_cluster.name,
            opts = pulumi.ResourceOptions(parent=self))

        eks_sg = aws.ec2.SecurityGroup(f"{name}-eks_sg",
            name=f"{args['cluster_name']}_eks_sg",
            description="Cluster communication with worker nodes",
            vpc_id=args["vpcid"],
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
            opts = pulumi.ResourceOptions(parent=self))

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
            opts = pulumi.ResourceOptions(parent=self))

        assume_role_policy = pulumi.Output.all(
            account_id=current.account_id,
            oidc_issuer=std.replace_output(
                text=main.identities[0].oidcs[0].issuer,
                search="https://",
                replace=""
            ),
        ).apply(lambda args: json.dumps({
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
                        "Federated": f"arn:aws:iam::{args['account_id']}:oidc-provider/{args['oidc_issuer'].result}",
                    },
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{args['oidc_issuer'].result}:aud": "sts.amazonaws.com",
                            f"{args['oidc_issuer'].result}:sub": "system:serviceaccount:kube-system:ebs-csi-controller-sa",
                        },
                    },
                },
            ],
        }))


        eks_nodes = aws.iam.Role(f"{name}-eks_nodes",
            name=f"{args['cluster_name']}-eks-node-group",
            assume_role_policy=assume_role_policy,
            opts = pulumi.ResourceOptions(parent=self))

        amazon_ebscsi_driver_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEBSCSIDriverPolicy",
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

        amazon_eks_worker_node_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEKSWorkerNodePolicy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

        amazon_ekscni_policy = aws.iam.RolePolicyAttachment(f"{name}-AmazonEKS_CNI_Policy",
            policy_arn="arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

        amazon_ec2_container_registry_read_only = aws.iam.RolePolicyAttachment(f"{name}-AmazonEC2ContainerRegistryReadOnly",
            policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

        amazon_ssm_managed_instance_core = aws.iam.RolePolicyAttachment(f"{name}-AmazonSSMManagedInstanceCore",
            policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

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
            opts = pulumi.ResourceOptions(parent=self))

        autoscaler = aws.iam.RolePolicyAttachment(f"{name}-autoscaler",
            policy_arn=autoscaling.arn,
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

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
            opts = pulumi.ResourceOptions(parent=self))

        efs_driver_attachment = aws.iam.RolePolicyAttachment(f"{name}-efs-driver-attachment",
            policy_arn=amazon_eksefscsi_driver_policy.arn,
            role=eks_nodes.name,
            opts = pulumi.ResourceOptions(parent=self))

        self.awsIamRoleNodeId = eks_nodes.id
        self.awsIamRoleNodeArn = eks_nodes.arn
        self.eks_node_role = eks_nodes
        self.eks_cluster_role_name = main_cluster.name
        self.eksEp = main.endpoint
        self.policyAttachmentAmazonEKSWorkerNodePolicy = amazon_eks_worker_node_policy
        self.policyAttachmentAmazonEKSCNIPolicy = amazon_ekscni_policy
        self.policyAttachmentAmazonEC2ContainerRegistryReadOnly = amazon_ec2_container_registry_read_only
        self.policyAttachmentAmazonSSMManagedInstanceCore = amazon_ssm_managed_instance_core
        self.status = main.status
        self.clusterId = main.id
        self.cluster_name = main.name
        self.eks_security_group = eks_sg.id
        self.register_outputs({
            'awsIamRoleNodeId': eks_nodes.id, 
            'awsIamRoleNodeArn': eks_nodes.arn, 
            'eks_node_role': eks_nodes, 
            'eks_cluster_role_name': main_cluster.name, 
            'eksEp': main.endpoint, 
            'policyAttachmentAmazonEKSWorkerNodePolicy': amazon_eks_worker_node_policy, 
            'policyAttachmentAmazonEKSCNIPolicy': amazon_ekscni_policy, 
            'policyAttachmentAmazonEC2ContainerRegistryReadOnly': amazon_ec2_container_registry_read_only, 
            'policyAttachmentAmazonSSMManagedInstanceCore': amazon_ssm_managed_instance_core, 
            'status': main.status, 
            'clusterId': main.id, 
            'cluster_name': main.name, 
            'eks_security_group': eks_sg.id
        })