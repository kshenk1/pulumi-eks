import pulumi
# from asg_tags import AsgTags
from efs import Efs
from eks import Eks
from eks_nodes_ec2 import EksNodesEc2
from rds import Rds
from scheduling import Scheduling
from vpc import Vpc
import pulumi_aws as aws
import pulumi_command as command
import pulumi_null as null
import pulumi_std as std


def die(msg):
    raise Exception(msg)

config = pulumi.Config()

resource_prefix = config.get("resource_prefix") or \
    die("resource_prefix is a required configuration value and must be set to continue. This value is used as a prefix for all resources created in this project.")
vpc_cidr_block = config.get("vpc_cidr_block") or \
    die("vpc_cidr_block is required")
subnet_cidr_prefix = config.get("subnet_cidr_prefix") or \
    die("subnet_cidr_prefix is required")
kubernetes_version = config.get("kubernetes_version") or \
    die("kubernetes_version is required. Example valid values: 1.33, 1.35, etc.")
eks_node_group_instance_types = config.get_object("eks_node_group_instance_types") or \
    die("eks_node_group_instance_types is required. Example valid value: [\"t3.large\", \"m5.large\"]")

pulumi.export("resourcePrefix", resource_prefix)

# The number of PUBLIC subnets to create
public_subnet_count = config.get_int("public_subnet_count")
if public_subnet_count is None:
    public_subnet_count = 2

# The number of PRIVATE subnets to create. This also current dictates the number of node-groups created for the cluster - 1 per private subnet.
private_subnet_count = config.get_int("private_subnet_count")
if private_subnet_count is None:
    private_subnet_count = 1

