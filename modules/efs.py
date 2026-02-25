import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_aws as aws

class EfsArgs(TypedDict):
    resource_prefix: Input[Any]
    private_subnet_ids: Input[Any]
    vpc_id: Input[Any]
    vpc_cidr: Input[Any]

class Efs(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: EfsArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Efs", name, args, opts)

        main = aws.efs.FileSystem(f"{name}-main",
            creation_token=args["resource_prefix"],
            performance_mode="generalPurpose",
            tags={
                "Name": args["resource_prefix"],
            },
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        efs_sg = aws.ec2.SecurityGroup(f"{name}-efs_sg",
            name=f"{args['resource_prefix']}_efs_sg",
            description="Cluster communication with worker nodes",
            vpc_id=args["vpc_id"],
            ingress=[{
                "protocol": "-1",
                "from_port": 0,
                "to_port": 0,
                "cidr_blocks": [args["vpc_cidr"]],
            }],
            egress=[{
                "from_port": 0,
                "to_port": 0,
                "protocol": "-1",
                "cidr_blocks": ["0.0.0.0/0"],
            }],
            tags={
                "Name": f"{args['resource_prefix']}_efs_sg",
            },
            opts = pulumi.ResourceOptions(parent=self, provider=provider))

        main_mounts = []
        for i in range(len(args["private_subnet_ids"])):
            main_mounts.append(aws.efs.MountTarget(f"{name}-main_mounts-{i}",
                file_system_id=main.id,
                subnet_id=args["private_subnet_ids"][i],
                security_groups=[efs_sg.id],
                opts = pulumi.ResourceOptions(parent=self, provider=provider)))

        
        self.efs_mount_target = main.dns_name
        self.efs_file_system_id = main.id

        self.register_outputs({
            'efs_mount_target': self.efs_mount_target, 
            'efs_file_system_id': self.efs_file_system_id
        })