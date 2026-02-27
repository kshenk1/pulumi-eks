import pulumi
from pulumi import Input
from typing import Optional, TypedDict
import pulumi_aws as aws

class Route53Args(TypedDict, total=False):
    resource_prefix: Input[str]
    zone_name: Input[str]
    wait_for_validation: Input[bool]

class Route53(pulumi.ComponentResource):
    def __init__(self, provider: aws.Provider, name: str, args: Route53Args, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:Route53", name, args, opts)

        # 1. Create the NEW child zone (e.g., dev.example.com)
        child_zone = aws.route53.Zone(f"{name}-child-zone",
            name=args['zone_name'],
            opts=pulumi.ResourceOptions(parent=self, provider=provider)
        )

        # 2. Look up your EXISTING parent zone (e.g., example.com)
        # We split the name to get the parent (dev.example.com -> example.com)
        parent_domain = args['zone_name'].split('.', 1)[-1]
        parent_zone = aws.route53.get_zone(name=parent_domain)

        # 3. AUTOMATIC DELEGATION:
        # Create an NS record in the Parent Zone pointing to the Child Zone's nameservers
        aws.route53.Record(f"{name}-delegation-record",
            zone_id=parent_zone.id,
            name=args['zone_name'],
            type="NS",
            ttl=172800,
            # This is the "secret sauce": link the child servers to the parent record
            records=child_zone.name_servers, 
            opts=pulumi.ResourceOptions(parent=self, provider=provider)
        )

        cert = aws.acm.Certificate(f"{name}-cert",
            domain_name=f"*.{args['zone_name']}",
            validation_method="DNS",
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        dvo = cert.domain_validation_options.apply(
            lambda opts: {
                "name": opts[0].resource_record_name,
                "type": opts[0].resource_record_type,
                "value": opts[0].resource_record_value,
            } if opts else {"name": "", "type": "", "value": ""}
        )

        validation_record = aws.route53.Record(f"{name}-cert-validation-record",
            zone_id=child_zone.id,
            name=dvo["name"],
            type=dvo["type"],
            records=[dvo["value"]],
            ttl=300,
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        if args.get('wait_for_validation'):
            cert_validation = aws.acm.CertificateValidation(f"{name}-cert-validation",
                certificate_arn=cert.arn,
                validation_record_fqdns=[validation_record.fqdn],
                opts = pulumi.ResourceOptions(parent=self, provider=provider)
            )
        else:
            pulumi.log.info("Skipping ACM certificate validation as 'wait_for_validation' is not true.")  

        self.hosted_zone_id = child_zone.id
        self.certificate_arn = cert.arn
        self.nameservers = child_zone.name_servers

        self.register_outputs({
            "hosted_zone_id": self.hosted_zone_id,
            "certificate_arn": self.certificate_arn,
            "nameservers": self.nameservers,
        })
        