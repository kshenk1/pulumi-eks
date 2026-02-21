import pulumi
from scheduling import Scheduling
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_aws as aws
import pulumi_null as null
import pulumiverse_time as time


def not_implemented(msg):
    raise NotImplementedError(msg)

class EksNodesEc2Args(TypedDict, total=False):
    cluster_name: Input[Any]
    private_subnet_ids: Input[Any]
    policyAttachmentAmazonEKSWorkerNodePolicy: Input[Any]
    policyAttachmentAmazonEKSCNIPolicy: Input[Any]
    policyAttachmentAmazonEC2ContainerRegistryReadOnly: Input[Any]
    policyAttachmentAmazonSSMManagedInstanceCore: Input[Any]
    awsIamRoleNodeArn: Input[Any]
    nodegroup_name: Input[Any]
    sizeMin: Input[float]
    sizeMax: Input[float]
    sizeDesired: Input[float]
    instanceTypes: Input[Any]
    memory_min: Input[Any]
    vcpu_min: Input[Any]
    tags: Input[Any]
    asg_schedule: Input[Any]

class EksNodesEc2(pulumi.ComponentResource):
    def __init__(self, name: str, args: EksNodesEc2Args, opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:EksNodesEc2", name, args, opts)

        node_template = aws.ec2.LaunchTemplate(f"{name}-node-template",
            name=f"{args['cluster_name']}-nodes",
            instance_requirements={
                "allowed_instance_types": args["instanceTypes"],
                "instance_generations": ["current"],
                "memory_mib": {
                    "min": args["memory_min"],
                },
                "vcpu_count": {
                    "min": args["vcpu_min"],
                },
            },
            metadata_options={
                "http_put_response_hop_limit": 2,
                "http_endpoint": "enabled",
            },
            tag_specifications=[{
                "resource_type": "instance",
                "tags": {
                    **args["tags"],
                    "Name": f"{args['cluster_name']}-node"
                },
            }],
            opts=pulumi.ResourceOptions(parent=self))

        node = []
        for _range in [{"value": i} for i in range(0, len(args["private_subnet_ids"]))]:
            ng = aws.eks.NodeGroup(f"{name}-node-{_range['value']}",
                cluster_name=args["cluster_name"],
                node_group_name=f"{args['cluster_name']}-{args['nodegroup_name']}-{_range['value']}",
                node_role_arn=args["awsIamRoleNodeArn"],
                subnet_ids=[args["private_subnet_ids"][_range["value"]]],
                instance_types=args["instanceTypes"],
                ami_type="AL2023_x86_64_STANDARD",
                launch_template={
                    "id": node_template.id,
                    "version": node_template.latest_version,
                },
                scaling_config={
                    "desired_size": args["sizeDesired"],
                    "max_size": args["sizeMax"],
                    "min_size": args["sizeMin"],
                },
                tags={
                    **args["tags"],
                    "k8s.io/cluster-autoscaler/enabled": "true",
                    f"k8s.io/cluster-autoscaler/{args['cluster_name']}": "owned",
                    f"k8s.io/cluster/{args['cluster_name']}": "owned",
                },
                opts=pulumi.ResourceOptions(parent=self))
            node.append(ng)

            # Tag the underlying ASG with all tags
            for key, val in args["tags"].items():
                aws.autoscaling.Tag(
                    f"{name}-asg-tag-{_range['value']}-{key}",
                    autoscaling_group_name=ng.resources.apply(
                        lambda r: r[0].autoscaling_groups[0].name
                    ),
                    tag={
                        "key": key,
                        "value": val,
                        "propagate_at_launch": True,
                    },
                    opts=pulumi.ResourceOptions(parent=ng),
                )

            # Apply schedules to the ASG if all required schedule keys are present
            asg_schedule = args.get("asg_schedule") or {}
            required_schedule_keys = ["weekday_config_down", "weekday_config_up", "weekend_config", "timezone"]
            if asg_schedule and all(k in asg_schedule for k in required_schedule_keys):
                Scheduling(f"scheduling-{_range['value']}", {
                    'autoscaling_group_name': ng.resources.apply(
                        lambda r: r[0].autoscaling_groups[0].name
                    ),
                    'weekday_config_down': asg_schedule["weekday_config_down"],
                    'weekday_config_up': asg_schedule["weekday_config_up"],
                    'weekend_config': asg_schedule["weekend_config"],
                    'timezone': asg_schedule["timezone"]
                },
                    opts=pulumi.ResourceOptions(parent=ng)
                )

        asg_names = pulumi.Output.all(*[ng.resources for ng in node]).apply(
            lambda resources_list: [
                asg.name
                for r in resources_list if r
                for asg in r.autoscaling_groups
            ]
        )
        self.eks_nodegroup_asgs = asg_names
        self.eks_nodegroup_arns = [__item.arn for __item in node]
        self.eks_nodegroup_ids = [__item.id for __item in node]

        self.register_outputs({
            'eks_nodegroup_arns': [__item.arn for __item in node], 
            'eks_nodegroup_ids': [__item.id for __item in node], 
            'eks_nodegroup_asgs': asg_names
        })