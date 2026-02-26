import pulumi
import json
from modules.efs import Efs
from modules.eks import Eks
from modules.eks_nodes_ec2 import EksNodesEc2
from modules.vpc import Vpc
from modules.route53 import Route53
from modules.lb import LoadBalancer
from modules.eks_addons import EfsAddon
import pulumi_aws as aws
# import pulumi_command as command
# import pulumi_null as null
import pulumi_std as std
import pulumi_kubernetes as k8s

def die(msg):
    raise Exception(msg)

config = pulumi.Config()

###################################################################################################
## Required Settings
###################################################################################################
resource_prefix                 = config.require("resource_prefix")
vpc_cidr_block                  = config.require("vpc_cidr_block")
kubernetes_version              = config.require("kubernetes_version")
eks_node_group_instance_types   = config.require_object("eks_node_group_instance_types")
zone_name                       = config.require("zone_name")
storage_class_name              = config.require("storage_class_name")

pulumi.export("resource_prefix", resource_prefix)

# The number of PUBLIC subnets to create
public_subnet_count = config.get_int("public_subnet_count")
if public_subnet_count is None:
    public_subnet_count = 2

# The number of PRIVATE subnets to create. This also current dictates the number of node-groups created for the cluster - 1 per private subnet.
private_subnet_count = config.get_int("private_subnet_count")
if private_subnet_count is None:
    private_subnet_count = 1

common_tags = config.get_object("common_tags")
if common_tags is None:
    common_tags = {
        "cb-environment": "development",
        "cb-expiry": "2027-2-30",
        "cb-owner": "professional-services",
        "cb-purpose": "local testing cluster",
        "cb-user": "kshenk",
    }

kubernetes_upgrade_policy = config.get("kubernetes_upgrade_policy")
if kubernetes_upgrade_policy is None:
    kubernetes_upgrade_policy = "STANDARD"

eks_instance_min_vcpu = config.get_int("eks_instance_min_vcpu")
if eks_instance_min_vcpu is None:
    eks_instance_min_vcpu = 1

# This is the min memory (mib) for any instance participating in a node group/autoscaling group
eks_instance_min_mem = config.get_int("eks_instance_min_mem")
if eks_instance_min_mem is None:
    eks_instance_min_mem = 4096

# How many nodes should exist in each nodegroup created
eks_nodes_per_nodegroup = config.get_int("eks_nodes_per_nodegroup")
if eks_nodes_per_nodegroup is None:
    eks_nodes_per_nodegroup = 1

# Maximum nodes that should exist in each nodegroup created
eks_max_nodes_per_nodegroup = config.get_int("eks_max_nodes_per_nodegroup")
if eks_max_nodes_per_nodegroup is None:
    eks_max_nodes_per_nodegroup = 10

create_alb_controller = config.get_bool("create_alb_controller") or False
create_eks_cluster = config.get_bool("create_eks_cluster") or False
create_efs_filesystem = config.get_bool("create_efs_filesystem") or False
create_asg_schedule = config.get_bool("create_asg_schedule") or False
create_r53_zone = config.get_bool("create_r53_zone") or False
route53_wait_for_validation = config.get_bool("route53_wait_for_validation") or False

cluster_enable_private_access = config.get_bool("cluster_enable_private_access")
cluster_enable_public_access = config.get_bool("cluster_enable_public_access")

# You typically want YOUR local IP address in here at the least.
cluster_access_cidrs = [config.get("myip")]

asg_schedule = config.get_object("asg_schedule")
if create_asg_schedule is not True:
    pulumi.info("AutoScaling Group Schedules not enabled")

if eks_max_nodes_per_nodegroup < eks_nodes_per_nodegroup and eks_nodes_per_nodegroup > 0:
    die("eks_max_nodes_per_nodegroup must be greater than eks_nodes_per_nodegroup!")

if create_alb_controller and not create_eks_cluster:
    die("create_eks_cluster must be true if create_alb_controller is true")

available = aws.get_availability_zones_output()

aws_provider = aws.Provider("aws-provider",
    default_tags=aws.ProviderDefaultTagsArgs(
        tags=common_tags
    )
)

###################################################################################################
## Creating resources
###################################################################################################
## VPC
###################################################################################################
vpc = Vpc(aws_provider, f"{resource_prefix}-vpc", {
    'availability_zones': available.names, 
    'resource_prefix': resource_prefix, 
    'public_subnet_count': public_subnet_count, 
    'private_subnet_count': private_subnet_count, 
    'cidr_block': vpc_cidr_block, 
    'enable_dns_support': config.get_bool("enable_dns_support") or True, 
    'enable_dns_hostnames': config.get_bool("enable_dns_host_name") or True
})

pulumi.export("vpc_id", vpc.vpc_id)
pulumi.export("vpc_cidr_block", vpc.cidr_block)
pulumi.export("nat_public_ip", vpc.nat_public_ip)

## Hosted Zone & Certificate
###################################################################################################
if create_r53_zone:
    zone = Route53(aws_provider, f"{resource_prefix}-route53", {
        'resource_prefix': resource_prefix, 
        'zone_name': zone_name,
        'wait_for_validation': route53_wait_for_validation
    })

    pulumi.export("zone_name", zone.zone_name)
    pulumi.export("hosted_zone_id", zone.hosted_zone_id)
    pulumi.export("certificate_arn", zone.certificate_arn)
    pulumi.export("nameservers", zone.nameservers)

