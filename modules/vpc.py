import pulumi
from typing import Optional, Sequence, TypedDict
import pulumi_aws as aws


class VpcArgs(TypedDict):
    cidr_block: str
    subnet_cidr_prefix: str
    public_subnet_count: int
    private_subnet_count: int
    enable_dns_hostnames: bool
    enable_dns_support: bool
    availability_zones: Sequence[str]
    resource_prefix: str

class Vpc(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: VpcArgs, opts: Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Vpc", name, args, opts)

        resource_prefix = args["resource_prefix"]
        child_opts = pulumi.ResourceOptions(parent=self, provider=provider)

        # VPC
        main = aws.ec2.Vpc(
            f"{name}-main",
            cidr_block=args["cidr_block"],
            enable_dns_support=args["enable_dns_support"],
            enable_dns_hostnames=args["enable_dns_hostnames"],
            tags={
                "Name": f"{resource_prefix}-vpc",
                f"kubernetes.io/cluster/{resource_prefix}": "shared",
            },
            opts=child_opts,
        )

        # Private subnets
        private_sn = []
        for i in range(args["private_subnet_count"]):
            private_sn.append(
                aws.ec2.Subnet(
                    f"{name}-private-sn-{i}",
                    availability_zone=args["availability_zones"][i],
                    cidr_block=f"{args['subnet_cidr_prefix']}.{int(i) * 16}.0/20",
                    vpc_id=main.id,
                    tags={
                        "Name": f"{resource_prefix}-private-sn-{i}",
                        f"kubernetes.io/cluster/{resource_prefix}": "shared",
                        "kubernetes.io/role/internal-elb": "1",
                    },
                    opts=child_opts,
                )
            )

        # Public subnets
        public_sn = []
        for i in range(args["public_subnet_count"]):
            _num = i + int(args["private_subnet_count"])
            public_sn.append(
                aws.ec2.Subnet(
                    f"{name}-public-sn-{i}",
                    availability_zone=args["availability_zones"][i],
                    cidr_block=f"{args['subnet_cidr_prefix']}.{_num * 16}.0/20",
                    vpc_id=main.id,
                    map_public_ip_on_launch=True,
                    tags={
                        "Name": f"{resource_prefix}-public-sn-{i}",
                        f"kubernetes.io/cluster/{resource_prefix}": "shared",
                        "kubernetes.io/role/elb": "1",
                    },
                    opts=child_opts,
                )
            )

        # Internet gateway
        main_igw = aws.ec2.InternetGateway(
            f"{name}-main-igw",
            vpc_id=main.id,
            tags={"Name": f"{resource_prefix}-igw"},
            opts=child_opts,
        )

        # Public route table
        public_rtb = aws.ec2.RouteTable(
            f"{name}-public-rtb",
            vpc_id=main.id,
            routes=[{"cidr_block": "0.0.0.0/0", "gateway_id": main_igw.id}],
            tags={"Name": f"{resource_prefix}-public-rtb"},
            opts=child_opts,
        )

        for i, sn in enumerate(public_sn):
            aws.ec2.RouteTableAssociation(
                f"{name}-public-rtba-{i}",
                subnet_id=sn.id,
                route_table_id=public_rtb.id,
                opts=child_opts,
            )

        # NAT gateway
        cd_eip = aws.ec2.Eip(
            f"{name}-cd-eip",
            domain="vpc",
            tags={"Name": f"{resource_prefix}-gwip"},
            opts=child_opts,
        )

        nat_cd_gw = aws.ec2.NatGateway(
            f"{name}-nat-cd-gw",
            subnet_id=public_sn[0].id,
            allocation_id=cd_eip.id,
            tags={"Name": f"{resource_prefix}-nat"},
            opts=child_opts,
        )

        # Private route table
        private_rtb = aws.ec2.RouteTable(
            f"{name}-private-rtb",
            vpc_id=main.id,
            routes=[{"cidr_block": "0.0.0.0/0", "nat_gateway_id": nat_cd_gw.id}],
            tags={"Name": f"{resource_prefix}-private-rtb"},
            opts=child_opts,
        )

        for i, sn in enumerate(private_sn):
            aws.ec2.RouteTableAssociation(
                f"{name}-private-rtba-{i}",
                subnet_id=sn.id,
                route_table_id=private_rtb.id,
                opts=child_opts,
            )

        # Outputs
        self.vpc_id = main.id
        self.public_subnet_ids = [sn.id for sn in public_sn]
        self.private_subnet_ids = [sn.id for sn in private_sn]
        self.vpc_cidr_block = main.cidr_block
        self.nat_public_ip = nat_cd_gw.public_ip

        self.register_outputs({
            "vpc_id": self.vpc_id,
            "public_subnet_ids": self.public_subnet_ids,
            "private_subnet_ids": self.private_subnet_ids,
            "vpc_cidr_block": self.vpc_cidr_block,
            "nat_public_ip": self.nat_public_ip,
        })