# A simple hash map of key-value pairs that will be attached to each object created by this terraform.
common_tags = config.get_object("common_tags")
if common_tags is None:
    common_tags = {
        "cb-environment": "development",
        "cb-expiry": "2027-2-30",
        "cb-owner": "professional-services",
        "cb-purpose": "undefined",
        "cb-user": "<username>",
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

create_eks_cluster = config.get_bool("create_eks_cluster") or False
create_efs_filesystem = config.get_bool("create_efs_filesystem") or False
create_rds_instance = config.get_bool("create_rds_instance") or False
create_asg_schedule = config.get_bool("create_asg_schedule") or False

cluster_enable_private_access = config.get_bool("cluster_enable_private_access")
cluster_enable_public_access = config.get_bool("cluster_enable_public_access")

# You typically want YOUR local IP address in here at the least. See: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/eks_cluster.html#public_access_cidrs
cluster_access_cidrs = [config.get("myip")]

asg_schedule = config.get_object("asg_schedule")

# The domain name of the hosted zone to use with infra created in here. 
# If you are NOT creating an RDS instance, any value will do here for now. 
# This is required when creating the RDS instance (create-rds-instance=true)
domain_name = config.get("domain_name")

if eks_max_nodes_per_nodegroup < eks_nodes_per_nodegroup and eks_nodes_per_nodegroup > 0:
    die("eks_max_nodes_per_nodegroup must be greater than eks_nodes_per_nodegroup!")

if create_rds_instance == True and domain_name == None:
    die("The domain_name cannot be blank when create_rds_instance is true")

# Used to configure credentials for providers
available = aws.get_availability_zones_output()

# Modules
vpc = Vpc("vpc", {
    'availability_zones': available.names, 
    'resource_prefix': resource_prefix, 
    'public_subnet_count': public_subnet_count, 
    'private_subnet_count': private_subnet_count, 
    'cidr_block': vpc_cidr_block, 
    'enable_dns_support': config.get_bool("enable_dns_support") or True, 
    'enable_dns_hostnames': config.get_bool("enable_dns_host_name") or True, 
    'subnet_cidr_prefix': subnet_cidr_prefix
})
pulumi.export("vpcId", vpc.vpcid)
pulumi.export("vpcCidrBlock", vpc.cidr_block)
pulumi.export("natPublicIp", vpc.nat_public_ip)

if create_eks_cluster:
    eks = Eks(f"eks", {
        'cluster_name': resource_prefix, 
        'k8s_version': kubernetes_version, 
        'k8s_upgrade_policy': kubernetes_upgrade_policy, 
        'vpcid': vpc.vpcid, 
        'vpc_cidr': vpc_cidr_block, 
        'private_subnet_ids': vpc.private_subnet_ids, 
        'enable_private_access': cluster_enable_private_access, 
        'enable_public_access': cluster_enable_public_access, 
        'public_access_cidrs': std.concat_output(input=[
            cluster_access_cidrs,
            [vpc.nat_public_ip.apply(lambda nat_public_ip: f"{nat_public_ip}/32")],
        ]).apply(lambda invoke: invoke.result)
    })

    eks_nodes_ec2 = EksNodesEc2(f"eks-nodes-ec2", {
        'cluster_name': resource_prefix, 
        'awsIamRoleNodeArn': eks.awsIamRoleNodeArn, 
        'nodegroup_name': "ng", 
        'policyAttachmentAmazonEC2ContainerRegistryReadOnly': eks.policyAttachmentAmazonEC2ContainerRegistryReadOnly, 
        'policyAttachmentAmazonEKSWorkerNodePolicy': eks.policyAttachmentAmazonEKSWorkerNodePolicy, 
        'policyAttachmentAmazonEKSCNIPolicy': eks.policyAttachmentAmazonEKSCNIPolicy, 
        'policyAttachmentAmazonSSMManagedInstanceCore': eks.policyAttachmentAmazonSSMManagedInstanceCore, 
        'private_subnet_ids': vpc.private_subnet_ids, 
        'instanceTypes': eks_node_group_instance_types, 
        'sizeMin': 0,
        'sizeMax': eks_max_nodes_per_nodegroup, 
        'sizeDesired': eks_nodes_per_nodegroup, 
        'memory_min': eks_instance_min_mem, 
        'vcpu_min': eks_instance_min_vcpu, 
        'tags': common_tags,
        'asg_schedule': asg_schedule if create_asg_schedule else {}
    })

    pulumi.export("eksNodeRoleArn", eks.awsIamRoleNodeArn)
    pulumi.export("eksClusterRoleName", eks.eks_cluster_role_name)
    pulumi.export("eksClusterName", eks.cluster_name)
    pulumi.export("eksClusterId", eks.clusterId)
    pulumi.export("eksClusterStatus", eks.status)
    pulumi.export("eksClusterEndpoint", eks.eksEp)

    pulumi.export("eksNodegroupIds", eks_nodes_ec2.eks_nodegroup_ids)
    pulumi.export("eksNodegroupArns", eks_nodes_ec2.eks_nodegroup_arns)
    pulumi.export("eksNodegroupASGs", eks_nodes_ec2.eks_nodegroup_asgs)

    create_kubeconfig = null.Resource("create_kubeconfig", triggers={
        "always_run": std.timestamp_output().apply(lambda invoke: invoke.result),
    })

    create_kubeconfig_provisioner0 = command.local.Command(
        "createKubeconfigProvisioner0", 
        create=eks.cluster_name.apply(
            lambda cluster_name: f"aws eks update-kubeconfig --name {cluster_name} --alias {resource_prefix}"
        ),
        opts = pulumi.ResourceOptions(depends_on=[create_kubeconfig])
    )

    ## END: if create_eks_cluster:
    

efs = []
if create_efs_filesystem:
    efs.append(Efs(f"efs-1", {
        'private_subnet_ids': vpc.private_subnet_ids, 
        'resource_prefix': resource_prefix, 
        'vpcid': vpc.vpcid, 
        'vpc_cidr': vpc_cidr_block
        }
    ))

    pulumi.export("efsMountTarget", [__item.efs_mount_target for __item in efs])
    pulumi.export("efsSystemId", [__item.efs_file_system_id for __item in efs])
    

if create_rds_instance:
    db_mysql = config.get_object("db_mysql")
    if db_mysql is None:
        db_mysql = {
            "allocated-storage": 25,
            "database-name": "thedb",
            "database-user": "theuser",
            "db-port": 3306,
            "engine": "mysql",
            "engine-version": "8.0.33",
            "instance-class": "db.m5d.large",
        }
    rds = Rds("rds", {
        'database_name': db_mysql["database_name"], 
        'engine': db_mysql["engine"], 
        'engine_version': db_mysql["engine_version"], 
        'db_port': db_mysql["db_port"], 
        'database_user': db_mysql["database_user"], 
        'instance_class': db_mysql["instance_class"], 
        'allocated_storage': db_mysql["allocated_storage"], 
        'domain_name': domain_name, 
        'rds_instance_identifier': resource_prefix, 
        'vpc_cidr_block': vpc_cidr_block, 
        'private_subnet_ids': vpc["private_subnet_ids"], 
        'vpc_id': vpc.vpcid, 
        'db_dns_name': f"db.{resource_prefix}.internal.com"
    })

    pulumi.export("dbName", std.join_output(separator=",", input=rds.name).apply(lambda invoke: invoke.result))
    pulumi.export("dbUser", std.join_output(separator=",", input=rds.user).apply(lambda invoke: invoke.result))
    pulumi.export("dbPassword", std.join_output(separator=",", input=rds.password).apply(lambda invoke: invoke.result))
    pulumi.export("dbEndpoint", std.join_output(separator=",", input=rds.endpoint).apply(lambda invoke: invoke.result))
    pulumi.export("dbAddress", std.join_output(separator=",", input=rds.address).apply(lambda invoke: invoke.result))
    pulumi.export("dbPort", std.join_output(separator=",", input=rds.port).apply(lambda invoke: invoke.result))

