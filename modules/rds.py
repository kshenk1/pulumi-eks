import pulumi
from pulumi import Input
from typing import Optional, Dict, TypedDict, Any
import pulumi_aws as aws
import pulumi_random as random
import pulumi_std as std

class RdsArgs(TypedDict, total=False):
    rds_instance_identifier: Input[str]
    private_subnet_ids: Input[list]
    vpc_id: Input[str]
    vpc_cidr_block: Input[str]
    database_name: Input[str]
    database_user: Input[str]
    db_dns_name: Input[str]
    engine: Input[str]
    engine_version: Input[str]
    instance_class: Input[str]
    allocated_storage: Input[float]
    db_port: Input[str]
    internal_domain: Input[str]

class Rds(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: RdsArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Rds", name, args, opts)

        default_sg = aws.rds.SubnetGroup(f"{name}-default-db",
            name=f"{args['rds_instance_identifier']}-subnet-group",
            description="Terraform RDS subnet group",
            subnet_ids=args["private_subnet_ids"],
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        rds_sg = aws.ec2.SecurityGroup(f"{name}-rds",
            name=f"{args['rds_instance_identifier']}-rds_security_group",
            description="Terraform RDS MySQL server",
            vpc_id=args["vpc_id"],
            tags={
                "Name": f"{args['rds_instance_identifier']}-rds-security-group",
            },
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        rds_ingress = aws.ec2.SecurityGroupRule(f"{name}-rds-ingress",
            type="ingress",
            from_port=args["db_port"],
            to_port=args["db_port"],
            protocol=aws.ec2.ProtocolType.TCP,
            cidr_blocks=[args["vpc_cidr_block"]],
            security_group_id=rds_sg.id,
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        nfs_egress_efs = aws.ec2.SecurityGroupRule(f"{name}-nfs-egress-efs",
            type="egress",
            from_port=0,
            to_port=0,
            protocol="-1",
            cidr_blocks=["0.0.0.0/0"],
            security_group_id=rds_sg.id,
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        default_parameter_group = aws.rds.ParameterGroup(f"{name}-default",
            name=f"{args['rds_instance_identifier']}-param-group",
            description="Terraform parameter group for mysql 8.0",
            family="mysql8.0",
            parameters=[
                {
                    "name": "character_set_server",
                    "value": "utf8",
                },
                {
                    "name": "character_set_client",
                    "value": "utf8",
                },
            ],
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        db_pw = random.RandomPassword(f"{name}-db",
            length=32,
            special=False,
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        default_instance = aws.rds.Instance(f"{name}-default",
            identifier=args["rds_instance_identifier"],
            allocated_storage=args["allocated_storage"],
            engine=args["engine"],
            instance_class=args["instance_class"],
            engine_version=args["engine_version"],
            port=args["db_port"],
            db_name=args["database_name"],
            username=args["database_user"],
            password=db_pw.result,
            db_subnet_group_name=default_sg.id,
            vpc_security_group_ids=[rds_sg.id],
            skip_final_snapshot=True,
            final_snapshot_identifier="Ignore",
            parameter_group_name=default_parameter_group.name,
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        # Create a private hosted zone associated with the VPC
        private_zone = aws.route53.Zone("rds-private-zone",
            name=args['internal_domain'],  # Your internal domain
            vpcs=[{
                "vpc_id": args["vpc_id"],
            }],
            comment="Private zone for RDS endpoints",
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        rds_record = aws.route53.Record(f"{name}-rds",
            zone_id=private_zone.id,
            name=args["db_dns_name"],
            type=aws.route53.RecordType.CNAME,
            ttl=300,
            records=[std.trimsuffix_output(input=default_instance.endpoint,
                suffix=f":{args['db_port']}").apply(lambda invoke: invoke.result)],
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        self.name = default_instance.db_name
        self.user = default_instance.username
        self.password = default_instance.password
        self.endpoint = default_instance.endpoint
        self.dns_name = rds_record.fqdn
        self.address = default_instance.address
        self.port = default_instance.port

        self.register_outputs({
            'name': self.name, 
            'user': self.user, 
            'password': self.password, 
            'endpoint': self.endpoint, 
            'dns_name': self.dns_name,
            'address': self.address, 
            'port': self.port
        })