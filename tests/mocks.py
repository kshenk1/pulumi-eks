"""
Pulumi unit tests for pulumi-eks infrastructure.

Usage:
    cd <project-root>
    source .venv/bin/activate
    pip install pytest
    pytest tests/test_infra.py -v
"""
import pulumi

# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------
class PulumiEksMocks(pulumi.runtime.Mocks):
    """
    Mocks for every resource type and provider function used by the
    pulumi-eks project.
    """

    def new_resource(self, args: pulumi.runtime.MockResourceArgs):
        outputs = {**args.inputs}

        # ── AWS IAM ──────────────────────────────────────────────
        if args.typ == "aws:iam/role:Role":
            outputs["arn"] = f"arn:aws:iam::123456789012:role/{args.name}"
            outputs["name"] = outputs.get("name", args.name)
            outputs["uniqueId"] = "AROAMOCKID"

        elif args.typ == "aws:iam/policy:Policy":
            outputs["arn"] = f"arn:aws:iam::123456789012:policy/{args.name}"

        elif args.typ == "aws:iam/rolePolicyAttachment:RolePolicyAttachment":
            pass  # no extra outputs needed

        elif args.typ == "aws:iam/openIdConnectProvider:OpenIdConnectProvider":
            outputs["arn"] = (
                "arn:aws:iam::123456789012:oidc-provider/"
                "oidc.eks.us-east-1.amazonaws.com/id/ABCDEF1234"
            )
            outputs["url"] = "https://oidc.eks.us-east-1.amazonaws.com/id/ABCDEF1234"

        # ── AWS EC2 / VPC ────────────────────────────────────────
        elif args.typ == "aws:ec2/vpc:Vpc":
            outputs["id"] = "vpc-mock123"
            outputs["cidrBlock"] = outputs.get("cidrBlock", "10.0.0.0/20")

        elif args.typ == "aws:ec2/subnet:Subnet":
            outputs["id"] = f"subnet-mock-{args.name}"

        elif args.typ == "aws:ec2/internetGateway:InternetGateway":
            outputs["id"] = "igw-mock123"

        elif args.typ == "aws:ec2/routeTable:RouteTable":
            outputs["id"] = "rtb-mock123"

        elif args.typ == "aws:ec2/routeTableAssociation:RouteTableAssociation":
            outputs["id"] = f"rtba-mock-{args.name}"

        elif args.typ == "aws:ec2/eip:Eip":
            outputs["id"] = "eipalloc-mock123"
            outputs["publicIp"] = "203.0.113.1"

        elif args.typ == "aws:ec2/natGateway:NatGateway":
            outputs["id"] = "nat-mock123"
            outputs["publicIp"] = "203.0.113.1"

        elif args.typ == "aws:ec2/securityGroup:SecurityGroup":
            outputs["id"] = f"sg-mock-{args.name}"

        elif args.typ == "aws:ec2/launchTemplate:LaunchTemplate":
            outputs["id"] = "lt-mock123"
            outputs["latestVersion"] = "1"

        # ── AWS EKS ──────────────────────────────────────────────
        elif args.typ == "aws:eks/cluster:Cluster":
            cluster_name = outputs.get("name", args.name)
            outputs["arn"] = f"arn:aws:eks:us-east-1:123456789012:cluster/{cluster_name}"
            outputs["endpoint"] = "https://ABCDEF1234.gr7.us-east-1.eks.amazonaws.com"
            outputs["status"] = "ACTIVE"
            outputs["certificateAuthority"] = {"data": "bW9jay1jYS1kYXRh"}
            outputs["identities"] = [
                {
                    "oidcs": [
                        {"issuer": "https://oidc.eks.us-east-1.amazonaws.com/id/ABCDEF1234"}
                    ]
                }
            ]

        elif args.typ == "aws:eks/nodeGroup:NodeGroup":
            outputs["arn"] = f"arn:aws:eks:us-east-1:123456789012:nodegroup/{args.name}"
            outputs["status"] = "ACTIVE"
            outputs["resources"] = [
                {"autoscalingGroups": [{"name": f"eks-{args.name}-asg"}]}
            ]

        elif args.typ == "aws:eks/addon:Addon":
            outputs["addonName"] = outputs.get("addonName", "aws-efs-csi-driver")

        # ── AWS EFS ──────────────────────────────────────────────
        elif args.typ == "aws:efs/fileSystem:FileSystem":
            outputs["id"] = "fs-mock123"
            outputs["dnsName"] = "fs-mock123.efs.us-east-1.amazonaws.com"

        elif args.typ == "aws:efs/mountTarget:MountTarget":
            outputs["id"] = f"fsmt-mock-{args.name}"

        # ── AWS Route53 / ACM ────────────────────────────────────
        elif args.typ == "aws:route53/zone:Zone":
            outputs["id"] = "Z0123456789MOCK"
            outputs["nameServers"] = [
                "ns-111.awsdns-11.com",
                "ns-222.awsdns-22.net",
            ]

        elif args.typ == "aws:route53/record:Record":
            outputs["fqdn"] = outputs.get("name", f"{args.name}.example.com")

        elif args.typ == "aws:acm/certificate:Certificate":
            outputs["arn"] = f"arn:aws:acm:us-east-1:123456789012:certificate/mock-cert"
            outputs["domainValidationOptions"] = [
                {
                    "domainName": "*.example.com",
                    "resourceRecordName": "_abc.example.com",
                    "resourceRecordType": "CNAME",
                    "resourceRecordValue": "_xyz.acm-validations.aws.",
                }
            ]

        elif args.typ == "aws:acm/certificateValidation:CertificateValidation":
            outputs["certificateArn"] = outputs.get("certificateArn", "arn:aws:acm:mock")

        # ── AWS Autoscaling ──────────────────────────────────────
        elif args.typ == "aws:autoscaling/schedule:Schedule":
            outputs["id"] = f"asg-schedule-{args.name}"

        elif args.typ == "aws:autoscaling/tag:Tag":
            pass

        # ── AWS Provider ─────────────────────────────────────────
        elif args.typ == "pulumi:providers:aws":
            pass

        # ── TLS ──────────────────────────────────────────────────
        elif args.typ == "tls:index/privateKey:PrivateKey":
            outputs["privateKeyPem"] = "-----BEGIN RSA PRIVATE KEY-----\nMOCK\n-----END RSA PRIVATE KEY-----\n"
            outputs["publicKeyPem"] = "-----BEGIN PUBLIC KEY-----\nMOCK\n-----END PUBLIC KEY-----\n"

        elif args.typ == "tls:index/selfSignedCert:SelfSignedCert":
            outputs["certPem"] = "-----BEGIN CERTIFICATE-----\nMOCKCA\n-----END CERTIFICATE-----\n"

        elif args.typ == "tls:index/certRequest:CertRequest":
            outputs["certRequestPem"] = "-----BEGIN CERTIFICATE REQUEST-----\nMOCK\n-----END CERTIFICATE REQUEST-----\n"

        elif args.typ == "tls:index/locallySignedCert:LocallySignedCert":
            outputs["certPem"] = "-----BEGIN CERTIFICATE-----\nMOCKSERVER\n-----END CERTIFICATE-----\n"

        # ── Kubernetes ───────────────────────────────────────────
        elif args.typ == "pulumi:providers:kubernetes":
            pass

        elif args.typ == "kubernetes:core/v1:ServiceAccount":
            outputs["metadata"] = outputs.get("metadata", {"name": args.name, "namespace": "kube-system"})

        elif args.typ == "kubernetes:core/v1:Secret":
            outputs["metadata"] = outputs.get("metadata", {"name": args.name, "namespace": "kube-system"})

        elif args.typ == "kubernetes:helm.sh/v4:Chart":
            pass

        elif args.typ == "kubernetes:storage.k8s.io/v1:StorageClass":
            outputs["id"] = f"sc-{args.name}"

        # ── Null / Command ───────────────────────────────────────
        elif args.typ == "null:index:Resource":
            pass

        elif args.typ == "command:local:Command":
            outputs["stdout"] = ""

        # ── Time ─────────────────────────────────────────────────
        elif args.typ.startswith("time:"):
            pass

        #return [f"{args.name}_id", outputs]
        return [outputs.get("id", f"{args.name}_id"), outputs]


    def call(self, args: pulumi.runtime.MockCallArgs):
        # aws.get_caller_identity()
        if args.token == "aws:index/getCallerIdentity:getCallerIdentity":
            return {
                "accountId": "123456789012",
                "arn": "arn:aws:iam::123456789012:user/mock",
                "userId": "AIDAMOCKUSERID",
            }

        # aws.get_availability_zones()
        if args.token == "aws:index/getAvailabilityZones:getAvailabilityZones":
            return {
                "names": ["us-east-1a", "us-east-1b", "us-east-1c"],
                "zoneIds": ["use1-az1", "use1-az2", "use1-az3"],
                "id": "us-east-1",
            }

        # tls.get_certificate()
        if args.token == "tls:index/getCertificate:getCertificate":
            return {
                "certificates": [
                    {"sha1Fingerprint": "aabbccddee11223344556677889900aabbccddee"}
                ]
            }

        # aws.route53.get_zone()
        if args.token == "aws:route53/getZone:getZone":
            return {
                "id": "Z9999999PARENT",
                "name": "example.com",
                "zoneId": "Z9999999PARENT",
            }

        # std.concat
        if args.token == "std:index:concat":
            # Flatten the input lists
            result = []
            for item in args.args.get("input", []):
                if isinstance(item, list):
                    result.extend(item)
                else:
                    result.append(item)
            return {"result": result}

        # std.replace
        if args.token == "std:index:replace":
            text = args.args.get("text", "")
            search = args.args.get("search", "")
            replace = args.args.get("replace", "")
            return {"result": text.replace(search, replace)}

        # std.timestamp
        if args.token == "std:index:timestamp":
            return {"result": "2025-01-01T00:00:00Z"}

        return {}