## EKS Cluster
###################################################################################################
if create_eks_cluster:
    eks = Eks(aws_provider, vpc, f"{resource_prefix}-eks", {
        'cluster_name': resource_prefix, 
        'k8s_version': kubernetes_version, 
        'k8s_upgrade_policy': kubernetes_upgrade_policy, 
        'vpc_id': vpc.vpc_id, 
        'vpc_cidr': vpc_cidr_block, 
        'private_subnet_ids': vpc.private_subnet_ids, 
        'enable_private_access': cluster_enable_private_access, 
        'enable_public_access': cluster_enable_public_access, 
        'storage_class_name': storage_class_name,
        'public_access_cidrs': std.concat_output(input=[
            cluster_access_cidrs,
            [vpc.nat_public_ip.apply(lambda nat_public_ip: f"{nat_public_ip}/32")],
        ]).apply(lambda invoke: [cidr for cidr in invoke.result if cidr is not None])
    })

    k8s_provider = k8s.Provider(f"{resource_prefix}-k8s-provider",
        kubeconfig=pulumi.Output.all(
            eks.eks_endpoint,
            eks.certificate_authority,  # you'll need to expose this from Eks
            eks.cluster_name,
        ).apply(lambda args: json.dumps({
            "apiVersion": "v1",
            "clusters": [{"cluster": {"server": args[0], "certificate-authority-data": args[1]}, "name": "eks"}],
            "contexts": [{"context": {"cluster": "eks", "user": "eks"}, "name": "eks"}],
            "current-context": "eks",
            "users": [{"name": "eks", "user": {"exec": {
                "apiVersion": "client.authentication.k8s.io/v1beta1",
                "command": "aws",
                "args": ["eks", "get-token", "--cluster-name", args[2]],
            }}}],
        })),
        opts=pulumi.ResourceOptions(parent=eks)
    )

    eks_nodes_ec2 = EksNodesEc2(aws_provider, eks, vpc, f"{resource_prefix}-eks-nodes", {
        'cluster_name': resource_prefix, 
        'aws_iam_role_node_arn': eks.aws_iam_role_node_arn, 
        'nodegroup_name': "ng", 
        'private_subnet_ids': vpc.private_subnet_ids, 
        'instance_types': eks_node_group_instance_types, 
        'sizeMin': 0,
        'sizeMax': eks_max_nodes_per_nodegroup, 
        'sizeDesired': eks_nodes_per_nodegroup, 
        'memory_min': eks_instance_min_mem, 
        'vcpu_min': eks_instance_min_vcpu, 
        'tags': common_tags,
        'asg_schedule': asg_schedule if create_asg_schedule else {}
    })

    pulumi.export("asg_creation_info", eks_nodes_ec2.asg_creation_info)
    pulumi.export("eks_node_role_arn", eks.aws_iam_role_node_arn)
    pulumi.export("eks_cluster_role_name", eks.eks_cluster_role_name)
    pulumi.export("eks_cluster_name", eks.cluster_name)
    pulumi.export("eks_cluster_id", eks.cluster_id)
    pulumi.export("eks_cluster_status", eks.status)
    pulumi.export("eks_cluster_endpoint", eks.eks_endpoint)
    pulumi.export("storage_class_name", storage_class_name)

    pulumi.export("eks_nodegroup_ids", eks_nodes_ec2.eks_nodegroup_ids)
    pulumi.export("eks_nodegroup_arns", eks_nodes_ec2.eks_nodegroup_arns)
    pulumi.export("eks_nodegroup_asgs", eks_nodes_ec2.eks_nodegroup_asgs)

## END: if create_eks_cluster
###################################################################################################
    
## EFS
###################################################################################################
efs = []
if create_efs_filesystem:
    efs.append(Efs(aws_provider, f"{resource_prefix}-efs-1", {
        'private_subnet_ids': vpc.private_subnet_ids, 
        'resource_prefix': resource_prefix, 
        'vpc_id': vpc.vpc_id, 
        'vpc_cidr': vpc_cidr_block,
        }
    ))

    pulumi.export("efs_mount_target", [__item.efs_mount_target for __item in efs])
    pulumi.export("efs_system_id", [__item.efs_file_system_id for __item in efs])

    if create_eks_cluster:
        efs_addon = EfsAddon(k8s_provider, eks_nodes_ec2, f"{resource_prefix}-efs-addon", {
            'cluster_name': eks.cluster_name, 
            'oidc_provider_arn': eks.oidc_provider_arn, 
            'oidc_provider_url': eks.oidc_provider_url,
            'storage_class_name': "efs-sc-1000",
            'efs_filesystem_id': efs[0].efs_file_system_id
        })

## ALB Controller
###################################################################################################
if create_alb_controller:
    alb = LoadBalancer(k8s_provider, eks, f"{resource_prefix}-alb-controller", {
        'cluster_name': eks.cluster_name,
        'resource_prefix': resource_prefix,
        'oidc_provider_arn': eks.oidc_provider_arn,
        'oidc_provider_url': eks.oidc_provider_url,
    })

    pulumi.export("alb_controller_sa_name", alb.service_account_name)
    pulumi.export("alb_controller_role_arn", alb.lb_controller_role_arn)

