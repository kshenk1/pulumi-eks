import pulumi
from mocks import PulumiEksMocks
import json
import importlib.util
import os

# ---------------------------------------------------------------------------
# Set up mocks and config BEFORE importing the Pulumi program
# ---------------------------------------------------------------------------
pulumi.runtime.set_mocks(
    PulumiEksMocks(),
    preview=False,
    project="pulumi-eks",
    stack="cbci",
)

# Set required config values
pulumi.runtime.set_all_config({
    "pulumi-eks:resource_prefix": "test-cluster",
    "pulumi-eks:vpc_cidr_block": "10.0.0.0/20",
    "pulumi-eks:kubernetes_version": "1.31",
    "pulumi-eks:zone_name": "test.example.com",
    "pulumi-eks:storage_class_name": "efs-sc-1000",
    "pulumi-eks:eks_node_group_instance_types": json.dumps(["t3.xlarge"]),
    "pulumi-eks:storage_mount_options": json.dumps(["tls", "iam"]),
    "pulumi-eks:create_eks_cluster": "true",
    "pulumi-eks:create_alb_controller": "true",
    "pulumi-eks:create_efs_filesystem": "true",
    "pulumi-eks:create_r53_zone": "true",
    "pulumi-eks:route53_wait_for_validation": "true",
    "pulumi-eks:myip": "203.0.113.50/32",
    "aws:region": "us-east-1",
})

_spec = importlib.util.spec_from_file_location(
    "pulumi_program",
    os.path.join(os.path.dirname(__file__), "..", "__main__.py"),
)
infra = importlib.util.module_from_spec(_spec)
try:
    _spec.loader.exec_module(infra)
except Exception as e:
    print(f"ERROR loading __main__.py: {e}")
    raise


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVpc:
    @pulumi.runtime.test
    def test_vpc_is_created(self):
        def check(vpc_id):
            assert vpc_id is not None
        return infra.vpc.vpc_id.apply(check)

    @pulumi.runtime.test
    def test_vpc_has_private_subnets(self):
        def check(ids):
            assert len(ids) >= 2, f"Expected at least 2 private subnets, got {len(ids)}"
        return pulumi.Output.all(*infra.vpc.private_subnet_ids).apply(check)

    @pulumi.runtime.test
    def test_nat_gateway_has_public_ip(self):
        def check(ip):
            assert ip is not None and ip != ""
        return infra.vpc.nat_public_ip.apply(check)


class TestEksCluster:
    @pulumi.runtime.test
    def test_cluster_is_active(self):
        def check(status):
            assert status == "ACTIVE"
        return infra.eks.status.apply(check)

    @pulumi.runtime.test
    def test_cluster_has_endpoint(self):
        def check(endpoint):
            assert endpoint.startswith("https://")
        return infra.eks.eks_endpoint.apply(check)

    @pulumi.runtime.test
    def test_oidc_provider_url_has_no_https(self):
        """The OIDC URL stored on the Eks component should have https:// stripped."""
        def check(url):
            assert not url.startswith("https://"), \
                f"OIDC URL should not have https:// prefix, got: {url}"
            assert "oidc.eks" in url
        return infra.eks.oidc_provider_url.apply(check)

    @pulumi.runtime.test
    def test_oidc_provider_arn_is_valid(self):
        def check(arn):
            assert arn.startswith("arn:aws:iam:")
            assert "oidc-provider" in arn
        return infra.eks.oidc_provider_arn.apply(check)

    @pulumi.runtime.test
    def test_node_role_arn_exists(self):
        def check(arn):
            assert arn is not None
            assert arn.startswith("arn:aws:iam:")
        return infra.eks.aws_iam_role_node_arn.apply(check)


class TestEksNodes:
    @pulumi.runtime.test
    def test_nodegroups_created(self):
        def check(arns):
            assert len(arns) >= 2, f"Expected at least 2 node groups, got {len(arns)}"
        return pulumi.Output.all(*infra.eks_nodes_ec2.eks_nodegroup_arns).apply(check)

    @pulumi.runtime.test
    def test_nodegroup_ids_exist(self):
        def check(ids):
            for ng_id in ids:
                assert ng_id is not None
        return pulumi.Output.all(*infra.eks_nodes_ec2.eks_nodegroup_ids).apply(check)


class TestAlbController:
    @pulumi.runtime.test
    def test_alb_role_arn_exported(self):
        def check(arn):
            assert arn is not None
            assert "role" in arn
        return infra.alb.lb_controller_role_arn.apply(check)

    @pulumi.runtime.test
    def test_service_account_name(self):
        def check(name):
            assert name == "aws-load-balancer-controller"
        return pulumi.Output.from_input(infra.alb.service_account_name).apply(check)


class TestEfs:
    @pulumi.runtime.test
    def test_efs_mount_target_exists(self):
        def check(dns):
            assert dns is not None
            assert "efs" in dns
        return infra.efs[0].efs_mount_target.apply(check)

    @pulumi.runtime.test
    def test_efs_filesystem_id_exists(self):
        def check(fs_id):
            assert fs_id is not None
            assert fs_id.startswith("fs-")
        return infra.efs[0].efs_file_system_id.apply(check)


class TestRoute53:
    @pulumi.runtime.test
    def test_hosted_zone_id_exists(self):
        def check(zone_id):
            assert zone_id is not None
        return infra.zone.hosted_zone_id.apply(check)

    @pulumi.runtime.test
    def test_certificate_arn_exists(self):
        def check(arn):
            assert arn is not None
            assert "acm" in arn
        return infra.zone.certificate_arn.apply(check)

    @pulumi.runtime.test
    def test_nameservers_returned(self):
        def check(ns):
            assert len(ns) >= 2
        return infra.zone.nameservers.apply(check)


class TestIamPolicies:
    @pulumi.runtime.test
    def test_node_role_assume_policy_has_no_object_repr(self):
        """
        Regression test: ensure the assume role policy on the EKS node role
        does not contain Python object repr strings like
        '<pulumi_std.replace.ReplaceResult object at 0x...>'.
        """
        def check(policy_json):
            assert "object at 0x" not in policy_json, \
                "Policy contains Python object repr -- use .apply() to resolve values"
        return infra.eks.eks_node_role.assume_role_policy.apply(check)

    @pulumi.runtime.test
    def test_node_role_trust_policy_structure(self):
        """Verify the trust policy has the expected statements."""
        def check(policy_json):
            policy = json.loads(policy_json)
            assert policy["Version"] == "2012-10-17"
            statements = policy["Statement"]
            assert len(statements) == 2

            # First statement: EC2 service
            assert statements[0]["Principal"]["Service"] == "ec2.amazonaws.com"
            assert statements[0]["Action"] == "sts:AssumeRole"

            # Second statement: OIDC web identity
            assert statements[1]["Action"] == "sts:AssumeRoleWithWebIdentity"
            assert "Federated" in statements[1]["Principal"]
            assert "StringEquals" in statements[1]["Condition"]

        return infra.eks.eks_node_role.assume_role_policy.apply(check)