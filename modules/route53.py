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

        zone = aws.route53.Zone(f"{name}-zone",
            name=args['zone_name'],
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        cert = aws.acm.Certificate(f"{name}-cert",
            domain_name=f"*.{args['zone_name']}",
            validation_method="DNS",
            opts = pulumi.ResourceOptions(parent=self, provider=provider)
        )

        validation_record = aws.route53.Record(f"{name}-cert-validation-record",
            zone_id=zone.zone_id,
            name=cert.domain_validation_options[0].resource_record_name,
            type=cert.domain_validation_options[0].resource_record_type,
            records=[cert.domain_validation_options[0].resource_record_value],
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

        self.zone_id = zone.zone_id
        self.certificate_arn = cert.arn
        self.nameservers = zone.name_servers

        self.register_outputs({
            "zone_id": self.zone_id,
            "certificate_arn": self.certificate_arn,
            "nameservers": self.nameservers,
        })
        