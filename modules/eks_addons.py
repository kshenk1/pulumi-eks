import pulumi
import json
from pulumi import Input
from typing import Optional, TypedDict
import pulumi_aws as aws
import pulumi_kubernetes as k8s

class EfsAddonsArgs(TypedDict):
    cluster_name: Input[str]
    oidc_provider_arn: Input[str]
    oidc_provider_url: Input[str]
    storage_class_name: Input[str]
    storage_mount_options: Input[list]
    efs_filesystem_id: Input[str]

class EfsAddon(pulumi.ComponentResource):
    def __init__(self, provider: k8s.Provider, stepparent: object, name: str, args: EfsAddonsArgs, opts:Optional[pulumi.ResourceOptions] = None):
        super().__init__("components:index:EfsAddon", name, args, opts)

        efs_csi_role = aws.iam.Role(f"{name}-role",
            assume_role_policy=pulumi.Output.all(
                args["oidc_provider_arn"],
                args["oidc_provider_url"],
            ).apply(lambda args: json.dumps({
                "Version": "2012-10-17",
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Federated": args[0]},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            f"{args[1]}:sub": "system:serviceaccount:kube-system:efs-csi-controller-sa",
                            f"{args[1]}:aud": "sts.amazonaws.com",
                        },
                    },
                }],
            })),
            opts = pulumi.ResourceOptions(parent=self)
        )

        storage_class_resource = k8s.storage.v1.StorageClass(f"{name}-efs-sc",
            provisioner="efs.csi.aws.com",
            allow_volume_expansion=True,
            kind="StorageClass",
            metadata={
                "name": args["storage_class_name"],
            },
            mount_options=args['storage_mount_options'],
            parameters={
                "provisioningMode": "efs-ap",
                "fileSystemId": args["efs_filesystem_id"],
                "directoryPerms": "700",
                "gid": "1000",
                "uid": "1000"
            },
            opts=pulumi.ResourceOptions(parent=self, provider=provider, depends_on=[stepparent])
        )

        aws.iam.RolePolicyAttachment(f"{name}-policy",
            role=efs_csi_role.name,
            policy_arn="arn:aws:iam::aws:policy/service-role/AmazonEFSCSIDriverPolicy",
            opts = pulumi.ResourceOptions(parent=self)
        )

        efs_csi_addon = aws.eks.Addon(f"{name}-addon",
            cluster_name=args["cluster_name"],
            addon_name="aws-efs-csi-driver",
            addon_version="v2.3.0-eksbuild.1",
            service_account_role_arn=efs_csi_role.arn,
            resolve_conflicts_on_create="OVERWRITE",
            resolve_conflicts_on_update="PRESERVE",
            opts = pulumi.ResourceOptions(parent=self, provider=provider, depends_on=[stepparent])
        )

        self.register_outputs({
            "storage_class_id": storage_class_resource.id,
            "efs_csi_role_arn": efs_csi_role.arn,
            "efs_csi_addon_name": efs_csi_addon.addon_name,
        })